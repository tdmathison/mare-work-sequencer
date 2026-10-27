"""Owner-scoped, versioned Explorer configuration, never content snapshots."""
import json
import math
import re
import uuid
from datetime import datetime, timezone
from flask import abort, g, jsonify, request

ID=re.compile(r'(?:case:[1-9][0-9]{0,18}(?::(?:indicators|references|reports|files|images))?|(?:family|actor):[A-Za-z0-9-]{1,80})\Z')

def validate_config(value):
    if not isinstance(value,dict) or set(value)-{'version','query','types','contents','layout','positions','viewport','expanded','selected','focus','shared'}:raise ValueError('Unsupported view fields.')
    if value.get('version')!=1:raise ValueError('Unsupported saved-view version.')
    if len(json.dumps(value,allow_nan=False).encode())>1024*1024:raise ValueError('View exceeds 1 MiB.')
    def ids(items,maximum=2400):
        if not isinstance(items,list) or len(items)>maximum or any(not isinstance(x,str) or not ID.fullmatch(x) for x in items) or len(set(items))!=len(items):raise ValueError('Invalid object identifiers.')
    def point(p):
        if not isinstance(p,dict) or set(p)!={'x','y'} or any(type(n) not in (int,float) or not math.isfinite(n) or abs(n)>1e7 for n in p.values()):raise ValueError('Invalid coordinates.')
    if not isinstance(value.get('query'),str) or len(value['query'])>200 or type(value.get('contents')) is not bool:raise ValueError('Invalid filters.')
    if not isinstance(value.get('types'),list) or len(value['types'])>3 or any(t not in ('case','family','actor') for t in value['types']):raise ValueError('Invalid object types.')
    layout=value.get('layout',{})
    if not isinstance(layout,dict) or set(layout)!={'mode','direction','center','spacing','emphasis'} or layout['mode'] not in ('tree','radial','clusters') or layout['direction'] not in ('tb','lr') or layout['center'] not in ('selected','automatic') or layout['spacing'] not in ('compact','balanced','spacious') or type(layout['emphasis']) is not bool:raise ValueError('Invalid layout settings.')
    positions=value.get('positions');
    if not isinstance(positions,dict):raise ValueError('Invalid positions.')
    ids(list(positions));[point(p) for p in positions.values()]
    ids(value.get('selected'));ids(value.get('expanded'),400)
    if any(not re.fullmatch(r'case:[1-9][0-9]{0,18}',identity) for identity in value['expanded']):raise ValueError('Only Cases can be expanded.')
    viewport=value.get('viewport',{})
    if not isinstance(viewport,dict) or set(viewport)!={'zoom','pan'} or type(viewport['zoom']) not in (int,float) or not .005<=viewport['zoom']<=3:raise ValueError('Invalid viewport.')
    point(viewport['pan'])
    focus=value.get('focus')
    if focus is not None:
        if not isinstance(focus,dict) or set(focus)!={'id','depth'} or type(focus['depth']) is not int or not 1<=focus['depth']<=8:raise ValueError('Invalid focus.')
        ids([focus['id']],1)
        if focus['id'].count(':')!=1:raise ValueError('Focus requires an entity object.')
    shared=value.get('shared',{'enabled':False,'types':['md5','sha1','sha256','domain','ip','url'],'minimum':1})
    if not isinstance(shared,dict) or set(shared)!={'enabled','types','minimum'} or type(shared['enabled']) is not bool or type(shared['minimum']) is not int or not 1<=shared['minimum']<=100 or not isinstance(shared['types'],list) or len(shared['types'])>6 or any(t not in ('md5','sha1','sha256','domain','ip','url') for t in shared['types']):raise ValueError('Invalid shared-indicator settings.')
    if shared['enabled'] and not shared['types']:raise ValueError('Choose a supported indicator type.')
    return value

def initialize(connection):
    connection.executescript('''CREATE TABLE IF NOT EXISTS explorer_views(
     id TEXT PRIMARY KEY,owner_uuid TEXT NOT NULL REFERENCES users(user_uuid) ON DELETE CASCADE,
     name TEXT NOT NULL,description TEXT NOT NULL DEFAULT '',configuration TEXT NOT NULL,
     created_at TEXT NOT NULL,updated_at TEXT NOT NULL);
     CREATE INDEX IF NOT EXISTS explorer_views_owner ON explorer_views(owner_uuid,updated_at);
     INSERT OR IGNORE INTO schema_migrations VALUES('explorer-views-v1');''')
    connection.commit()

def register_views(app,db,require):
    with app.app_context():initialize(db())
    def owned(vid):
        require();row=db().execute('SELECT * FROM explorer_views WHERE id=? AND owner_uuid=?',(vid,g.user['user_uuid'])).fetchone()
        if not row:abort(404)
        return row
    def payload():
        name=request.form.get('name','').strip();description=request.form.get('description','').strip()
        if not 1<=len(name)<=120 or len(description)>1000:raise ValueError('Name must be 1–120 characters; description at most 1,000.')
        raw=request.form.get('configuration','')
        if len(raw)>1024*1024:raise ValueError('View exceeds 1 MiB.')
        config=validate_config(json.loads(raw))
        return name,description,json.dumps(config,allow_nan=False)
    @app.get('/data-explorer/views')
    def explorer_views():
        require();return jsonify(views=[dict(r) for r in db().execute('SELECT id,name,description,updated_at FROM explorer_views WHERE owner_uuid=? ORDER BY updated_at DESC,id',(g.user['user_uuid'],))]),200,{'Cache-Control':'private, no-store'}
    @app.get('/data-explorer/views/<vid>')
    def explorer_view(vid):
        row=dict(owned(vid))
        try:row['configuration']=validate_config(json.loads(row['configuration']))
        except (ValueError,TypeError,KeyError,RecursionError):return {'error':'Saved-view configuration is invalid or uses an unsupported schema version.'},409
        return jsonify(row),200,{'Cache-Control':'private, no-store'}
    @app.post('/data-explorer/views')
    def explorer_view_create():
        require()
        if db().execute('SELECT count(*) FROM explorer_views WHERE owner_uuid=?',(g.user['user_uuid'],)).fetchone()[0]>=100:abort(409,description='Limit of 100 saved views reached.')
        try:name,description,config=payload()
        except (ValueError,TypeError,KeyError,OverflowError,RecursionError):return {'error':'Invalid view name, description or configuration.'},400
        vid=str(uuid.uuid4());now=datetime.now(timezone.utc).isoformat()
        db().execute('INSERT INTO explorer_views VALUES(?,?,?,?,?,?,?)',(vid,g.user['user_uuid'],name,description,config,now,now));db().commit();return {'id':vid},201
    @app.post('/data-explorer/views/<vid>/update')
    def explorer_view_update(vid):
        owned(vid)
        try:name,description,config=payload()
        except (ValueError,TypeError,KeyError,OverflowError,RecursionError):return {'error':'Invalid view name, description or configuration.'},400
        db().execute('UPDATE explorer_views SET name=?,description=?,configuration=?,updated_at=? WHERE id=? AND owner_uuid=?',(name,description,config,datetime.now(timezone.utc).isoformat(),vid,g.user['user_uuid']));db().commit();return {'saved':True}
    @app.post('/data-explorer/views/<vid>/delete')
    def explorer_view_delete(vid):
        owned(vid);db().execute('DELETE FROM explorer_views WHERE id=? AND owner_uuid=?',(vid,g.user['user_uuid']));db().commit();return {'deleted':True}
