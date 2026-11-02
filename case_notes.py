"""Private Case notebook and transactional activity writer (not the audit log)."""

import json
import uuid
from datetime import datetime, timezone
from flask import abort, g, has_request_context, request
from authorization import has_permission
from task_collections import editable, readable, can_edit, case_state

FIELDS = {
    "note_uuid": "",
    "note_type": "user",
    "author_uuid": "",
    "edited": "",
    "event_type": "",
    "event_metadata": "{}",
    "source_id": "",
    "migrated_at": "",
}


def now():
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def initialize(con):
    columns = {r[1] for r in con.execute("PRAGMA table_info(notes)")}
    for name, default in FIELDS.items():
        if name not in columns:
            con.execute(
                f"ALTER TABLE notes ADD COLUMN {name} TEXT NOT NULL DEFAULT '{default}'"
            )
    con.execute(
        "CREATE TABLE IF NOT EXISTS case_activity_state(case_id INTEGER PRIMARY KEY REFERENCES cases(id) ON DELETE CASCADE,snapshot TEXT NOT NULL)"
    )
    con.execute(
        "CREATE INDEX IF NOT EXISTS notes_case_chronology ON notes(case_id,created,id)"
    )
    migrate(con)
    con.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS note_identity ON notes(case_id,note_uuid) WHERE note_uuid<>''"
    )
    con.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS note_submission_identity ON notes(case_id,author_uuid,source_id) WHERE source_id LIKE 'request:%'"
    )
    con.commit()


def migrate(con, cid=None):
    rows = con.execute(
        "SELECT * FROM notes WHERE note_uuid='' AND trim(body)<>''"
        + (" AND case_id=?" if cid is not None else ""),
        (() if cid is None else (cid,)),
    ).fetchall()
    for row in rows:
        if not row["body"].strip():
            continue
        # Existing records really have their own author/date. Never relabel the
        # migration clock as an original creation timestamp.
        scope = con.execute(
            "SELECT case_uuid FROM sync_cases WHERE case_id=?", (row["case_id"],)
        ).fetchone()
        key = (scope[0] if scope else str(row["case_id"])) + ":" + str(row["id"])
        con.execute(
            "UPDATE notes SET note_uuid=?,source_id=?,author_uuid=?,migrated_at=? WHERE id=?",
            (
                uuid.uuid5(uuid.NAMESPACE_OID, key).hex,
                "legacy-reverse-engineering",
                "",
                now(),
                row["id"],
            ),
        )


def may_manage(con, user, row):
    return (
        row["note_type"] == "user"
        and has_permission(user, "cases:update", con)
        and (
            user["role"] == "Administrator"
            or bool(row["author_uuid"])
            and user["user_uuid"] == row["author_uuid"]
        )
    )


def serialize(con, user, row):
    value = dict(row)
    value["html"] = (
        render_markdown(row["case_id"], row["body"])
        if row["note_type"] == "user"
        else ""
    )
    value["can_manage"] = may_manage(con, user, row)
    value["event_metadata"] = json.loads(value["event_metadata"])
    value["activity_link"] = None
    if row["note_type"] == "system":
        event = row["event_type"]
        tab = None
        if event.startswith("case."):
            tab = "workbench"
        elif event.startswith("tasks."):
            tab = "tasks"
        elif event.startswith("content.indicators.") and has_permission(
            user, "indicators:read", con
        ):
            tab = "indicators"
        elif (
            event.startswith("asset.")
            or event.startswith(("content.snort.", "content.yara."))
        ) and has_permission(user, "cases:assets", con):
            tab = "package"
        if tab:
            value["activity_link"] = {
                "href": f"/cases/{row['case_id']}?tab={tab}",
                "label": "View " + tab.title(),
            }

    return value


def sort_clock(value):
    try:
        date = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if date.tzinfo is None:
            date = date.replace(tzinfo=timezone.utc)
        return date.timestamp()
    except (ValueError, TypeError, AttributeError, OverflowError):
        return None


