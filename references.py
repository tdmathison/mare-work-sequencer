"""Analyst-maintained reference links used by the manual Word generator."""
import csv,io,json
from flask import request
COLUMNS=['Link','Description']
def load_references(db,cid):
    row=db().execute('SELECT * FROM reference_tables WHERE case_id=?',(cid,)).fetchone()
    return {'columns':COLUMNS,'rows':json.loads(row['rows']),'revision':row['revision']} if row else {'columns':COLUMNS,'rows':[],'revision':0}

def register_references(app,db,case,ensure_package,mark_pending,audit):
    with app.app_context():
        db().execute('CREATE TABLE IF NOT EXISTS reference_tables(case_id INTEGER PRIMARY KEY REFERENCES cases(id),rows TEXT NOT NULL,revision INTEGER NOT NULL)');db().commit()
    @app.get('/cases/<int:cid>/references')
    def references_data(cid):case(cid);return load_references(db,cid)
    @app.post('/cases/<int:cid>/references')
    def references_save(cid):
        case(cid)
        try:
            rows=json.loads(request.form['rows']);revision=int(request.form['revision'])
            if not isinstance(rows,list) or len(rows)>10000 or any(not isinstance(row,list) or len(row)!=2 or any(not isinstance(value,str) or len(value)>4000 for value in row) for row in rows):raise ValueError('Use two text cells per row, at most 4,000 characters per cell and 10,000 rows.')
            with db():
                db().execute('BEGIN IMMEDIATE')
                if case(cid)['stage'] not in (1,2):raise ValueError('Start analysis or reopen the case before editing references.')
                if revision!=load_references(db,cid)['revision']:raise ValueError('References changed in another session. Reload before saving.')
                if request.form.get('automatic')=='1' and rows==load_references(db,cid)['rows']:return load_references(db,cid)
                db().execute('INSERT OR REPLACE INTO reference_tables VALUES(?,?,?)',(cid,json.dumps(rows),revision+1))
            buffer=io.StringIO(newline='');writer=csv.writer(buffer);writer.writerow(COLUMNS);writer.writerows(rows)
            (ensure_package(cid)/'supporting/references.csv').write_text(buffer.getvalue())
            mark_pending(cid,'supporting/references.csv');mark_pending(cid,'reports/sections')
            audit(f'Updated references for case {cid}')
            return load_references(db,cid)
        except (ValueError,KeyError,TypeError) as exc:return {'error':str(exc)},409
