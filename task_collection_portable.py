"""Portable stable identities. Names never determine collection identity."""
import copy
import json
import re
from pathlib import Path
from werkzeug.exceptions import HTTPException
import task_collections as service

def export(con):
    rows=[]
    for record in con.execute('SELECT id FROM task_collections ORDER BY id'):
        item=service.get(con,record[0]);item.pop('task_count',None)
        item['revisions']=[json.loads(r[0]) for r in con.execute('SELECT snapshot FROM task_collection_revisions WHERE collection_id=? ORDER BY revision',(item['id'],))]
        rows.append(item)
    return rows

def validate(rows):
    if not isinstance(rows,list) or len(rows)>10000:raise ValueError('Invalid task collection library.')
    seen=set()
    for item in rows:
        if not isinstance(item,dict) or not re.fullmatch('[a-f0-9]{32}',str(item.get('id',''))) or item['id'] in seen:raise ValueError('Invalid or duplicate task collection identity.')
        seen.add(item['id'])
        versions=item.get('revisions')
        if not isinstance(versions,list) or not 1<=len(versions)<=10000:raise ValueError('Invalid collection revision history.')
        previous=0
        for record in [*versions,item]:
            if not isinstance(record,dict) or record.get('id')!=item['id'] or type(record.get('revision')) is not int or not 1<=record['revision']<2**31:raise ValueError('Invalid task collection revision.')
            try:
                service.string(record.get('name'),200,True);service.string(record.get('description'),20000);service.string(record.get('category'),100)
                if not isinstance(record.get('tasks'),list) or any(not isinstance(t,dict) or set(t)!={'id','name','description'} or not re.fullmatch('[a-f0-9]{32}',str(t.get('id',''))) for t in record['tasks']):raise ValueError('Invalid task template identities.')
                service.definitions(record['tasks'])
                for key in ('creator_name','created','updated'):service.string(record.get(key),200)
                if record.get('creator_uuid') is not None and not re.fullmatch('[a-f0-9]{32}',str(record['creator_uuid'])):raise ValueError('Invalid creator identity.')
            except HTTPException as error:raise ValueError('Invalid task collection data.') from error
        for record in versions:
            if record['revision']<=previous:raise ValueError('Collection revisions must be ordered and unique.')
            previous=record['revision']
        current={k:v for k,v in item.items() if k!='revisions'}
        if versions[-1]!=current:raise ValueError('Current collection does not match its final revision.')
    return rows

def mapped_creators(con,rows):
    rows=copy.deepcopy(rows)
    for item in rows:
        for record in [item,*item['revisions']]:
            match=con.execute('SELECT user_uuid FROM users WHERE username=?',(record['creator_name'],)).fetchone()
            record['creator_uuid']=match[0] if match else None
    return rows

def plan(con,rows,choices):
    validate(rows);rows=mapped_creators(con,rows);conflicts=[];records=[]
    for item in rows:
        local=con.execute('SELECT revision FROM task_collections WHERE id=?',(item['id'],)).fetchone()
        identical=False
        if local:
            existing=service.get(con,item['id']);existing.pop('task_count',None)
            history=[json.loads(r[0]) for r in con.execute('SELECT snapshot FROM task_collection_revisions WHERE collection_id=? ORDER BY revision',(item['id'],))]
            identical=existing=={k:v for k,v in item.items() if k!='revisions'} and history==item['revisions']
        key='task_collection:'+item['id'];choice=choices.get(key)
        if local and not identical and choice not in ('keep','replace'):
            conflicts.append(dict(key=key,label='Task collection '+item['name']+' has different content or revisions.',options=[['keep','Keep destination collection'],['replace','Replace with archive collection']]))
        records.append(dict(category='task_collections',identifier=item['id'],name=item['name'],description=item['description'],task_count=len(item['tasks']),revision=item['revision'],predicted_action='unchanged' if identical else 'skipped' if local and choice=='keep' else 'conflict' if local and choice not in ('replace','keep') else 'updated' if local else 'new',details='Independent Case copies will not be changed.'))
    return conflicts,records

