"""Explicit preview/apply steps for existing archive-format regression tests."""
import json
from app import app, db


def apply_preview(client, response, csrf):
    if response.status_code==302 and response.location and '/import-export/review/' in response.location:
        operation=response.location.rsplit('/',1)[-1]
        with app.app_context():
            plan=json.loads(db().execute('SELECT plan FROM sync_imports WHERE id=?',(operation,)).fetchone()[0])
        decisions={f'decision-{index}':'new' for index,item in enumerate(plan['items']) if item['preview']['classification']=='review'}
        return client.post('/import-export/apply/'+operation,data={'csrf':csrf,**decisions})
    return response


def other_destination():
    """Model unrelated preexisting destination cases; titles are NOT identities."""
    with app.app_context():
        db().execute('DELETE FROM sync_cases')
        service=app.extensions['case_sync']
        for row in db().execute('SELECT id FROM cases').fetchall():service.reconcile(row['id'])
        db().commit()
