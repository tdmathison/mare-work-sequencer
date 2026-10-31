"""Reusable guidance and independent case copies. All writes use one transaction."""
import hashlib
import json
import uuid
from datetime import datetime, timezone
from flask import abort
from authorization import has_permission
from case_queries import CASE_QUERY

STATES = ('Not Started', 'In Progress', 'Completed')
MIGRATION = 'task-collections-v1'

def now(): return datetime.now(timezone.utc).isoformat(timespec='seconds')
def identity(): return uuid.uuid4().hex

def initialize(con):
    con.executescript('''
    CREATE TABLE IF NOT EXISTS task_collections(
      id TEXT PRIMARY KEY,name TEXT NOT NULL,description TEXT NOT NULL DEFAULT '',category TEXT NOT NULL DEFAULT '',
      tasks TEXT NOT NULL,revision INTEGER NOT NULL,creator_uuid TEXT,creator_name TEXT NOT NULL,created TEXT NOT NULL,updated TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS task_collection_revisions(
      collection_id TEXT NOT NULL,revision INTEGER NOT NULL,snapshot TEXT NOT NULL,PRIMARY KEY(collection_id,revision));
    CREATE TABLE IF NOT EXISTS task_groups(
      id TEXT NOT NULL,case_id INTEGER NOT NULL REFERENCES cases(id),name TEXT NOT NULL,
      source_collection_id TEXT,source_revision INTEGER,added TEXT NOT NULL,position INTEGER NOT NULL,PRIMARY KEY(case_id,id));
    CREATE TABLE IF NOT EXISTS task_collection_applications(
      case_id INTEGER NOT NULL,request_key TEXT NOT NULL,fingerprint TEXT NOT NULL,response TEXT NOT NULL,
      source_collection_id TEXT NOT NULL,template_ids TEXT NOT NULL,added TEXT NOT NULL,PRIMARY KEY(case_id,request_key));
    ''')
    columns={r[1] for r in con.execute('PRAGMA table_info(tasks)')}
    for column,definition in [('group_id','TEXT'),('source_template_id','TEXT'),('source_collection_id','TEXT'),('source_revision','INTEGER'),('position','INTEGER NOT NULL DEFAULT 0')]:
        if column not in columns: con.execute(f'ALTER TABLE tasks ADD COLUMN {column} {definition}')
    if not con.execute('SELECT 1 FROM schema_migrations WHERE name=?',(MIGRATION,)).fetchone():
        con.execute('UPDATE tasks SET position=id')
        for row in con.execute("SELECT DISTINCT role_name FROM role_permissions WHERE permission='cases:update'").fetchall():
            for permission in ('task_collections:create','task_collections:update','task_collections:delete'):
                con.execute('INSERT OR IGNORE INTO role_permissions VALUES(?,?)',(row[0],permission))
        con.execute('INSERT INTO schema_migrations VALUES(?)',(MIGRATION,))
    if con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='sync_dirty'").fetchone():
        for table in ('task_groups','task_collection_applications'):
            for event,reference in [('INSERT','NEW'),('UPDATE','NEW'),('DELETE','OLD')]:
                con.execute(f"CREATE TRIGGER IF NOT EXISTS sync_dirty_{table}_{event} AFTER {event} ON {table} BEGIN INSERT OR IGNORE INTO sync_dirty SELECT {reference}.case_id WHERE EXISTS(SELECT 1 FROM cases WHERE id={reference}.case_id); END")
    con.commit()
    from core_task_collections import install
    install(con)

def permission(con,user,action,record=None):
    if not user: abort(403)
    if record is not None and record['read_only']:
        abort(403,description='Core collections are read-only. Duplicate as a custom collection to customize them.')
    broad=has_permission(user,'task_collections:manage',con)
    if not broad and not has_permission(user,'task_collections:'+action,con): abort(403)
    if record is not None and not broad and record['creator_uuid']!=user['user_uuid']: abort(403)

def case_state(con,cid):
    row=con.execute(CASE_QUERY+' WHERE c.id=?',(cid,)).fetchone()
    if row is None:abort(404)
    return row

def can_edit(con,user,row):
    return has_permission(user,'cases:update',con) and not row['workspace_locked']

def editable(con,user,cid):
    if not has_permission(user,'cases:update',con):abort(403)
    row=case_state(con,cid)
    if row['workspace_locked']:
        abort(409,description='Start analysis or reopen the case to edit content.')
    return row

