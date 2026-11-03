"""Authoritative package presence/applicability; no independent population flag."""

from pathlib import Path
import re
import json
import zipfile
from xml.etree import ElementTree
from mip import CATEGORIES, OPTIONAL_TEMPLATES, REPORT_TEMPLATE
from reporting import SECTIONS, current_report, is_backup

MIGRATION = "automatic-package-status-v1"
GENERATED = {
    "iocs/indicators.csv": "indicators",
    "iocs/indicators.stix.json": "indicators",
    "supporting/references.csv": "references",
}
TEXT = {
    ".md",
    ".txt",
    ".json",
    ".csv",
    ".yml",
    ".yaml",
    ".yar",
    ".sigma",
    ".py",
    ".sh",
    ".ps1",
    ".rules",
    ".yara",
}
EDITABLE = TEXT - {".rules", ".yara"}


def text_editable(path):
    if path.suffix.lower() not in EDITABLE or path.stat().st_size >= 1024 * 1024:
        return False
    try:
        return "\x00" not in path.read_text(encoding="utf-8")
    except (UnicodeError, OSError):
        return False


def meaningful(path):
    if (
        not path.is_file()
        or any(p.is_symlink() for p in (path, *path.parents))
        or path.stat().st_size == 0
    ):
        return False
    if path.suffix.lower() == ".docx":
        # Recognize empty Word templates without treating presence as quality review.
        try:
            with zipfile.ZipFile(path) as archive:
                if archive.getinfo("word/document.xml").file_size > 2 * 1024 * 1024:
                    return True
                document = ElementTree.fromstring(archive.read("word/document.xml"))
            from reporting import TOKENS

            labels = set(TOKENS.values()) | {"Malware Analysis Report"}
            paragraphs = [
                "".join(p.itertext()).strip()
                for p in document.iter(
                    "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}p"
                )
            ]
            return any(
                value
                and value not in labels
                and not (value.startswith("{{") and value.endswith("}}"))
                for value in paragraphs
            )
        except (
            OSError,
            ValueError,
            KeyError,
            zipfile.BadZipFile,
            ElementTree.ParseError,
        ):
            # Unknown/binary formats remain artifacts; presence is not validation.
            return True
    if path.suffix.lower() not in TEXT:
        return True
    if path.stat().st_size > 2 * 1024 * 1024:
        return True
    value = path.read_text(errors="replace").strip()
    if path.suffix.lower() == ".json":
        try:
            if json.loads(value) in ({}, [], None, ""):
                return False
        except ValueError:
            pass
    if not value or value in {
        v.strip() for v in (*OPTIONAL_TEMPLATES.values(), REPORT_TEMPLATE)
    }:
        return False
    if path.suffix.lower() == ".md":
        # Headings, table headings/separators and placeholder prompts are scaffolds.
        lines = [line.strip() for line in value.splitlines() if line.strip()]
        lines = [
            line
            for index, line in enumerate(lines)
            if not (
                index + 1 < len(lines)
                and re.fullmatch(r"[| :\-]+", lines[index + 1])
                and "|" in lines[index + 1]
            )
        ]
        value = "\n".join(
            line
            for line in lines
            if not line.startswith("#")
            and not (line.startswith("[") and line.endswith("]"))
            and not re.fullmatch(r"[| :\-]+", line)
            and line
            not in (
                "| Technique ID | Technique | Evidence |",
                "| Behavior ID | Behavior | Evidence |",
            )
        )
    return bool(value.strip())


def inventory(con, record, root):
    """One logical item per artifact or generated record group; no internal editors."""
    from indicators import load_table
    from references import load_references

    cid = record["id"]
    root = Path(root)
    counts = {key: 0 for key in CATEGORIES}
    rows = []

    def add(name, section, kind, path=None, owner=None, count=1, updated=None):
        rows.append(
            dict(
                name=name,
                section=section,
                type=kind,
                path=path,
                owner=owner,
                count=count,
                updated=updated,
                editable=bool(
                    path
                    and not owner
                    and section != "samples"
                    and text_editable(root / path)
                ),
            )
        )
        counts[section] += count

    indicators = sum(
        bool(len(row) > 1 and row[1].strip())
        for s in load_table(lambda: con, cid)["sections"]
        for row in s["rows"]
    )
    references = sum(
        bool(row and row[0].strip())
        for row in load_references(lambda: con, cid)["rows"]
    )
    if indicators:
        add(
            "Saved indicators",
            "iocs",
            "Generated",
            path="iocs/indicators.csv",
            owner="indicators",
            count=indicators,
        )
    if references:
        add(
            "Saved reference links",
            "supporting",
            "Generated",
            path="supporting/references.csv",
            owner="references",
            count=references,
        )
    manual = root / "reports/sections"
    narratives = [manual / (key + ".md") for key in SECTIONS]
    narratives = [
        (
            manual / "threat_overview.md"
            if p.name == "key_findings.md" and not p.exists()
            else p
        )
        for p in narratives
    ]
    # Internal report sources stay editable only in Report, never as Package files.
    narrative_count = sum(meaningful(p) for p in narratives)
    if narrative_count:
        add(
            "Saved report narrative",
            "reports",
            "Generated",
            owner="report",
            count=narrative_count,
        )
    from standard_package import raw_file

    current = current_report(record, root)
    for path in sorted(root.rglob("*")) if root.is_dir() else []:
        rel = path.relative_to(root).as_posix()
        if (
            not (raw_file(rel, True) or rel.startswith("samples/"))
            or not path.is_file()
            or any(p.is_symlink() for p in (path, *path.parents))
            or is_backup(rel)
        ):
            continue
        if rel in GENERATED or rel.startswith("reports/sections/"):
            continue
        qualifies = meaningful(path)
        if not qualifies and (
            rel in OPTIONAL_TEMPLATES or rel == "reports/malware-analysis-report.md"
        ):
            continue
        section = rel.split("/")[0]
        if section not in counts:
            continue
        if rel in (
            "reports/malware-analysis-report.md",
            "reports/executive-summary.md",
        ):
            add(path.name, section, "Generated", owner="report")
            continue
        owner = (
            "report"
            if rel == current or rel == Path(current).with_suffix(".pdf").as_posix()
            else (
                "report"
                if rel in ("mappings/mitre-attack.md", "mappings/mitre-mbc.md")
                else None
            )
        )
        add(
            path.name,
            section,
            (
                "Generated"
                if owner
                else (
                    "Sample archive"
                    if section == "samples"
                    else path.suffix.lower().lstrip(".") or "File"
                )
            ),
            rel,
            owner,
            count=int(
                qualifies and (section != "samples" or path.suffix.lower() == ".zip")
            ),
            updated=path.stat().st_mtime,
        )
    return counts, rows


