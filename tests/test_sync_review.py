import json
import time
import uuid
import pytest
from app import app, db
from test_backups import setup_backup_case
from sync_review import review_context, decision_model, OUTCOMES


def mixed_plan():
    classes = ["new", "unchanged", "conflict", "older", "invalid", "review", "update"]
    return {
        "items": [
            {
                "preview": {
                    "classification": kind,
                    "title": "<script>long title</script> " + ("family " * 40),
                    "case_uuid": str(uuid.uuid4()),
                    "incoming_number": f"LONG-MARE-2026-00000{index}",
                    "destination_id": 1 if kind not in ("new", "review") else None,
                    "destination_number": (
                        "CM-TEST" if kind not in ("new", "review") else None
                    ),
                    "local_revision": "local-revision",
                    "incoming_revision": "incoming-revision",
                    "reason": "Validated reason",
                    "owner_warning": "Ownership warning",
                    "summary": None,
                    "suggestions": [],
                }
            }
            for index, kind in enumerate(classes)
        ],
        "catalog": None,
    }


@pytest.mark.parametrize(
    "classification,decision,target,action",
    [
        ("new", "", None, "new"),
        ("update", "", None, "update"),
        ("conflict", "", None, "unresolved"),
        ("conflict", "keep", None, "kept"),
        ("conflict", "replace", None, "replacement"),
        ("review", "new", None, "new"),
        ("review", "link", "1", "linked"),
        ("older", "", None, "older"),
        ("invalid", "", None, "invalid"),
        ("unchanged", "", None, "unchanged"),
    ],
)
def test_submission_decision_model(classification, decision, target, action):
    assert decision_model(classification, decision, target=target) == action


def test_link_validation_and_invalid_decisions():
    with pytest.raises(ValueError):
        decision_model("review", "link")
    with pytest.raises(ValueError):
        decision_model("conflict", "automatic-merge")
    with pytest.raises(ValueError):
        decision_model("update", "", ownership="anything")


def test_group_order_counts_indices_and_completion_labels():
    context = review_context(mixed_plan(), [])
    assert [group["key"] for group in context["action_groups"]] == [
        "review",
        "invalid",
        "update",
        "new",
        "unchanged",
        "older",
    ]
    assert [row["index"] for row in context["action_groups"][0]["rows"]] == [2, 5]
    assert context["action_counts"]["review"] == 2
    assert [group["expanded"] for group in context["action_groups"]] == [
        True,
        True,
        True,
        True,
        False,
        False,
    ]
    empty = review_context({"items": []}, [])
    assert empty["action_groups"] == [] and all(
        value == 0 for value in empty["action_counts"].values()
    )
    outcomes = [
        {"index": index, "action": action} for index, action in enumerate(OUTCOMES)
    ]
    result = review_context({"items": []}, outcomes)
    assert next(
        item
        for item in result["review_outcomes"]
        if item["action"] == "Failed and rolled back"
    )["badge"] == ("invalid", "Failed / rolled back")


def test_rendered_review_preserves_form_indices_and_escapes_labels():
    client, _, uid, _ = setup_backup_case()
    operation = str(uuid.uuid4())
    with app.app_context():
        account = (
            db().execute("SELECT user_uuid FROM users WHERE id=?", (uid,)).fetchone()[0]
        )
        db().execute(
            "INSERT INTO sync_imports(id,user_id,user_uuid,filename,checksum,created,stage,status,plan) VALUES(?,?,?,?,?,?,?,?,?)",
            (
                operation,
                uid,
                account,
                "review.zip",
                "0" * 64,
                time.time(),
                operation,
                "preview",
                json.dumps(mixed_plan()),
            ),
        )
        db().commit()
    response = client.get("/import-export/review/" + operation)
    assert response.status_code == 200
    text = response.get_data(as_text=True)
    assert 'name="decision-2"' in text and 'name="decision-5"' in text
    assert 'name="decision-0"' not in text
    assert (
        "&lt;script&gt;long title&lt;/script&gt;" in text
        and "<script>long title</script>" not in text
    )
    assert 'id="sync-group-unchanged" data-sync-panel hidden' in text
    assert 'id="sync-group-review" data-sync-panel hidden' not in text
    # Case review remains usable without privileged system-backup navigation.
    assert 'BACKUP &amp; RESTORE' not in text


def test_single_group_and_processed_decisions():
    plan = mixed_plan()
    plan["items"] = plan["items"][:1]
    context = review_context(plan, [])
    assert [group["key"] for group in context["action_groups"]] == ["new"]
    assert context["action_counts"]["new"] == 1
    assert decision_model("new", "keep") == "kept"
    assert decision_model("unchanged", "keep") == "unchanged"
    plan = mixed_plan()
    plan["items"][2]["done"] = True
    context = review_context(
        plan,
        [
            {
                "index": 2,
                "action": "Replaced by explicit decision",
                "decision": "replace",
                "ownership_decision": "incoming",
            }
        ],
    )
    row = context["action_groups"][0]["rows"][0]
    assert (
        row["done"] and row["decision"] == "replace" and row["ownership"] == "incoming"
    )
