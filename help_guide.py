"""Authenticated, administrator-managed global Help guide and recovery migration."""

import json
import uuid
from datetime import datetime, timezone
from urllib.parse import urlsplit
from flask import g, request, render_template
from markdown_support import markdown_parser

DEFAULT_INTRO = "MARE Work Sequencer organizes malware investigations, tracks intelligence, and helps analysts prepare consistent MIP deliverables."
TABLE = "help_guide"


def initialize(con):
    con.execute(
        "CREATE TABLE IF NOT EXISTS help_guide(id INTEGER PRIMARY KEY CHECK(id=1), revision INTEGER NOT NULL, content TEXT NOT NULL)"
    )
    con.commit()


def read(con):
    row = con.execute("SELECT revision,content FROM help_guide WHERE id=1").fetchone()
    return (
        dict(json.loads(row[1]), revision=row[0])
        if row
        else dict(
            introduction=DEFAULT_INTRO,
            sops=[],
            faqs=[],
            revision=0,
            updated_at=None,
            updated_by=None,
        )
    )


def render(text):
    parser = markdown_parser()
    # Help never fetches embedded remote content or exposes Case image assets.
    from html import escape

    parser.renderer.rules["image"] = lambda tokens, index, *args: escape(
        tokens[index].content
    )
    return parser.render(text)


def public(con):
    doc = read(con)
    validate_stored(doc)
    for faq in doc["faqs"]:
        faq["html"] = render(faq["answer"])
    return doc


def validate_stored(doc):
    """Validate recovered content before it can become browser navigation/HTML."""
    try:
        text(doc["introduction"], "Introduction", 2000)
        if "\n" in doc["introduction"] or "\r" in doc["introduction"]:
            raise ValueError("The Help introduction must be one paragraph.")
        for kind in ("sops", "faqs"):
            entries = doc[kind]
            if not isinstance(entries, list) or len(entries) > 100:
                raise ValueError("Invalid Help section.")
            seen = set()
            for index, entry in enumerate(entries):
                key = entry["id"]
                if (
                    uuid.UUID(key).hex != key
                    or key in seen
                    or entry["position"] != index
                ):
                    raise ValueError("Invalid Help identity or ordering.")
                seen.add(key)
                if kind == "sops":
                    text(entry["title"], "SOP title", 200)
                    safe_url(entry["url"])
                else:
                    text(entry["question"], "FAQ question", 300)
                    text(entry["answer"], "FAQ answer", 20000)
        if len(json.dumps(doc).encode()) > 2 * 1024 * 1024:
            raise ValueError("Help content is too large.")
    except (KeyError, TypeError, AttributeError) as error:
        raise ValueError("Invalid saved Help content.") from error


def text(value, label, maximum):
    if (
        not isinstance(value, str)
        or not value.strip()
        or len(value) > maximum
        or "\x00" in value
    ):
        raise ValueError(
            f"{label} is required and must be at most {maximum:,} characters."
        )
    return value.strip()


def safe_url(value):
    value = text(value, "SOP URL", 4096)
    try:
        url = urlsplit(value)
        if (
            url.scheme != "https"
            or not url.hostname
            or url.username is not None
            or url.password is not None
            or any(c.isspace() or ord(c) < 32 or ord(c) == 127 for c in value)
            or "\\" in value
        ):
            raise ValueError()
        url.port
    except ValueError:
        raise ValueError(
            "Use an absolute HTTPS SOP URL without embedded credentials or whitespace."
        ) from None
    return value