def readable(con,user,cid):
    if not has_permission(user,'cases:read',con):abort(403)
    if not con.execute('SELECT 1 FROM cases WHERE id=?',(cid,)).fetchone():abort(404)

def string(value,maximum,required=False):
    if not isinstance(value,str) or len(value)>maximum or required and not value.strip():abort(400,description='Invalid collection or task text.')
    return value.strip() if required else value

def definitions(values,previous=()):
    if not isinstance(values,list) or not 1<=len(values)<=500:abort(400,description='Provide between 1 and 500 task definitions.')
    allowed={t['id'] for t in previous};seen=set();result=[]
    for item in values:
        if not isinstance(item,dict):abort(400)
        tid=item.get('id') or identity()
        if not isinstance(tid,str) or tid in seen or (tid not in allowed and not __import__('re').fullmatch('[a-f0-9]{32}',tid)):abort(400)
        seen.add(tid)
        result.append(dict(id=tid,name=string(item.get('name'),200,True),description=string(item.get('description',''),20000)))
    return result

def get(con,cid):
    row=con.execute('SELECT * FROM task_collections WHERE id=?',(cid,)).fetchone()
    if row is None:abort(404)
    result=dict(row);result['tasks']=json.loads(result['tasks']);result['task_count']=len(result['tasks']);result.setdefault('origin','custom')
    from core_task_collections import reserved_ids
    result['read_only']=result['origin']=='core' or cid in reserved_ids()
    return result

def catalog(con,user):
    result=[]
    for row in con.execute('SELECT id FROM task_collections ORDER BY name COLLATE NOCASE,id'):
        item=get(con,row[0]);broad=has_permission(user,'task_collections:manage',con)
        item['can_edit']=not item['read_only'] and (broad or item['creator_uuid']==user['user_uuid'] and has_permission(user,'task_collections:update',con))
        item['can_delete']=not item['read_only'] and (broad or item['creator_uuid']==user['user_uuid'] and has_permission(user,'task_collections:delete',con))
        result.append(item)
    return result

def event(con,user,message):con.execute('INSERT INTO audit(actor,action,created) VALUES(?,?,?)',(user['username'],message,now()))

def save(con,user,value,cid=None):
    if not isinstance(value,dict):abort(400)
    with con:
        con.execute('BEGIN IMMEDIATE')
        old=get(con,cid) if cid else None
        permission(con,user,'update' if old else 'create',old)
        if old and (type(value.get('revision')) is not int or value.get('revision')!=old['revision']):abort(409,description='Collection changed. Reload before saving.')
        if value.get('origin','custom')!='custom' or value.get('read_only',False):abort(403,description='Core origin is managed by MWS, not collection CRUD.')
        tasks=definitions(value.get('tasks'),old['tasks'] if old else ())
        item=dict(id=cid or identity(),name=string(value.get('name'),200,True),description=string(value.get('description',''),20000),category=string(value.get('category',''),100),tasks=tasks,revision=old['revision']+1 if old else 1,creator_uuid=old['creator_uuid'] if old else user['user_uuid'],creator_name=old['creator_name'] if old else user['username'],created=old['created'] if old else now(),updated=now(),origin='custom')
        con.execute('INSERT INTO task_collections (id,name,description,category,tasks,revision,creator_uuid,creator_name,created,updated) VALUES(?,?,?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET name=excluded.name,description=excluded.description,category=excluded.category,tasks=excluded.tasks,revision=excluded.revision,updated=excluded.updated',tuple(json.dumps(item[k]) if k=='tasks' else item[k] for k in ('id','name','description','category','tasks','revision','creator_uuid','creator_name','created','updated')))
        con.execute('INSERT INTO task_collection_revisions VALUES(?,?,?)',(item['id'],item['revision'],json.dumps(item)))
        event(con,user,('Updated' if old else 'Created')+' global task collection '+item['id']+' revision '+str(item['revision']))
    return get(con,item['id'])

def duplicate(con,user,cid,value):
    permission(con,user,'create')
    source=get(con,cid)
    return save(con,user,dict(name=value.get('name',source['name'][:190]+' (custom)'),
        description=source['description'],category=source['category'],
        tasks=[dict(name=t['name'],description=t['description']) for t in source['tasks']]))

