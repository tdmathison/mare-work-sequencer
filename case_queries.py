"""Shared case inventory scope for the Board and authenticated metrics.

Both web pages use the existing session/forced-password gates. The Board has no
owner/role visibility predicate or soft-delete flag: all existing case rows are
eligible. Workflow locks control editing, not listing. Keep future visibility
changes here so date parsing, history joins and pagination cannot narrow inventory.
"""

CASE_RELATIONS = (
    "FROM cases c LEFT JOIN users cr ON cr.id=c.creator "
    "LEFT JOIN users ow ON ow.id=c.owner"
)
CASE_ELIGIBILITY = "1=1"
CASE_QUERY = (
    "SELECT DISTINCT c.*,COALESCE(cr.username,c.creator_username,'Unknown') AS creator_name,"
    "ow.username AS owner_name,ow.active AS owner_active,"
    "CASE WHEN c.stage IN (0,3) OR (c.owner_required=1 AND COALESCE(ow.active,0)=0) "
    "THEN 1 ELSE 0 END AS workspace_locked " + CASE_RELATIONS
)


def inventory(connection):
    return [
        dict(row)
        for row in connection.execute(
            "SELECT DISTINCT c.id,c.stage,c.created,c.creator,c.creator_username,c.owner "
            + CASE_RELATIONS
            + " WHERE "
            + CASE_ELIGIBILITY
        )
    ]


def inventory_total(connection):
    return connection.execute(
        "SELECT count(DISTINCT c.id) " + CASE_RELATIONS + " WHERE " + CASE_ELIGIBILITY
    ).fetchone()[0]