def listing(con, user, cid, args):
    readable(con, user, cid)
    kind = args.get("type", "all")
    order = args.get("order", "newest")
    if kind not in ("all", "user", "system") or order not in ("newest", "oldest"):
        abort(400, description="Invalid note filter or ordering.")
    try:
        limit, offset = int(args.get("limit", 50)), int(args.get("offset", 0))
        if not 1 <= limit <= 500 or offset < 0:
            raise ValueError()
    except (ValueError, TypeError):
        abort(400, description="Invalid pagination.")
    q = args.get("q", "").strip()
    if len(q) > 1000:
        abort(400)
    where, values = (
        "case_id=? AND (note_type='system' OR length(trim(body,char(9)||char(10)||char(13)||' '))>0)",
        [cid],
    )
    if q:
        where += " AND (instr(lower(body),lower(?))>0 OR instr(lower(title),lower(?))>0 OR instr(lower(coalesce(author,'')),lower(?))>0)"
        values.extend([q] * 3)
    counts = {"all": 0, "user": 0, "system": 0}
    for r in con.execute(
        f"SELECT note_type,count(*) FROM notes WHERE {where} GROUP BY note_type", values
    ):
        counts[r[0]] = r[1]
        counts["all"] += r[1]
    if kind != "all":
        where += " AND note_type=?"
        values.append(kind)
    direction = "DESC" if order == "newest" else "ASC"
    con.create_function("case_note_epoch", 1, sort_clock, deterministic=True)
    rows = con.execute(
        f"SELECT * FROM notes WHERE {where} ORDER BY case_note_epoch(created) {direction},id {direction} LIMIT ? OFFSET ?",
        values + [limit, offset],
    ).fetchall()
    return dict(
        notes=[serialize(con, user, r) for r in rows],
        counts=counts,
        total=counts[kind],
        limit=limit,
        offset=offset,
        editable=can_edit(con, user, case_state(con, cid)),
    )


def mutate(con, user, cid, value, nid=None, delete=False):
    editable(con, user, cid)
    row = None
    if nid is not None:
        row = con.execute(
            "SELECT * FROM notes WHERE id=? AND case_id=?", (nid, cid)
        ).fetchone()
        if row is None:
            abort(404)
        if not may_manage(con, user, row):
            abort(
                403,
                description="Only the author or an Administrator may manage a user note.",
            )
    # Compatibility fields remain accepted. Identity, clock and system fields do not.
    if set(value) - {"title", "body", "include_export", "request_id"}:
        abort(400, description="Unsupported note fields.")
    if delete:
        if row["include_export"]:
            pending(con, cid)
        con.execute("DELETE FROM notes WHERE id=? AND case_id=?", (nid, cid))
        audit(con, user, f"Deleted note {nid} from case {cid}")
        return None
    text = value.get("body", row["body"] if row else "")
    title = value.get("title", row["title"] if row else "")
    include = value.get("include_export", bool(row["include_export"]) if row else False)
    if (
        not isinstance(text, str)
        or not text.strip()
        or not isinstance(title, str)
        or len(title) > 200
        or not isinstance(include, bool)
    ):
        abort(400, description="A note must contain non-whitespace Markdown.")
    if row:
        if (text, title, int(include)) != (
            row["body"],
            row["title"],
            row["include_export"],
        ):
            con.execute(
                "UPDATE notes SET body=?,title=?,include_export=?,edited=? WHERE id=?",
                (text, title, int(include), now(), nid),
            )
            audit(con, user, f"Updated note {nid} in case {cid}")
    else:
        key = value.get("request_id")
        if key is not None and (
            not isinstance(key, str)
            or not __import__("re").fullmatch("[a-f0-9]{32}", key)
        ):
            abort(400)
        if key:
            previous = con.execute(
                "SELECT * FROM notes WHERE case_id=? AND source_id=? AND author_uuid=?",
                (cid, "request:" + key, user["user_uuid"]),
            ).fetchone()
            if previous:
                if (
                    previous["body"],
                    previous["title"],
                    previous["include_export"],
                ) != (text, title, int(include)):
                    abort(
                        409,
                        description="Request identity already used for another note.",
                    )
                return serialize(con, user, previous)
        cur = con.execute(
            "INSERT INTO notes(case_id,body,author,created,title,include_export,note_uuid,author_uuid,source_id) VALUES(?,?,?,?,?,?,?,?,?)",
            (
                cid,
                text,
                user["username"],
                now(),
                title,
                int(include),
                uuid.uuid4().hex,
                user["user_uuid"],
                "request:" + key if key else "",
            ),
        )
        nid = cur.lastrowid
        audit(con, user, f"Added note {nid} to case {cid}")
        con.execute(
            "DELETE FROM drafts WHERE case_id=? AND user_id=?", (cid, user["id"])
        )
    if include or row and row["include_export"]:
        pending(con, cid)
    return serialize(
        con, user, con.execute("SELECT * FROM notes WHERE id=?", (nid,)).fetchone()
    )