def remove(con,user,cid,revision):
    with con:
        con.execute('BEGIN IMMEDIATE');item=get(con,cid);permission(con,user,'delete',item)
        if revision!=item['revision']:abort(409,description='Collection changed. Reload before deleting.')
        con.execute('DELETE FROM task_collections WHERE id=?',(cid,))
        # Revision history and Case provenance deliberately outlive the template.
        event(con,user,'Deleted global task collection '+cid)

def selected(con,user,cid,ids):
    readable(con,user,cid)
    if not isinstance(ids,list) or not ids or len(ids)>500 or any(type(i)!=int for i in ids) or len(set(ids))!=len(ids):abort(400)
    rows={r['id']:r for r in con.execute('SELECT * FROM tasks WHERE case_id=?',(cid,))}
    if any(i not in rows for i in ids):abort(404)
    return [dict(name=rows[i]['title'],description=rows[i]['body'] or '') for i in ids]

def from_case(con,user,cid,value):
    # Copy definitions only; never copy state, assignment, provenance or image files.
    tasks=selected(con,user,cid,value.get('task_ids'))
    collection_id=value.get('collection_id')
    if collection_id is not None and not isinstance(collection_id,str):abort(400)
    if collection_id:
        if type(value.get('revision')) is not int:abort(409,description='Reload the target collection revision before appending.')
        old=get(con,collection_id)
        tasks=old['tasks']+tasks
        value={**old,**value}
    return save(con,user,{**value,'tasks':tasks},collection_id)

def apply(con,user,case_id,collection_id,value):
    if not isinstance(value,dict):abort(400)
    key=string(value.get('request_key'),100,True)
    if len(key)<16:abort(400,description='Provide a unique request key of at least 16 characters.')
    fingerprint=hashlib.sha256(json.dumps({'collection':collection_id,'payload':value},sort_keys=True).encode()).hexdigest()
    with con:
        con.execute('BEGIN IMMEDIATE');editable(con,user,case_id)
        replay=con.execute('SELECT * FROM task_collection_applications WHERE case_id=? AND request_key=?',(case_id,key)).fetchone()
        if replay:
            if replay['fingerprint']!=fingerprint:abort(409,description='Request key was already used for a different application.')
            return {**json.loads(replay['response']),'replayed':True}
        item=get(con,collection_id)
        if value.get('revision')!=item['revision']:abort(409,description='Collection changed. Refresh the preview before adding tasks.')
        ids=value.get('template_ids');available={t['id']:t for t in item['tasks']}
        if not isinstance(ids,list) or not ids or len(ids)>500 or any(not isinstance(i,str) for i in ids) or len(set(ids))!=len(ids) or any(i not in available for i in ids):abort(400)
        previous=con.execute('SELECT template_ids FROM task_collection_applications WHERE case_id=? AND source_collection_id=?',(case_id,collection_id)).fetchall()
        mode=value.get('mode','missing')
        if mode not in ('missing','copy'):abort(400)
        seen={i for row in previous for i in json.loads(row[0])}
        ids=[t['id'] for t in item['tasks'] if t['id'] in ids and (mode=='copy' or t['id'] not in seen)]
        if not ids:abort(409,description='All selected templates were previously added. Choose another copy explicitly.')
        gid=identity();added=now()
        pos=con.execute('SELECT coalesce(max(position),0)+1 FROM task_groups WHERE case_id=?',(case_id,)).fetchone()[0]
        con.execute('INSERT INTO task_groups VALUES(?,?,?,?,?,?,?)',(gid,case_id,item['name'],collection_id,item['revision'],added,pos))
        task_ids=[]
        for position,tid in enumerate(ids):
            template=available[tid]
            cursor=con.execute("INSERT INTO tasks(case_id,title,body,state,done,priority,created,group_id,source_template_id,source_collection_id,source_revision,position) VALUES(?,?,?,'Not Started',0,'Normal',?,?,?,?,?,?)",(case_id,template['name'],template['description'],added,gid,tid,collection_id,item['revision'],position))
            task_ids.append(cursor.lastrowid)
        source_fingerprint=hashlib.sha256(json.dumps({k:item[k] for k in ('id','revision','name','description','category','tasks')},sort_keys=True).encode()).hexdigest()
        result=dict(group_id=gid,task_ids=task_ids,count=len(ids),source_collection_id=collection_id,source_revision=item['revision'],source_fingerprint=source_fingerprint,source_tasks=[available[tid] for tid in ids],added=added)
        con.execute('INSERT INTO task_collection_applications VALUES(?,?,?,?,?,?,?)',(case_id,key,fingerprint,json.dumps(result),collection_id,json.dumps(ids),added))
        event(con,user,f'Applied task collection {collection_id} revision {item["revision"]} to case {case_id}; {len(ids)} tasks')
    return result

