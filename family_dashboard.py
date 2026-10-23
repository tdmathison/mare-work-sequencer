"""Anonymous family-library projection: never serialize internal profiles or files."""

from datetime import datetime, timezone
from flask import abort, jsonify, render_template, request

INVESTIGATION_SIZE = 3
LIBRARY_SIZE = 24
# Families have no private/hidden flag. Deletion is physical. Match the public
# Cases dashboard's stage eligibility, including unassigned cases. Stable FK
# relationships, never names or MAL_ prefix matching, determine linked cases.
CTE = """WITH eligible AS (
 SELECT f.id,substr(f.name,1,200) name,t.name tag,
 substr(f.short_description,1,1200) short_description,
 strftime('%Y-%m-%dT%H:%M:%SZ',f.updated_at) updated_at,
 julianday(f.updated_at) updated_jd,f.tag_id
 FROM malware_families f JOIN tags t ON t.id=f.tag_id
 WHERE substr(t.name,1,4)='MAL_' AND length(t.name)>4
), linked AS (
 SELECT ct.tag_id,count(DISTINCT c.id) linked_cases,
 count(DISTINCT CASE WHEN c.stage IN (1,2) THEN c.id END) in_progress
 FROM case_tags ct JOIN cases c ON c.id=ct.case_id
 WHERE c.stage BETWEEN 0 AND 3 GROUP BY ct.tag_id
), osint AS (
 SELECT family_id,count(*) osint_links FROM family_osint GROUP BY family_id
), reports AS (
 SELECT family_id,count(*) reports_collected FROM family_reports GROUP BY family_id
), projected AS (
 SELECT e.*,coalesce(l.linked_cases,0) linked_cases,
 coalesce(l.in_progress,0) in_progress,coalesce(o.osint_links,0) osint_links,
 coalesce(r.reports_collected,0) reports_collected
 FROM eligible e LEFT JOIN linked l ON l.tag_id=e.tag_id
 LEFT JOIN osint o ON o.family_id=e.id LEFT JOIN reports r ON r.family_id=e.id
) """
FIELDS = (
    "name",
    "tag",
    "short_description",
    "updated_at",
    "linked_cases",
    "in_progress",
    "osint_links",
    "reports_collected",
)


def public_family(row):
    return {key: row[key] for key in FIELDS} if row else None


def snapshot(connection, page=0, library_page=0, current=None, timezone_name="UTC"):
    current = current or datetime.now(timezone.utc)
    connection.execute("SAVEPOINT public_family_dashboard")
    try:
        metrics = dict(
            connection.execute(
                CTE
                + """SELECT count(*) tracked_families,
          count(CASE WHEN in_progress>0 THEN 1 END) families_in_progress,
          coalesce(sum(reports_collected),0) reports_collected,
          (SELECT count(DISTINCT c.id) FROM cases c JOIN case_tags ct ON ct.case_id=c.id
           JOIN eligible e ON e.tag_id=ct.tag_id WHERE c.stage BETWEEN 0 AND 3) unique_linked_cases
          FROM projected"""
            ).fetchone()
        )

        def pagination(number, total, size):
            pages = max(1, (total + size - 1) // size)
            return dict(
                page=min(max(number, 0), pages - 1),
                pages=pages,
                total=total,
                page_size=size,
            )

        active = pagination(page, metrics["families_in_progress"], INVESTIGATION_SIZE)
        library = pagination(library_page, metrics["tracked_families"], LIBRARY_SIZE)
        featured = connection.execute(
            CTE
            + """SELECT * FROM projected
          ORDER BY (in_progress>0) DESC,updated_jd DESC,id ASC LIMIT 1"""
        ).fetchone()
        investigations = connection.execute(
            CTE
            + """SELECT * FROM projected WHERE in_progress>0
          ORDER BY in_progress DESC,updated_jd DESC,id ASC LIMIT ? OFFSET ?""",
            (INVESTIGATION_SIZE, active["page"] * INVESTIGATION_SIZE),
        ).fetchall()
        tracked = connection.execute(
            CTE
            + """SELECT * FROM projected
          ORDER BY name COLLATE NOCASE,id ASC LIMIT ? OFFSET ?""",
            (LIBRARY_SIZE, library["page"] * LIBRARY_SIZE),
        ).fetchall()
    finally:
        connection.execute("RELEASE public_family_dashboard")
    return dict(
        updated_at=current.isoformat(),
        timezone=timezone_name,
        metrics=metrics,
        featured=public_family(featured),
        investigations=[public_family(r) for r in investigations],
        tracked=[public_family(r) for r in tracked],
        pagination=active,
        library_pagination=library,
    )


def register_family_dashboard(app, db):
    @app.get("/dashboards/malware-families")
    def family_dashboard():
        return render_template("family_dashboard.html")

    @app.get("/dashboards/malware-families/data")
    def family_dashboard_data():
        try:
            page = int(request.args.get("page", "0"))
            library_page = int(request.args.get("library_page", "0"))
            if not 0 <= page <= 1000000 or not 0 <= library_page <= 1000000:
                raise ValueError()
        except ValueError:
            abort(400)
        response = jsonify(
            snapshot(
                db(), page, library_page, timezone_name=app.config["DISPLAY_TIMEZONE"]
            )
        )
        response.headers["Cache-Control"] = "no-store"
        return response