def pending(con, cid):
    con.execute(
        "INSERT OR REPLACE INTO readiness(case_id,category,status,reason) VALUES(?,'reports','Pending','Content changed; review this category.')",
        (cid,),
    )


def audit(con, user, message):
    con.execute(
        "INSERT INTO audit(actor,action,created) VALUES(?,?,?)",
        (user["username"], message, now()),
    )


def activity(con, cid, event_type, message, metadata=None, source_id=None):
    """Trusted internal writer; caller's transaction owns commit/rollback."""
    if (
        source_id
        and con.execute(
            "SELECT 1 FROM notes WHERE case_id=? AND note_type='system' AND source_id=?",
            (cid, source_id),
        ).fetchone()
    ):
        return
    user = getattr(g, "user", None) if has_request_context() else None
    con.execute(
        "INSERT INTO notes(case_id,body,author,created,title,include_export,note_uuid,note_type,author_uuid,event_type,event_metadata,source_id) VALUES(?,?,?,?,?,0,?,'system',?,?,?,?)",
        (
            cid,
            message,
            user["username"] if user else "",
            now(),
            "",
            uuid.uuid4().hex,
            user["user_uuid"] if user else "",
            event_type,
            json.dumps(metadata or {}),
            source_id or uuid.uuid4().hex,
        ),
    )


def snapshot(con, cid):
    c = con.execute("SELECT stage,owner FROM cases WHERE id=?", (cid,)).fetchone()
    owner = con.execute(
        "SELECT username FROM users WHERE id=?", (c["owner"],)
    ).fetchone()
    state = dict(
        stage=c["stage"],
        owner=c["owner"],
        owner_name=owner[0] if owner else "Unassigned",
        groups={},
        content={},
        assets=sorted(
            r[0]
            for r in con.execute("SELECT path FROM artifacts WHERE case_id=?", (cid,))
        ),
    )
    for r in con.execute("SELECT id,name FROM task_groups WHERE case_id=?", (cid,)):
        state["groups"][r["id"]] = r["name"]
    if con.execute(
        "SELECT 1 FROM sqlite_master WHERE name='content_events'"
    ).fetchone():
        scope = con.execute(
            "SELECT case_uuid FROM sync_cases WHERE case_id=?", (cid,)
        ).fetchone()
        if scope:
            for r in con.execute(
                "SELECT kind,source_key FROM content_events WHERE scope='case' AND scope_id=? AND live=1",
                (scope[0],),
            ):
                state["content"].setdefault(r["kind"], []).append(r["source_key"])
    for values in state["content"].values():
        values.sort()
    return state


def baseline(con, cid):
    migrate(con, cid)
    con.execute(
        "INSERT OR REPLACE INTO case_activity_state VALUES(?,?)",
        (cid, json.dumps(snapshot(con, cid), sort_keys=True)),
    )