def workspace(con,user,cid):
    readable(con,user,cid)
    tasks=[dict(r) for r in con.execute('SELECT * FROM tasks WHERE case_id=? ORDER BY position,id',(cid,))]
    groups=[dict(r) for r in con.execute('SELECT * FROM task_groups WHERE case_id=? ORDER BY position,id',(cid,))]
    applications=[dict(r) for r in con.execute('SELECT source_collection_id,template_ids,added,response FROM task_collection_applications WHERE case_id=? ORDER BY added',(cid,))]
    sources={}
    for a in applications:
        response=json.loads(a.pop('response'));sources[response.get('group_id')]=response
        a['template_ids']=json.loads(a['template_ids'])
    for group in groups:
        source=sources.get(group['id'],{});group['source_fingerprint']=source.get('source_fingerprint','');group['source_tasks']=source.get('source_tasks',[])
    return dict(tasks=tasks,groups=groups,applications=applications,editable=can_edit(con,user,case_state(con,cid)))

def create_task(con,user,cid,value):
    with con:
        con.execute('BEGIN IMMEDIATE');editable(con,user,cid)
        title=string(value.get('title',value.get('name')),200,True)
        body=string(value.get('body',value.get('description','')),20000)
        priority=value.get('priority','Normal')
        if priority not in ('Low','Normal','High','Critical'):abort(400)
        position=con.execute('SELECT coalesce(max(position),-1)+1 FROM tasks WHERE case_id=? AND group_id IS NULL',(cid,)).fetchone()[0]
        cursor=con.execute("INSERT INTO tasks(case_id,title,body,priority,state,done,created,position) VALUES(?,?,?,?,'Not Started',0,?,?)",(cid,title,body,priority,now(),position))
        event(con,user,f'Added task to case {cid}')
        tid=cursor.lastrowid
    return dict(con.execute('SELECT * FROM tasks WHERE id=?',(tid,)).fetchone())

def mutate_task(con,user,cid,tid,value,delete=False):
    with con:
        con.execute('BEGIN IMMEDIATE');editable(con,user,cid)
        task=con.execute('SELECT * FROM tasks WHERE case_id=? AND id=?',(cid,tid)).fetchone()
        if task is None:abort(404)
        if delete:con.execute('DELETE FROM tasks WHERE id=?',(tid,))
        else:
            title=string(value.get('title',task['title']),200,True);body=string(value.get('body',value.get('description',task['body'] or '')),20000)
            state=value.get('state',task['state']);priority=value.get('priority',task['priority'])
            if state not in STATES or priority not in ('Low','Normal','High','Critical'):abort(400)
            con.execute('UPDATE tasks SET title=?,body=?,state=?,done=?,priority=? WHERE id=?',(title,body,state,int(state=='Completed'),priority,tid))
        event(con,user,('Deleted' if delete else 'Updated')+f' task {tid} in case {cid}')
    return dict(con.execute('SELECT * FROM tasks WHERE id=?',(tid,)).fetchone()) if not delete else None

def reorder(con,user,cid,gid,ids):
    if gid is not None and (not isinstance(gid,str) or not __import__('re').fullmatch('[a-f0-9]{32}',gid)):abort(400)
    with con:
        con.execute('BEGIN IMMEDIATE');editable(con,user,cid)
        if gid is not None and not con.execute('SELECT 1 FROM task_groups WHERE case_id=? AND id=?',(cid,gid)).fetchone():abort(404)
        existing={r[0] for r in con.execute('SELECT id FROM tasks WHERE case_id=? AND group_id IS ?',(cid,gid))}
        if not isinstance(ids,list) or any(type(i)!=int for i in ids) or len(set(ids))!=len(ids) or set(ids)!=existing:abort(409,description='Task group changed. Refresh before reordering.')
        for pos,tid in enumerate(ids):con.execute('UPDATE tasks SET position=? WHERE case_id=? AND id=?',(pos,cid,tid))
        event(con,user,f'Reordered case {cid} task group {gid or "custom"}')