def save(con, user, incoming, audit):
    if user["role"] != "Administrator":
        raise PermissionError("Only administrators can manage Help.")
    if not isinstance(incoming, dict):
        raise ValueError("Expected a Help document.")
    revision = incoming.get("revision")
    if not isinstance(revision, int) or isinstance(revision, bool) or revision < 0:
        raise ValueError("A valid Help revision is required.")
    previous = read(con)
    stamp = datetime.now(timezone.utc).isoformat(timespec="microseconds")
    actor = user["user_uuid"]
    result = dict(
        introduction=text(incoming.get("introduction"), "Introduction", 2000),
        updated_at=stamp,
        updated_by=actor,
    )
    if "\n" in result["introduction"] or "\r" in result["introduction"]:
        raise ValueError("Keep the introduction to one paragraph.")
    for kind in ("sops", "faqs"):
        records = incoming.get(kind)
        if not isinstance(records, list) or len(records) > 100:
            raise ValueError("Provide at most 100 entries per section.")
        old = {item["id"]: item for item in previous[kind]}
        seen = set()
        result[kind] = []
        for position, item in enumerate(records):
            if not isinstance(item, dict):
                raise ValueError("Invalid Help entry.")
            key = item.get("id") or uuid.uuid4().hex
            try:
                if uuid.UUID(key).hex != key or key in seen:
                    raise ValueError()
            except (ValueError, TypeError, AttributeError):
                raise ValueError(
                    "Help entry IDs must be unique canonical UUIDs."
                ) from None
            seen.add(key)
            fields = (
                dict(
                    title=text(item.get("title"), "SOP title", 200),
                    url=safe_url(item.get("url")),
                )
                if kind == "sops"
                else dict(
                    question=text(item.get("question"), "FAQ question", 300),
                    answer=text(item.get("answer"), "FAQ answer", 20000),
                )
            )
            prior = old.get(key)
            changed = (
                prior is None
                or prior["position"] != position
                or any(prior[k] != v for k, v in fields.items())
            )
            result[kind].append(
                dict(
                    fields,
                    id=key,
                    position=position,
                    created_at=prior["created_at"] if prior else stamp,
                    created_by=prior["created_by"] if prior else actor,
                    updated_at=stamp if changed else prior["updated_at"],
                    updated_by=actor if changed else prior["updated_by"],
                )
            )
    encoded = json.dumps(result, ensure_ascii=False)
    if len(encoded.encode()) > 1024 * 1024:
        raise ValueError("Help content must be at most 1 MiB.")
    # Compare-and-swap protects concurrent editors, including the first save.
    con.execute(
        "INSERT OR IGNORE INTO help_guide VALUES(1,0,?)",
        (
            json.dumps(
                dict(
                    introduction=DEFAULT_INTRO,
                    sops=[],
                    faqs=[],
                    updated_at=None,
                    updated_by=None,
                )
            ),
        ),
    )
    cursor = con.execute(
        "UPDATE help_guide SET revision=revision+1,content=? WHERE id=1 AND revision=?",
        (encoded, revision),
    )
    if cursor.rowcount != 1:
        con.rollback()
        return None
    audit("Updated global Help guide (introduction, SOP links and FAQs)")
    con.commit()
    return public(con)


def recover(con, preserved=None):
    """Additive upgrade; absent historical Help never erases destination content."""
    missing = not con.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='help_guide'"
    ).fetchone()
    initialize(con)
    if missing and preserved is not None:
        doc = dict(preserved)
        revision = doc.pop("revision")
        con.execute("INSERT INTO help_guide VALUES(1,?,?)", (revision, json.dumps(doc)))
        con.commit()
    validate_stored(read(con))
    return missing


def register(app, db, audit):
    with app.app_context():
        initialize(db())

    @app.get("/help")
    def help_page():
        return render_template(
            "help.html",
            guide=public(db()),
            can_manage=g.user["role"] == "Administrator",
        )

    @app.get("/help/content")
    def help_content():
        return public(db()), 200, {"Cache-Control": "private, no-store"}

    @app.post("/help/content")
    def help_save():
        if g.user["role"] != "Administrator":
            return {"error": "Only administrators can manage Help."}, 403
        if request.content_length and request.content_length > 2 * 1024 * 1024:
            return {"error": "Help content is too large."}, 413
        try:
            doc = json.loads(request.form.get("document", "null"))
            result = save(db(), g.user, doc, audit)
            if result is None:
                return {
                    "error": "Help changed since you opened it. Your edits are retained. Reload current content before saving again."
                }, 409
            return result
        except (ValueError, TypeError) as error:
            return {"error": str(error)}, 400

    @app.post("/help/preview")
    def help_preview():
        if g.user["role"] != "Administrator":
            return {"error": "Only administrators can preview Help edits."}, 403
        value = request.form.get("text", "")
        if len(value) > 20000:
            return {"error": "FAQ answers must be at most 20,000 characters."}, 400
        return {"html": render(value)}