def restore(con,user,directory,choices):
    path=Path(directory)/'task-collections.json'
    if not path.exists():return []
    rows=mapped_creators(con,validate(json.loads(path.read_text())));conflicts,records=plan(con,rows,choices)
    if conflicts:raise ValueError('Resolve task collection conflicts and refresh the preview.')
    if not rows:return []
    service.permission(con,user,'manage')
    with con:
        con.execute('BEGIN IMMEDIATE')
        for item,record in zip(rows,records):
            action=record['predicted_action']
            if action in ('unchanged','skipped'):continue
            # Match exact usernames, like the existing portable Case importer;
            # never trust a source numeric user ID. Unmapped creators remain unowned.
            owner_uuid=item['creator_uuid']
            con.execute('DELETE FROM task_collection_revisions WHERE collection_id=?',(item['id'],))
            con.execute('INSERT OR REPLACE INTO task_collections VALUES(?,?,?,?,?,?,?,?,?,?)',tuple(json.dumps(item[k]) if k=='tasks' else owner_uuid if k=='creator_uuid' else item[k] for k in ('id','name','description','category','tasks','revision','creator_uuid','creator_name','created','updated')))
            for revision in item['revisions']:con.execute('INSERT INTO task_collection_revisions VALUES(?,?,?)',(item['id'],revision['revision'],json.dumps(revision)))
        if rows:service.event(con,user,'Restored global task collections: '+str(len(rows)))
    for r in records:
        action=r.pop('predicted_action');r['action']={'new':'added','updated':'updated'}.get(action,action)
    return records


def validate_source_tasks(values):
    if not isinstance(values,list) or len(values)>500:raise ValueError('Invalid task source snapshot.')
    if values:
        try:
            if any(not isinstance(t,dict) or set(t)!={'id','name','description'} or not re.fullmatch('[a-f0-9]{32}',str(t.get('id',''))) for t in values):raise ValueError('Invalid task source definition.')
            service.definitions(values)
        except HTTPException as error:raise ValueError('Invalid task source definitions.') from error


def validate_database(con):
    """Complete snapshots preserve deleted-source history without requiring live sources."""
    tables={r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    required={'task_collections','task_collection_revisions','task_groups','task_collection_applications'}
    if not required & tables:return
    if not required<=tables:raise ValueError('Incomplete task collection schema.')
    if not con.execute('SELECT 1 FROM schema_migrations WHERE name=?',(service.MIGRATION,)).fetchone():raise ValueError('Missing task collection migration marker.')
    validate(export(con))
    for row in con.execute('SELECT * FROM task_collection_revisions'):
        snapshot=json.loads(row['snapshot'])
        if not isinstance(snapshot,dict) or snapshot.get('id')!=row['collection_id'] or snapshot.get('revision')!=row['revision']:raise ValueError('Task collection history identity mismatch.')
        validate([{**snapshot,'revisions':[snapshot]}])
    groups={}
    for row in con.execute('SELECT * FROM task_groups'):
        if not re.fullmatch('[a-f0-9]{32}',row['id']) or not re.fullmatch('[a-f0-9]{32}',row['source_collection_id'] or '') or type(row['source_revision']) is not int or row['source_revision']<1 or row['position']<0 or not isinstance(row['name'],str) or not row['name'].strip():raise ValueError('Invalid Case task group.')
        groups[(row['case_id'],row['id'])]=row
    for task in con.execute('SELECT * FROM tasks'):
        if task['group_id']:
            group=groups.get((task['case_id'],task['group_id']))
            if group is None or task['source_collection_id']!=group['source_collection_id'] or task['source_revision']!=group['source_revision'] or not re.fullmatch('[a-f0-9]{32}',task['source_template_id'] or ''):raise ValueError('Invalid Case task provenance.')
        if task['state'] not in service.STATES or task['position']<0:raise ValueError('Invalid Case task state or order.')
    for row in con.execute('SELECT * FROM task_collection_applications'):
        ids=json.loads(row['template_ids']);response=json.loads(row['response'])
        if isinstance(response,dict):
            validate_source_tasks(response.get('source_tasks',[]))
            if response.get('source_fingerprint') and not re.fullmatch('[a-f0-9]{64}',response['source_fingerprint']):raise ValueError('Invalid task source fingerprint.')
        if not isinstance(ids,list) or len(ids)>500 or any(not isinstance(i,str) or not re.fullmatch('[a-f0-9]{32}',i) for i in ids) or not isinstance(response,dict) or not re.fullmatch('[a-f0-9]{32}',response.get('group_id','')) or not con.execute('SELECT 1 FROM cases WHERE id=?',(row['case_id'],)).fetchone():raise ValueError('Invalid task application provenance.')
