"""Isolated, disposable public-family dashboard browser fixture."""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
if not os.environ.get("MARE_FAMILY_WALL_TEST") or not os.environ.get("MARE_DATA_DIR"):
    raise RuntimeError("An isolated data directory is required")
from app import app, db, now
from tagging import create

with app.app_context():
    for i in range(33):
        tid = create(db(), "MAL_" + ("LONG_TAG_" * 12 if i == 0 else "") + str(i))[0]
        fid = f"{i:08x}-0000-4000-8000-000000000000"
        db().execute(
            """INSERT INTO malware_families(id,name,tag_id,short_description,long_description,
          attribution_notes,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)""",
            (
                fid,
                (
                    ("<img src=x onerror=alert(1)> " + ("Long family name " * 8))[:200]
                    if i == 0
                    else f"Research family {i:02}"
                ),
                tid,
                "Short research description. " * 80,
                "PRIVATE LONG",
                "PRIVATE ATTRIBUTION",
                now(),
                "2026-10-01T12:00:00Z",
            ),
        )
        if i < 8:
            cid = (
                db()
                .execute(
                    "INSERT INTO cases(number,name,stage,created) VALUES(?,?,?,?)",
                    (str(i), "PRIVATE CASE", 1 if i % 2 else 2, now()),
                )
                .lastrowid
            )
            db().execute(
                "INSERT INTO case_tags(case_id,tag_id,assigned_at) VALUES(?,?,?)",
                (cid, tid, now()),
            )
    db().commit()
app.run(host="127.0.0.1", port=8798, use_reloader=False)