def collect(con, cid):
    if not con.execute(
        "SELECT 1 FROM sqlite_master WHERE name='case_activity_state'"
    ).fetchone():
        return
    current = snapshot(con, cid)
    old = con.execute(
        "SELECT snapshot FROM case_activity_state WHERE case_id=?", (cid,)
    ).fetchone()
    restoring = (
        con.execute("SELECT restoring FROM content_metrics_state WHERE id=1").fetchone()
        if con.execute(
            "SELECT 1 FROM sqlite_master WHERE name='content_metrics_state'"
        ).fetchone()
        else None
    )
    live = (
        has_request_context()
        and request.method in ("POST", "PUT", "PATCH", "DELETE")
        and not (restoring and restoring[0])
    )
    if live:
        if old is None:
            activity(con, cid, "case.created", "Case created.")
        else:
            before = json.loads(old[0])
            if before["stage"] != current["stage"]:
                from app import STAGES

                activity(
                    con,
                    cid,
                    "case.stage_changed",
                    f"Stage changed from {STAGES[before['stage']]} to {STAGES[current['stage']] }.",
                    {"from": before["stage"], "to": current["stage"]},
                )
            if before["owner"] != current["owner"]:
                activity(
                    con,
                    cid,
                    "case.owner_changed",
                    f"Assigned owner changed from {before['owner_name']} to {current['owner_name']}.",
                )
            for key, verb in ((current, "added"), (before, "removed")):
                other = before if verb == "added" else current
                for gid in key["groups"].keys() - other["groups"].keys():
                    activity(
                        con,
                        cid,
                        "tasks.collection_" + verb,
                        f"Task collection {key['groups'][gid]} {verb}.",
                        {"group_id": gid},
                    )
            a, b = set(before.get("assets", [])), set(current["assets"])
            for count, verb in ((len(b - a), "attached"), (len(a - b), "removed")):
                if count:
                    activity(
                        con,
                        cid,
                        "asset." + verb,
                        f"{count} Case assets {verb}.",
                        {"count": count},
                    )
            nouns = {
                "indicators": "indicator entries",
                "snort": "Snort signature files",
                "yara": "YARA signature files",
                "samples": "sample assets",
                "scripts": "script assets",
                "pdf": "PDF assets",
            }
            for kind, noun in nouns.items():
                a, b = set(before["content"].get(kind, [])), set(
                    current["content"].get(kind, [])
                )
                for count, verb in ((len(b - a), "added"), (len(a - b), "removed")):
                    if count:
                        activity(
                            con,
                            cid,
                            "content." + kind + "." + verb,
                            f"{count} {noun} {verb}.",
                            {"count": count, "kind": kind},
                        )
    baseline(con, cid)


def render_markdown(cid, text):
    from markdown_support import markdown_parser
    import html
    import re

    renderer = markdown_parser()

    def image(tokens, index, *args):
        token = tokens[index]
        source = token.attrGet("src") or ""
        if re.fullmatch(r"assets/report-image-[a-f0-9]{32}\.png", source):
            return (
                '<img src="/cases/'
                + str(cid)
                + "/report-images/"
                + source.split("/")[-1]
                + '" alt="'
                + html.escape(token.content, quote=True)
                + '">'
            )
        return "<span>" + html.escape(token.content) + "</span>"

    renderer.renderer.rules["image"] = image
    return renderer.render(text)


def register(app, db):
    from werkzeug.exceptions import HTTPException

    def notebook(cid, nid=None):
        try:
            if request.method == "GET":
                return listing(db(), g.user, cid, request.args)
            value = json.loads(request.form.get("payload", "{}"))
            if not isinstance(value, dict):
                abort(400)
            operation = value.pop("operation", "save")
            if operation not in ("save", "delete"):
                abort(400)
            return {
                "note": mutate(
                    db(), g.user, cid, value, nid, delete=operation == "delete"
                )
            }
        except (ValueError, TypeError):
            return {"error": "Invalid notebook request."}, 400
        except HTTPException as exc:
            return {"error": exc.description}, exc.code

    @app.post("/case-notebook/<int:cid>/preview")
    def case_notebook_preview(cid):
        readable(db(), g.user, cid)
        return {"html": render_markdown(cid, request.form.get("text", ""))}

    app.add_url_rule(
        "/case-notebook/<int:cid>", "case_notebook", notebook, methods=["GET", "POST"]
    )
    app.add_url_rule(
        "/case-notebook/<int:cid>/<int:nid>",
        "case_notebook_item",
        notebook,
        methods=["POST"],
    )


def merge_history(con, cid, notes):
    """Merge immutable activity when semantic Case content is already current."""
    columns = ["title", "body", "author", "created", "include_export", *FIELDS]
    for note in notes:
        if note.get("note_type") != "system":
            continue
        old = con.execute(
            "SELECT * FROM notes WHERE case_id=? AND note_uuid=?",
            (cid, note["note_uuid"]),
        ).fetchone()
        if old:
            if any(old[k] != note[k] for k in columns):
                raise ValueError("Conflicting Case activity identity.")
            continue
        con.execute(
            "INSERT INTO notes(case_id,"
            + ",".join(columns)
            + ") VALUES("
            + ",".join("?" for _ in range(len(columns) + 1))
            + ")",
            [cid] + [note[k] for k in columns],
        )