def states(con, record, root):
    counts, _ = inventory(con, record, root)
    saved = {
        r["category"]: dict(r)
        for r in con.execute("SELECT * FROM readiness WHERE case_id=?", (record["id"],))
    }
    result = []
    for category, label in CATEGORIES.items():
        row = saved.get(category, {})
        status = (
            "Populated"
            if counts[category]
            else "Not applicable" if row.get("status") == "Not applicable" else "Empty"
        )
        result.append(
            dict(
                category=category,
                label=label,
                status=status,
                legacy_status="Pending" if status == "Empty" else status,
                reason=row.get("reason", "") if status == "Not applicable" else "",
                count=counts[category],
            )
        )
    return result


def normalize(con, record, root, *, events=False):
    before = {
        r["category"]: r["status"]
        for r in con.execute("SELECT * FROM readiness WHERE case_id=?", (record["id"],))
    }
    cleared = []
    for row in states(con, record, root):
        if row["status"] != "Not applicable":
            con.execute(
                "DELETE FROM readiness WHERE case_id=? AND category=?",
                (record["id"], row["category"]),
            )
        if (
            before.get(row["category"]) == "Not applicable"
            and row["status"] == "Populated"
        ):
            cleared.append(row["label"])
            if events:
                from case_notes import activity

                activity(
                    con,
                    record["id"],
                    "package.applicability.cleared",
                    row["label"] + ": content added; Not applicable cleared.",
                    {"category": row["category"]},
                )
                from flask import g, has_request_context

                if has_request_context() and getattr(g, "user", None):
                    from app import audit

                    audit(
                        "Package "
                        + row["category"]
                        + ": Not applicable cleared after content was saved"
                    )
    return cleared


def initialize(con, data_root):
    data_root = Path(data_root).resolve()
    if con.execute(
        "SELECT 1 FROM schema_migrations WHERE name=?", (MIGRATION,)
    ).fetchone():
        return
    for record in con.execute("SELECT * FROM cases").fetchall():
        normalize(con, record, Path(data_root) / "cases" / str(record["id"]) / "mip")
    con.execute("INSERT OR IGNORE INTO schema_migrations VALUES(?)", (MIGRATION,))
    con.commit()


def applicability(con, record, root, category, status, reason=""):
    if (
        not isinstance(category, str)
        or category not in CATEGORIES
        or status not in ("Empty", "Not applicable")
    ):
        raise ValueError(
            "Population is automatic. Set status to Empty or Not applicable only."
        )
    if (
        status == "Not applicable"
        and next(r for r in states(con, record, root) if r["category"] == category)[
            "count"
        ]
    ):
        raise FileExistsError("A populated section cannot be marked Not applicable.")
    existing = con.execute(
        "SELECT status,reason FROM readiness WHERE case_id=? AND category=?",
        (record["id"], category),
    ).fetchone()
    reason = reason.strip() or "No content expected."
    if len(reason) > 2000:
        raise ValueError("Applicability reason must be at most 2,000 characters.")
    if status == "Not applicable":
        con.execute(
            "INSERT OR REPLACE INTO readiness VALUES(?,?,?,?)",
            (record["id"], category, status, reason),
        )
    else:
        con.execute(
            "DELETE FROM readiness WHERE case_id=? AND category=?",
            (record["id"], category),
        )
    changed = (not existing and status == "Not applicable") or (
        existing and (status == "Empty" or existing["reason"] != reason)
    )
    if changed:
        from case_notes import activity

        activity(
            con,
            record["id"],
            "package.applicability",
            CATEGORIES[category] + ": " + status + ".",
            {
                "category": category,
                "status": status,
                "reason": reason if status == "Not applicable" else "",
            },
        )
    return bool(changed)


def carriers(con, cid, *, existing=()):
    """Current derived CSV bytes, shared by downloads and Standard export plans."""
    import csv
    import io
    from indicators import load_table, indicator_csv
    from references import load_references

    table = load_table(lambda: con, cid)
    refs = load_references(lambda: con, cid)
    result = {}
    if "iocs/indicators.csv" in existing or any(
        len(row) > 1 and row[1].strip()
        for section in table["sections"]
        for row in section["rows"]
    ):
        result["iocs/indicators.csv"] = indicator_csv(table).encode("utf-8")
    if "supporting/references.csv" in existing or any(
        row and row[0].strip() for row in refs["rows"]
    ):
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(refs["columns"])
        writer.writerows(refs["rows"])
        result["supporting/references.csv"] = output.getvalue().encode("utf-8")
    return result
