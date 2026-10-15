"""Presentation labels and the submission's allowed synchronization decisions."""

GROUPS = (
    ("review", "Review required", ("conflict", "review"), True),
    ("invalid", "Invalid", ("invalid",), True),
    ("update", "Update existing", ("update",), True),
    ("new", "Import new", ("new",), True),
    ("unchanged", "Unchanged", ("unchanged",), False),
    ("older", "Skip older", ("older",), False),
)
DECISIONS = ("", "keep", "replace", "new", "link")
# This model is serialized for the browser; no outcome is inferred from CSS/text.
PLANNED = {
    "new": {"": "new"},
    "update": {"": "update"},
    "unchanged": {"": "unchanged"},
    "older": {"": "older"},
    "invalid": {"": "invalid"},
    "conflict": {"": "unresolved", "keep": "kept", "replace": "replacement"},
    "review": {"": "unresolved", "keep": "kept", "new": "new", "link": "linked"},
}
LABELS = {
    "new": "Import new",
    "update": "Update existing",
    "unchanged": "No changes",
    "older": "Skip older",
    "invalid": "Skip invalid",
    "unresolved": "Pending — unresolved",
    "kept": "Keep local — no content changes",
    "replacement": "Replace with incoming",
    "linked": "Link provenance — retain local content",
    "applied": "Already processed",
}
OUTCOMES = {
    "Imported new": ("new", "Imported new"),
    "Updated existing": ("update", "Updated existing"),
    "Unchanged": ("unchanged", "Unchanged"),
    "Skipped older": ("older", "Skipped older"),
    "Kept local": ("unchanged", "Kept local"),
    "Replaced by explicit decision": ("review", "Replaced by explicit decision"),
    "Conflict unresolved": ("review", "Conflict unresolved"),
    "Failed and rolled back": ("invalid", "Failed / rolled back"),
    "Invalid/failed": ("invalid", "Invalid / failed"),
}


def decision_model(
    classification, decision, ownership="local", target=None, *, validate_target=True
):
    # Preserve existing validation and decisions; linking already requires a target.
    if decision not in DECISIONS or ownership not in ("local", "incoming"):
        raise ValueError("Invalid conflict or ownership decision.")
    # Older API clients may send keep for automatic actions. Preserve the
    # existing precedence: unchanged/older/invalid remain no-ops; new/update keep.
    if classification in ("new", "update") and decision == "keep":
        return "kept"
    action = PLANNED.get(classification, {}).get(decision)
    if action is None:
        action = (
            PLANNED.get(classification, {}).get("", "unresolved")
            if classification not in ("conflict", "review")
            else "unresolved"
        )
    if (
        validate_target
        and action == "linked"
        and (not target or not str(target).isdigit())
    ):
        raise ValueError("Choose a destination for legacy linking.")
    return action


def review_context(plan, outcomes):
    prior = {outcome["index"]: outcome for outcome in outcomes}
    groups = []
    for key, label, classifications, expanded in GROUPS:
        rows = []
        for index, entry in enumerate(plan["items"]):
            item = entry["preview"]
            if item["classification"] not in classifications:
                continue
            outcome = prior.get(index, {})
            decision = outcome.get("decision", "")
            if decision not in PLANNED.get(item["classification"], {}):
                decision = ""
            rows.append(
                {
                    "item": item,
                    "index": index,
                    "done": bool(entry.get("done")),
                    "decision": decision,
                    "ownership": outcome.get("ownership_decision", "local"),
                    "outcome": outcome.get("action", ""),
                }
            )
        if rows:
            groups.append(
                {"key": key, "label": label, "expanded": expanded, "rows": rows}
            )
    counts = {
        key: sum(len(group["rows"]) for group in groups if group["key"] == key)
        for key, _, _, _ in GROUPS
    }
    decorated = [
        {
            **outcome,
            "badge": OUTCOMES.get(outcome["action"], ("invalid", outcome["action"])),
        }
        for outcome in outcomes
    ]
    return {
        "action_groups": groups,
        "action_counts": counts,
        "review_outcomes": decorated,
        "decision_model": {"actions": PLANNED, "labels": LABELS},
    }
