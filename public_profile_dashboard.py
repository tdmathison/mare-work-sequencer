"""Bounded, explicitly allowlisted public research projections.

Profiles have no hidden/private flags and deletion is physical. Only cases in
stages 0–3 are eligible, matching both existing public walls. No association table,
private research text, attachment bytes or filesystem paths are read by this projection.
"""
from datetime import datetime, timezone
from profile_types import FAMILY

INVESTIGATION_SIZE = 3
LIBRARY_SIZE = 24

def projection_cte(spec):
    return f"""WITH eligible AS (
 SELECT f.id,substr(f.name,1,200) name,t.name tag,
 substr(f.short_description,1,1200) short_description,
 strftime('%Y-%m-%dT%H:%M:%SZ',f.updated_at) updated_at,
 julianday(f.updated_at) updated_jd,f.tag_id
 FROM {spec.table} f JOIN tags t ON t.id=f.tag_id
 WHERE substr(t.name,1,{len(spec.tag_prefix)})='{spec.tag_prefix}' AND length(t.name)>{len(spec.tag_prefix)}
), linked AS (
 SELECT ct.tag_id,count(DISTINCT c.id) linked_cases,
 count(DISTINCT CASE WHEN c.stage IN (1,2) THEN c.id END) in_progress
 FROM case_tags ct JOIN cases c ON c.id=ct.case_id
 WHERE c.stage BETWEEN 0 AND 3 GROUP BY ct.tag_id
), osint AS (
 SELECT {spec.foreign_key},count(*) osint_links FROM {spec.osint_table} GROUP BY {spec.foreign_key}
), reports AS (
 SELECT {spec.foreign_key},count(*) reports_collected FROM {spec.reports_table} GROUP BY {spec.foreign_key}
), projected AS (
 SELECT e.*,coalesce(l.linked_cases,0) linked_cases,
 coalesce(l.in_progress,0) in_progress,coalesce(o.osint_links,0) osint_links,
 coalesce(r.reports_collected,0) reports_collected
 FROM eligible e LEFT JOIN linked l ON l.tag_id=e.tag_id
 LEFT JOIN osint o ON o.{spec.foreign_key}=e.id LEFT JOIN reports r ON r.{spec.foreign_key}=e.id
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


def public_profile(row):
    return {key: row[key] for key in FIELDS} if row else None


def snapshot(connection, page=0, library_page=0, current=None, timezone_name="UTC", *, spec=FAMILY):
    current = current or datetime.now(timezone.utc)
    CTE = projection_cte(spec)
    connection.execute("SAVEPOINT public_profile_dashboard")
    try:
        metrics = dict(
            connection.execute(
                CTE
                + f"""SELECT count(*) tracked_{spec.key},
          count(CASE WHEN in_progress>0 THEN 1 END) {spec.key}_in_progress,
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

        active = pagination(page, metrics[f"{spec.key}_in_progress"], INVESTIGATION_SIZE)
        library = pagination(library_page, metrics[f"tracked_{spec.key}"], LIBRARY_SIZE)
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
        connection.execute("RELEASE public_profile_dashboard")
    return dict(
        updated_at=current.isoformat(),
        timezone=timezone_name,
        metrics=metrics,
        featured=public_profile(featured),
        investigations=[public_profile(r) for r in investigations],
        tracked=[public_profile(r) for r in tracked],
        pagination=active,
        library_pagination=library,
    )

