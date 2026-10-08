import hashlib
import io
import json
import re
import secrets
import shutil
import sqlite3
import tempfile
import zipfile
from functools import wraps
from pathlib import Path

from flask import Blueprint, abort, render_template, g, get_flashed_messages, jsonify, redirect, request, send_file, session
from werkzeug.exceptions import HTTPException
from werkzeug.security import generate_password_hash
from werkzeug.utils import secure_filename

from authorization import PERMISSIONS, has_permission, role_records
from indicators import DEFAULT_COLUMNS, indicator_csv, load_table, validate_sections, validate_table
from mip import CATEGORIES, dated_title
from references import COLUMNS as REFERENCE_COLUMNS, load_references
from reporting import SECTIONS, TOKENS, current_report, is_backup


def register_api(app,db,run,case,package,ensure_package,now,audit,allocate_case_number,external_reference,sample_archive_password,mark_pending,readiness,review_issues,stages,safe_path,build_archive,report_helpers,asset_helpers,backup_helpers,metrics_data):
    with app.app_context():
        db().executescript('''
        CREATE TABLE IF NOT EXISTS api_tokens(
            id INTEGER PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            name TEXT NOT NULL,
            token_hash TEXT NOT NULL UNIQUE,
            token_prefix TEXT NOT NULL,
            created TEXT NOT NULL,
            last_used TEXT,
            revoked TEXT
        );
        CREATE INDEX IF NOT EXISTS api_tokens_user ON api_tokens(user_id,revoked);
        ''')
        if 'expires' not in {row[1] for row in db().execute('PRAGMA table_info(api_tokens)')}:db().execute('ALTER TABLE api_tokens ADD COLUMN expires TEXT')
        db().commit()

    api=Blueprint('api',__name__,url_prefix='/api/v1')

    @api.errorhandler(HTTPException)
    def api_http_error(error):
        return jsonify(error=error.description),error.code

    @api.errorhandler(Exception)
    def api_server_error(error):
        if isinstance(error,HTTPException):return api_http_error(error)
        app.logger.exception('API request failed')
        return jsonify(error='Internal server error.'),500

    def page():
        try:return max(1,min(int(request.args.get('limit','100')),500)),max(0,int(request.args.get('offset','0')))
        except ValueError:abort(400,description='limit and offset must be integers.')

    def web_result(response,ok='',status=200):
        # Reuses web handlers that report outcomes by flashing a message and redirecting.
        messages=get_flashed_messages();message=messages[-1] if messages else ''
        if getattr(response,'status_code',None) not in (301,302,303):return response
        if ok and message.startswith(ok):return jsonify(message=message),status
        return jsonify(error=message or 'Request failed.'),(409 if message.startswith('Wait for') else 400)

    def allowed(permission):
        return has_permission(g.user,permission,db())

    def require(permission):
        def decorate(function):
            @wraps(function)
            def wrapped(*args,**kwargs):
                required=permission.get(request.method) if isinstance(permission,dict) else permission
                if not required:return jsonify(error='Method not allowed.'),405
                if not allowed(required):return jsonify(error='Permission denied.',required_permission=required),403
                return function(*args,**kwargs)
            wrapped.permission=permission
            return wrapped
        return decorate

    def body():
        value=request.get_json(silent=True)
        if not isinstance(value,dict):abort(400,description='Request body must be a JSON object.')
        return value

    def user_data(user):
        return {'id':user['id'],'uuid':user['user_uuid'],'username':user['username'],'role':user['role'],'active':bool(user['active']),'forced_password_change':bool(user['forced'])}

    def role_permissions(name):
        return {row['permission'] for row in db().execute('SELECT permission FROM role_permissions WHERE role_name=?',(name,))}

    def can_assign_role(name):
        if allowed('roles:manage'):return True
        return role_permissions(name).issubset(role_permissions(g.user['role']))

    def editable_case(case_id):
        current=case(case_id)
        if current['owner_required'] and not current['owner_active']:abort(409,description='Assign an active owner before editing this case.')
        if current['stage'] in (0,3):abort(409,description='Start analysis or reopen this case before editing its content.')
        return current

    def new_token(user_id,name,expires=None):
        secret='mare_'+secrets.token_urlsafe(32)
        prefix=secret[:14]
        cursor=run('INSERT INTO api_tokens(user_id,name,token_hash,token_prefix,created,expires) VALUES(?,?,?,?,?,?)',(user_id,name,hashlib.sha256(secret.encode()).hexdigest(),prefix,now(),expires))
        return secret,cursor.lastrowid

    @api.get('/me')
    def me():
        return {'user':user_data(g.user),'permissions':sorted(role_permissions(g.user['role']))}

    @api.route('/tokens',methods=['GET','POST'])
    @require('tokens:manage')
    def tokens():
        if request.method=='GET':
            rows=db().execute('SELECT id,name,token_prefix,created,last_used,revoked,expires FROM api_tokens WHERE user_id=? ORDER BY id DESC',(g.user['id'],)).fetchall()
            return {'tokens':[dict(row) for row in rows]}
        value=body();name=value.get('name','')
        if not isinstance(name,str) or not name.strip() or len(name)>80:return jsonify(error='Token name must be 1-80 characters.'),400
        name=name.strip();days=value.get('expires_in_days');expires=None
        if days is not None:
            if type(days) is not int or not 1<=days<=3650:return jsonify(error='expires_in_days must be an integer from 1 to 3650.'),400
            from datetime import datetime,timedelta,timezone
            expires=(datetime.now(timezone.utc)+timedelta(days=days)).isoformat(timespec='seconds')
        secret,token_id=new_token(g.user['id'],name,expires)
        audit('Created API token '+name)
        return jsonify(id=token_id,name=name,token=secret,expires=expires),201

    @api.delete('/tokens/<int:token_id>')
    @require('tokens:manage')
    def revoke_token(token_id):
        row=db().execute('SELECT * FROM api_tokens WHERE id=?',(token_id,)).fetchone()
        if not row or (row['user_id']!=g.user['id'] and not allowed('users:manage')):abort(404)
        if row['revoked']:return '',204
        run('UPDATE api_tokens SET revoked=? WHERE id=?',(now(),token_id))
        audit('Revoked API token '+row['name'])
        return '',204

    @api.get('/permissions')
    @require('roles:manage')
    def permissions():
        return {'permissions':[{'name':name,'description':description} for name,description in PERMISSIONS.items()]}

    @api.route('/roles',methods=['GET','POST'])
    @require('roles:manage')
    def roles():
        if request.method=='GET':return {'roles':role_records(db())}
        value=body();name=value.get('name','');description=value.get('description','');assigned=value.get('permissions',[])
        if not isinstance(name,str) or not re.fullmatch(r'[a-z][a-z0-9_-]{2,31}',name):return jsonify(error='Role name must be 3-32 lowercase letters, numbers, underscores, or hyphens.'),400
        if not isinstance(description,str) or len(description)>300:return jsonify(error='Role description must be at most 300 characters.'),400
        description=description.strip()
        if not isinstance(assigned,list) or any(not isinstance(permission,str) for permission in assigned) or len(set(assigned))!=len(assigned) or any(permission not in PERMISSIONS for permission in assigned):return jsonify(error='Unknown or duplicate permission.'),400
        if not can_assign_role(name) or any(not allowed(permission) for permission in assigned):return jsonify(error='You cannot grant permissions you do not hold.'),403
        try:
            with db():
                db().execute('INSERT INTO roles(name,description,builtin) VALUES(?,?,0)',(name,description))
                db().executemany('INSERT INTO role_permissions(role_name,permission) VALUES(?,?)',[(name,permission) for permission in assigned])
        except sqlite3.IntegrityError:return jsonify(error='Role name already exists.'),409
        audit('Created role '+name)
        return jsonify(next(role for role in role_records(db()) if role['name']==name)),201

    @api.route('/roles/<name>',methods=['PATCH','DELETE'])
    @require('roles:manage')
    def role_item(name):
        role=db().execute('SELECT * FROM roles WHERE name=?',(name,)).fetchone()
        if not role:abort(404)
        if role['builtin']:return jsonify(error='Built-in roles cannot be changed or deleted.'),409
        if request.method=='DELETE':
            if db().execute('SELECT 1 FROM users WHERE role=?',(name,)).fetchone():return jsonify(error='Reassign users before deleting this role.'),409
            run('DELETE FROM roles WHERE name=?',(name,));audit('Deleted role '+name);return '',204
        value=body();description=value.get('description',role['description']);assigned=value.get('permissions',list(role_permissions(name)))
        if not isinstance(description,str) or len(description)>300:return jsonify(error='Role description must be at most 300 characters.'),400
        if not isinstance(assigned,list) or any(not isinstance(permission,str) for permission in assigned) or len(set(assigned))!=len(assigned) or any(permission not in PERMISSIONS for permission in assigned):return jsonify(error='Unknown or duplicate permission.'),400
        if any(not allowed(permission) for permission in assigned):return jsonify(error='You cannot grant permissions you do not hold.'),403
        with db():
            db().execute('UPDATE roles SET description=? WHERE name=?',(description,name))
            db().execute('DELETE FROM role_permissions WHERE role_name=?',(name,))
            db().executemany('INSERT INTO role_permissions(role_name,permission) VALUES(?,?)',[(name,permission) for permission in assigned])
        audit('Updated role '+name)
        return next(role for role in role_records(db()) if role['name']==name)

    @api.route('/users',methods=['GET','POST'])
    @require('users:manage')
    def users():
        if request.method=='GET':
            limit,offset=page()
            return {'users':[user_data(row) for row in db().execute('SELECT * FROM users ORDER BY username LIMIT ? OFFSET ?',(limit,offset))],'limit':limit,'offset':offset,'total':db().execute('SELECT count(*) FROM users').fetchone()[0]}
        value=body();username=value.get('username','');password=value.get('password','');role=value.get('role','User')
        if not isinstance(username,str) or not re.fullmatch(r'[A-Za-z0-9_.-]{3,64}',username.strip()):return jsonify(error='Invalid username.'),400
        username=username.strip()
        if not isinstance(password,str) or len(password)<12:return jsonify(error='Password must be at least 12 characters.'),400
        if not isinstance(role,str) or not db().execute('SELECT 1 FROM roles WHERE name=?',(role,)).fetchone():return jsonify(error='Unknown role.'),400
        if not can_assign_role(role):return jsonify(error='You cannot assign this role.'),403
        try:
            cursor=run('INSERT INTO users(username,password,role,forced) VALUES(?,?,?,0)',(username,generate_password_hash(password),role))
        except sqlite3.IntegrityError:return jsonify(error='Username already exists.'),409
        audit('Created user '+username)
        return jsonify(user=user_data(db().execute('SELECT * FROM users WHERE id=?',(cursor.lastrowid,)).fetchone())),201

    @api.route('/users/<int:user_id>',methods=['PATCH','DELETE'])
    @require('users:manage')
    def user_item(user_id):
        target=db().execute('SELECT * FROM users WHERE id=?',(user_id,)).fetchone()
        if not target:abort(404)
        if request.method=='DELETE':
            if target['id']==g.user['id']:return jsonify(error='You cannot delete the account used by this request.'),409
            if target['role']=='Administrator' and target['active'] and db().execute("SELECT count(*) FROM users WHERE role='Administrator' AND active=1").fetchone()[0]<=1:return jsonify(error='Cannot remove the last active Administrator.'),409
            with db():
                db().execute('UPDATE cases SET owner=NULL WHERE owner=?',(user_id,))
                db().execute('UPDATE cases SET creator=NULL WHERE creator=?',(user_id,))
                db().execute('DELETE FROM drafts WHERE user_id=?',(user_id,))
                db().execute('DELETE FROM users WHERE id=?',(user_id,))
            audit('Deleted user '+target['username'])
            return '',204
        value=body();role=value.get('role',target['role']);active=value.get('active',bool(target['active']))
        if not isinstance(role,str) or not db().execute('SELECT 1 FROM roles WHERE name=?',(role,)).fetchone():return jsonify(error='Unknown role.'),400
        if not can_assign_role(role):return jsonify(error='You cannot assign this role.'),403
        if not isinstance(active,bool):return jsonify(error='active must be a boolean.'),400
        if target['role']=='Administrator' and target['active'] and (role!='Administrator' or not active) and db().execute("SELECT count(*) FROM users WHERE role='Administrator' AND active=1").fetchone()[0]<=1:return jsonify(error='Cannot disable or demote the last active Administrator.'),409
        version_changed=bool(active)!=bool(target['active']) or role!=target['role']
        run('UPDATE users SET role=?,active=?,version=version+? WHERE id=?',(role,int(active),int(version_changed),user_id))
        audit('Updated user '+target['username'])
        return {'user':user_data(db().execute('SELECT * FROM users WHERE id=?',(user_id,)).fetchone())}

    @api.route('/settings',methods=['GET','PATCH'])
    @require({'GET':'settings:read','PATCH':'settings:write'})
    def settings():
        if request.method=='GET':return {'settings':{'sample_archive_password':{'configured':bool(sample_archive_password())}}}
        value=body();unknown=set(value)-{'sample_archive_password'}
        if unknown:return jsonify(error='Unknown setting: '+', '.join(sorted(unknown))),400
        password=value.get('sample_archive_password')
        if not isinstance(password,str) or not password or len(password)>256 or '\x00' in password:return jsonify(error='Sample archive password must be 1-256 characters.'),400
        run("INSERT INTO site_settings(name,value) VALUES('sample_archive_password',?) ON CONFLICT(name) DO UPDATE SET value=excluded.value",(password,))
        audit('Changed the sample archive password via API')
        return {'settings':{'sample_archive_password':{'configured':True}}}

    def case_data(row):
        return {'id':row['id'],'number':row['number'],'name':row['name'],'description':row['description'] or '', 'stage':row['stage'],'stage_name':app.config.get('MARE_STAGES',['Not started','Malware Analysis','Packaging & Delivery','Completed'])[row['stage']],'created':row['created'],'owner_id':row['owner'],'owner_name':row['owner_name'],'creator_id':row['creator'],'creator_name':row['creator_name'],'external_system':row['external_system'] or '', 'external_number':row['external_number'] or '','owner_active':bool(row['owner_active']),'report_path':row['report_path'] or ''}

    @api.route('/cases',methods=['GET','POST'])
    @require({'GET':'cases:read','POST':'cases:create'})
    def case_collection():
        if request.method=='GET':
            limit,offset=page()
            rows=db().execute('SELECT * FROM cases ORDER BY id DESC LIMIT ? OFFSET ?',(limit,offset)).fetchall()
            return {'cases':[case_data(case(row['id'])) for row in rows],'limit':limit,'offset':offset,'total':db().execute('SELECT count(*) FROM cases').fetchone()[0]}
        value=body();name=value.get('name','');description=value.get('description','');system=value.get('external_system','');external=value.get('external_number','')
        if not isinstance(name,str) or not name.strip() or len(name)>200:return jsonify(error='Case name must be 1-200 characters.'),400
        if not isinstance(description,str) or len(description)>20000:return jsonify(error='Description must be at most 20,000 characters.'),400
        if not isinstance(system,str) or not isinstance(external,str):return jsonify(error='External reference values must be strings.'),400
        reference=external_reference(value)
        if reference is None:return jsonify(error='External reference system and number must be supplied together.'),400
        name=dated_title(name)
        if len(name)>200:return jsonify(error='Case name with date prefix must be at most 200 characters.'),400
        owner=value.get('owner_id')
        if owner is not None and (type(owner) is not int or not db().execute('SELECT 1 FROM users WHERE id=? AND active=1',(owner,)).fetchone()):return jsonify(error='owner_id must identify an active user.'),400
        system,external=reference;connection=db()
        with connection:
            connection.execute('BEGIN IMMEDIATE');number=allocate_case_number(connection)
            cursor=connection.execute('INSERT INTO cases(number,name,description,created,owner,external_system,external_number,creator,creator_username,owner_required) VALUES(?,?,?,?,?,?,?,?,?,1)',(number,name,description,now(),owner,system,external,g.user['id'],g.user['username']))
            case_id=cursor.lastrowid
        ensure_package(case_id);audit('Created case '+number)
        return jsonify(case=case_data(case(case_id))),201

    @api.route('/cases/<int:case_id>',methods=['GET','PATCH','DELETE'])
    @require({'GET':'cases:read','PATCH':'cases:update','DELETE':'cases:delete'})
    def case_item(case_id):
        current=case(case_id)
        if request.method=='GET':
            detail=case_data(current)
            detail.update(readiness=readiness(case_id),history=[dict(row) for row in db().execute('SELECT stage,author,created,outcome,reason FROM history WHERE case_id=? ORDER BY rowid',(case_id,))],deferred=[dict(row) for row in db().execute('SELECT stage,reason,resolved FROM deferred WHERE case_id=?',(case_id,))])
            return {'case':detail}
        if request.method=='DELETE':
            if db().execute("SELECT 1 FROM report_jobs WHERE case_id=? AND status IN ('queued','running')",(case_id,)).fetchone():return jsonify(error='Wait for report generation to finish before deleting this case.'),409
            connection=db();folder=package(case_id).parent;staged=folder.parent/('.deleting-'+secrets.token_hex(8));moved=False
            try:
                if folder.exists():folder.rename(staged);moved=True
                with connection:
                    for table in ('notes','tasks','history','readiness','artifacts','drafts','deferred','report_jobs','report_images','figure_sequence','indicator_tables','indicator_sections','indicator_table_legacy','reference_tables'):
                        connection.execute(f'DELETE FROM {table} WHERE case_id=?',(case_id,))
                    connection.execute('DELETE FROM cases WHERE id=?',(case_id,))
                    connection.execute('INSERT INTO audit(actor,action,created) VALUES(?,?,?)',(g.user['username'],'Deleted case '+current['number'],now()))
            except Exception:
                if moved:staged.rename(folder)
                raise
            if moved:shutil.rmtree(staged)
            return '',204
        value=body();name=value.get('name',current['name']);description=value.get('description',current['description'] or '');system=value.get('external_system',current['external_system'] or '');external=value.get('external_number',current['external_number'] or '')
        if not isinstance(name,str) or not name.strip() or len(name)>200:return jsonify(error='Case name must be 1-200 characters.'),400
        if not isinstance(description,str) or len(description)>20000:return jsonify(error='Description must be at most 20,000 characters.'),400
        if not isinstance(system,str) or not isinstance(external,str):return jsonify(error='External reference values must be strings.'),400
        reference=external_reference({'external_system':system,'external_number':external})
        if reference is None:return jsonify(error='External reference system and number must be supplied together.'),400
        owner=value.get('owner_id',current['owner'])
        if owner is not None and (type(owner) is not int or not db().execute('SELECT 1 FROM users WHERE id=? AND active=1',(owner,)).fetchone()):return jsonify(error='owner_id must identify an active user.'),400
        system,external=reference
        run('UPDATE cases SET name=?,description=?,external_system=?,external_number=?,owner=? WHERE id=?',(name.strip(),description,system,external,owner,case_id))
        audit('Updated case details '+current['number'])
        return {'case':case_data(case(case_id))}

    @api.post('/cases/<int:case_id>/stage')
    @require('cases:workflow')
    def advance_case(case_id):
        current=case(case_id);value=body()
        if current['owner_required'] and not current['owner_active']:return jsonify(error='Assign an active owner before changing case stages.'),409
        if value.get('expected')!=current['stage']:return jsonify(error='Case stage changed; reload and retry.'),409
        outcome=value.get('outcome','Done');reason=value.get('reason','')
        if not isinstance(reason,str):return jsonify(error='reason must be a string.'),400
        reason=reason.strip()
        if outcome not in ('Done','No applicable work','Deferred'):return jsonify(error='Invalid stage outcome.'),400
        if outcome!='Done' and not reason:return jsonify(error='A reason is required for skipped or deferred work.'),400
        if current['stage']==0 and (not current['owner'] or not current['owner_active']):return jsonify(error='Assign an active owner before starting analysis.'),409
        if current['stage']==len(stages)-2:
            blockers=review_issues(case_id)
            if blockers:return jsonify(error='Case completion is blocked.',blockers=blockers),409
        if current['stage']<0 or current['stage']>=len(stages)-1:return jsonify(error='Case cannot advance from its current stage.'),409
        if current['stage']==0:outcome='Started';reason=''
        with db():
            cursor=db().execute('UPDATE cases SET stage=stage+1 WHERE id=? AND stage=?',(case_id,current['stage']))
            if not cursor.rowcount:return jsonify(error='Case stage changed; reload and retry.'),409
            db().execute('INSERT INTO history(case_id,stage,author,created,outcome,reason) VALUES(?,?,?,?,?,?)',(case_id,current['stage'],g.user['username'],now(),outcome,reason))
            if outcome=='Deferred':db().execute('INSERT OR REPLACE INTO deferred VALUES(?,?,?,0)',(case_id,current['stage'],reason))
        audit(f'Case {case_id}: {outcome} — {stages[current["stage"]]}')
        return {'case':case_data(case(case_id))}

    @api.post('/cases/<int:case_id>/reopen')
    @require('cases:workflow')
    def reopen_case(case_id):
        current=case(case_id)
        if current['stage']!=len(stages)-1:return jsonify(error='Only completed cases can be reopened.'),409
        if current['owner_required'] and not current['owner_active']:return jsonify(error='Assign an active owner before reopening this case.'),409
        with db():
            db().execute('UPDATE cases SET stage=? WHERE id=?',(1,case_id))
            db().execute('INSERT INTO history(case_id,stage,author,created,outcome,reason) VALUES(?,?,?,?,?,?)',(case_id,current['stage'],g.user['username'],now(),'Reopened','Returned to Malware Analysis'))
        audit(f'Reopened case {case_id}')
        return {'case':case_data(case(case_id))}

    @api.route('/cases/<int:case_id>/readiness',methods=['GET','PUT'])
    @require({'GET':'cases:read','PUT':'cases:update'})
    def case_readiness(case_id):
        case(case_id)
        if request.method=='GET':return {'readiness':readiness(case_id)}
        editable_case(case_id);value=body();category=value.get('category');status=value.get('status');reason=value.get('reason','')
        if not isinstance(reason,str):return jsonify(error='reason must be a string.'),400
        reason=reason.strip()
        from mip import CATEGORIES
        if category not in CATEGORIES or status not in ('Pending','Populated','Not applicable'):return jsonify(error='Invalid category or readiness status.'),400
        if category=='reports' and status=='Not applicable':return jsonify(error='A report is required for every MIP.'),400
        if status=='Not applicable' and not reason:return jsonify(error='A reason is required when a category is not applicable.'),400
        if status=='Populated':
            root=ensure_package(case_id)
            if not any(path.is_file() and not path.is_symlink() for path in (root/category).rglob('*')):return jsonify(error='Add content before marking this category populated.'),409
        run('INSERT OR REPLACE INTO readiness VALUES(?,?,?,?)',(case_id,category,status,reason if status=='Not applicable' else ''))
        audit(f'Case {case_id}: {category} {status}')
        return {'readiness':readiness(case_id)}

    @api.route('/cases/<int:case_id>/tasks',methods=['GET','POST'])
    @require({'GET':'cases:read','POST':'cases:update'})
    def case_tasks(case_id):
        case(case_id)
        if request.method=='GET':
            limit,offset=page()
            return {'tasks':[dict(row) for row in db().execute('SELECT id,title,body,priority,state,done,created FROM tasks WHERE case_id=? ORDER BY id LIMIT ? OFFSET ?',(case_id,limit,offset))],'limit':limit,'offset':offset,'total':db().execute('SELECT count(*) FROM tasks WHERE case_id=?',(case_id,)).fetchone()[0]}
        editable_case(case_id);value=body();title=value.get('title','');description=value.get('body',value.get('description',''));priority=value.get('priority','Normal')
        if not isinstance(title,str) or not title.strip() or len(title)>200 or not isinstance(description,str) or len(description)>20000 or priority not in ('Low','Normal','High','Critical'):return jsonify(error='Invalid task fields.'),400
        title=title.strip()
        cursor=run("INSERT INTO tasks(case_id,title,body,priority,state,done,created) VALUES(?,?,?,?,'Not Started',0,?)",(case_id,title,description,priority,now()))
        audit(f'Added task to case {case_id}')
        return jsonify(task=dict(db().execute('SELECT id,title,body,priority,state,done,created FROM tasks WHERE id=?',(cursor.lastrowid,)).fetchone())),201

    @api.route('/cases/<int:case_id>/tasks/<int:task_id>',methods=['PATCH','DELETE'])
    @require({'PATCH':'cases:update','DELETE':'cases:update'})
    def case_task(case_id,task_id):
        editable_case(case_id);task=db().execute('SELECT * FROM tasks WHERE id=? AND case_id=?',(task_id,case_id)).fetchone()
        if not task:abort(404)
        if request.method=='DELETE':
            run('DELETE FROM tasks WHERE id=? AND case_id=?',(task_id,case_id));audit(f'Deleted task {task_id} from case {case_id}');return '',204
        value=body();title=value.get('title',task['title']);description=value.get('body',value.get('description',task['body'] or ''));priority=value.get('priority',task['priority'] or 'Normal');state=value.get('state',task['state'] or 'Not Started')
        if not isinstance(title,str) or not title.strip() or len(title)>200 or not isinstance(description,str) or len(description)>20000 or priority not in ('Low','Normal','High','Critical') or state not in ('Not Started','In Progress','Completed'):return jsonify(error='Invalid task fields.'),400
        title=title.strip()
        run('UPDATE tasks SET title=?,body=?,priority=?,state=?,done=? WHERE id=? AND case_id=?',(title,description,priority,state,int(state=='Completed'),task_id,case_id));audit(f'Updated task {task_id} in case {case_id}')
        return {'task':dict(db().execute('SELECT id,title,body,priority,state,done,created FROM tasks WHERE id=?',(task_id,)).fetchone())}

    @api.route('/cases/<int:case_id>/notes',methods=['GET','POST'])
    @require({'GET':'cases:read','POST':'cases:update'})
    def case_notes(case_id):
        case(case_id)
        if request.method=='GET':
            limit,offset=page()
            return {'notes':[dict(row) for row in db().execute('SELECT id,title,body,author,created,include_export FROM notes WHERE case_id=? ORDER BY id LIMIT ? OFFSET ?',(case_id,limit,offset))],'limit':limit,'offset':offset,'total':db().execute('SELECT count(*) FROM notes WHERE case_id=?',(case_id,)).fetchone()[0]}
        editable_case(case_id);value=body();title=value.get('title','');text=value.get('body','');include=value.get('include_export',False)
        if not isinstance(title,str) or len(title)>200 or not isinstance(text,str) or not text.strip() or len(text)>100000 or not isinstance(include,bool):return jsonify(error='Invalid note fields.'),400
        title=title.strip()
        cursor=run('INSERT INTO notes(case_id,body,author,created,title,include_export) VALUES(?,?,?,?,?,?)',(case_id,text.strip(),g.user['username'],now(),title,int(include)))
        if include:mark_pending(case_id,'reports/reverse-engineering-notes.md')
        audit(f'Added note to case {case_id}')
        return jsonify(note=dict(db().execute('SELECT id,title,body,author,created,include_export FROM notes WHERE id=?',(cursor.lastrowid,)).fetchone())),201

    @api.route('/cases/<int:case_id>/notes/<int:note_id>',methods=['PATCH','DELETE'])
    @require({'PATCH':'cases:update','DELETE':'cases:update'})
    def case_note(case_id,note_id):
        editable_case(case_id);note=db().execute('SELECT * FROM notes WHERE id=? AND case_id=?',(note_id,case_id)).fetchone()
        if not note:abort(404)
        if request.method=='DELETE':
            if note['include_export']:mark_pending(case_id,'reports/reverse-engineering-notes.md')
            run('DELETE FROM notes WHERE id=? AND case_id=?',(note_id,case_id));audit(f'Deleted note {note_id} from case {case_id}');return '',204
        value=body();title=value.get('title',note['title'] or '');text=value.get('body',note['body']);include=value.get('include_export',bool(note['include_export']))
        if not isinstance(title,str) or len(title)>200 or not isinstance(text,str) or not text.strip() or len(text)>100000 or not isinstance(include,bool):return jsonify(error='Invalid note fields.'),400
        title=title.strip()
        if bool(note['include_export']) or include:mark_pending(case_id,'reports/reverse-engineering-notes.md')
        run('UPDATE notes SET title=?,body=?,include_export=? WHERE id=? AND case_id=?',(title,text.strip(),int(include),note_id,case_id));audit(f'Updated note {note_id} in case {case_id}')
        return {'note':dict(db().execute('SELECT id,title,body,author,created,include_export FROM notes WHERE id=?',(note_id,)).fetchone())}

    @api.route('/cases/<int:case_id>/draft',methods=['GET','PUT','DELETE'])
    @require({'GET':'cases:read','PUT':'cases:update','DELETE':'cases:update'})
    def case_draft(case_id):
        editable_case(case_id) if request.method!='GET' else case(case_id)
        draft=db().execute('SELECT title,body,updated FROM drafts WHERE case_id=? AND user_id=?',(case_id,g.user['id'])).fetchone()
        if request.method=='GET':return {'draft':dict(draft) if draft else None}
        if request.method=='DELETE':run('DELETE FROM drafts WHERE case_id=? AND user_id=?',(case_id,g.user['id']));return '',204
        value=body();title=value.get('title','');text=value.get('body','')
        if not isinstance(title,str) or len(title)>200 or not isinstance(text,str) or len(text)>100000:return jsonify(error='Draft title or body is too long.'),400
        run('INSERT OR REPLACE INTO drafts VALUES(?,?,?,?,?)',(case_id,g.user['id'],title,text,now()))
        return {'draft':{'title':title,'body':text,'updated':now()}}

    @api.route('/cases/<int:case_id>/assets',methods=['GET','POST','DELETE'])
    @require({'GET':'cases:read','POST':'cases:assets','DELETE':'cases:assets'})
    def case_assets(case_id):
        current=case(case_id)
        if request.method=='GET':
            category=request.args.get('category')
            if category and category not in CATEGORIES:return jsonify(error='Unknown asset category.'),400
            root=ensure_package(case_id);files=[]
            for path in sorted(root.rglob('*')):
                relative=path.relative_to(root).as_posix()
                if (category and not relative.startswith(category+'/')) or not path.is_file() or path.is_symlink() or is_backup(relative):continue
                artifact=db().execute('SELECT description FROM artifacts WHERE case_id=? AND path=?',(case_id,relative)).fetchone()
                files.append({'path':relative,'size':path.stat().st_size,'description':artifact['description'] if artifact else ''})
            return {'files':files}
        editable_case(case_id)
        if request.method=='DELETE':
            value=body();relative=value.get('path','')
            if not isinstance(relative,str) or relative.split('/')[0] not in CATEGORIES:return jsonify(error='Invalid asset path.'),400
            path=safe_path(case_id,relative)
            if not path.is_file():abort(404)
            path.unlink();db().execute('DELETE FROM artifacts WHERE case_id=? AND path=?',(case_id,relative));db().commit();mark_pending(case_id,relative);audit(f'Deleted case asset {case_id}: {relative}')
            return '',204
        category=request.form.get('category','');upload=request.files.get('file')
        if category not in CATEGORIES or not upload:return jsonify(error='Choose a valid category and file.'),400
        name=secure_filename(upload.filename or '')
        if not name:return jsonify(error='Invalid filename.'),400
        raw=upload.read(100*1024*1024+1)
        if len(raw)>100*1024*1024:return jsonify(error='Files are limited to 100 MiB.'),413
        relative_name=name+'.zip' if category=='samples' else name
        relative=category+'/'+relative_name;target=safe_path(case_id,relative);target.parent.mkdir(parents=True,exist_ok=True)
        if target.exists():return jsonify(error='A file with that name already exists.'),409
        if category=='samples':
            import pyzipper
            output=tempfile.SpooledTemporaryFile(max_size=8*1024*1024)
            try:
                with pyzipper.AESZipFile(output,'w',compression=pyzipper.ZIP_DEFLATED,encryption=pyzipper.WZ_AES) as archive:
                    archive.setpassword(sample_archive_password().encode('utf-8'));archive.writestr(name,raw)
                output.seek(0)
                with target.open('xb') as destination:shutil.copyfileobj(output,destination)
            finally:output.close()
        else:
            with target.open('xb') as destination:destination.write(raw)
        run('INSERT OR REPLACE INTO artifacts VALUES(?,?,?,?)',(case_id,relative,request.form.get('description','').strip(),''));mark_pending(case_id,relative);audit(f'Uploaded case {case_id}: {relative}')
        return jsonify(file={'path':relative,'size':target.stat().st_size}),201

    @api.get('/cases/<int:case_id>/assets/<path:relative_path>')
    @require('cases:assets')
    def download_case_asset(case_id,relative_path):
        case(case_id);path=safe_path(case_id,relative_path)
        if not path.is_file():abort(404)
        return send_file(path,as_attachment=True,download_name=path.name)

    @api.route('/cases/<int:case_id>/indicators',methods=['GET','PUT'])
    @require({'GET':'indicators:read','PUT':'indicators:write'})
    def case_indicators(case_id):
        case(case_id)
        if request.method=='GET':return load_table(db,case_id)
        editable_case(case_id);value=body();current=load_table(db,case_id)
        try:
            columns=value.get('columns',DEFAULT_COLUMNS);revision=value['revision'];sections=value.get('sections')
            if isinstance(revision,bool) or not isinstance(revision,int):raise ValueError('revision must be an integer.')
            if sections is None:
                rows=value.get('rows',[]);validate_table(columns,rows)
                if len(current['sections'])!=1:raise ValueError('Send all sections together to preserve their grouping.')
                sections=[{**current['sections'][0],'rows':rows}]
            sections=validate_sections(sections)
            if revision!=current['revision']:return jsonify(error='Indicators changed in another session; reload before saving.'),409
        except (ValueError,KeyError,TypeError) as error:return jsonify(error=str(error)),400
        with db():
            db().execute('BEGIN IMMEDIATE')
            if revision!=load_table(db,case_id)['revision']:return jsonify(error='Indicators changed in another session; reload before saving.'),409
            rows=[row for section in sections for row in section['rows']]
            db().execute('INSERT OR REPLACE INTO indicator_tables VALUES(?,?,?,?)',(case_id,json.dumps(DEFAULT_COLUMNS),json.dumps(rows),revision+1))
            db().execute('INSERT OR REPLACE INTO indicator_sections VALUES(?,?)',(case_id,json.dumps(sections)))
        result=load_table(db,case_id);(ensure_package(case_id)/'iocs/indicators.csv').write_text(indicator_csv(result));mark_pending(case_id,'iocs/indicators.csv');mark_pending(case_id,'reports/sections');audit(f'Updated indicators for case {case_id}')
        return result

    @api.route('/cases/<int:case_id>/references',methods=['GET','PUT'])
    @require({'GET':'references:read','PUT':'references:write'})
    def case_references(case_id):
        case(case_id)
        if request.method=='GET':return load_references(db,case_id)
        editable_case(case_id);value=body();rows=value.get('rows');revision=value.get('revision');current=load_references(db,case_id)
        if isinstance(revision,bool) or not isinstance(revision,int) or not isinstance(rows,list) or len(rows)>10000 or any(not isinstance(row,list) or len(row)!=len(REFERENCE_COLUMNS) or any(not isinstance(cell,str) or len(cell)>4000 for cell in row) for row in rows):return jsonify(error='References require a revision and at most 10,000 rows of two text cells (4,000 characters each).'),400
        if revision!=current['revision']:return jsonify(error='References changed in another session; reload before saving.'),409
        with db():
            db().execute('BEGIN IMMEDIATE')
            if revision!=load_references(db,case_id)['revision']:return jsonify(error='References changed in another session; reload before saving.'),409
            db().execute('INSERT OR REPLACE INTO reference_tables VALUES(?,?,?)',(case_id,json.dumps(rows),revision+1))
        import csv
        buffer=io.StringIO(newline='');writer=csv.writer(buffer);writer.writerow(REFERENCE_COLUMNS);writer.writerows(rows)
        (ensure_package(case_id)/'supporting/references.csv').write_text(buffer.getvalue());mark_pending(case_id,'supporting/references.csv');mark_pending(case_id,'reports/sections');audit(f'Updated references for case {case_id}')
        return load_references(db,case_id)

    @api.route('/cases/<int:case_id>/report',methods=['GET','PUT'])
    @require({'GET':'reports:read','PUT':'reports:write'})
    def case_report(case_id):
        current=case(case_id);root=ensure_package(case_id)
        if request.method=='GET':
            mappings=root/'mappings'
            return {'sections':report_helpers['manual'](case_id),'mappings':{key:(mappings/filename).read_text(encoding='utf-8') if (mappings/filename).is_file() else '' for key,filename in (('attack','mitre-attack.md'),('mbc','mitre-mbc.md'))},'report_path':current_report(current,root),'report_exists':(root/current_report(current,root)).is_file()}
        editable_case(case_id);value=body();sections=value.get('sections')
        if not isinstance(sections,dict) or set(sections)-set(TOKENS):return jsonify(error='sections must be an object containing known report section names.'),400
        directory=root/'reports/sections';directory.mkdir(exist_ok=True)
        for key,text in sections.items():
            if not isinstance(text,str) or len(text)>100000:return jsonify(error=f'Invalid report section: {key}.'),400
        for key in TOKENS:
            if key in SECTIONS:(directory/(key+'.md')).write_text(sections.get(key,report_helpers['manual'](case_id).get(key,'')))
        mark_pending(case_id,'reports/sections');audit(f'Saved report sections for case {case_id}')
        return {'sections':report_helpers['manual'](case_id)}

    @api.route('/cases/<int:case_id>/report/mappings',methods=['GET','PUT'])
    @require({'GET':'reports:read','PUT':'reports:write'})
    def case_report_mappings(case_id):
        case(case_id);directory=ensure_package(case_id)/'mappings';files={'attack':'mitre-attack.md','mbc':'mitre-mbc.md'}
        if request.method=='GET':return {'mappings':{key:(directory/name).read_text(encoding='utf-8') if (directory/name).is_file() else '' for key,name in files.items()}}
        editable_case(case_id);value=body();mappings=value.get('mappings')
        if not isinstance(mappings,dict) or set(mappings)-set(files) or any(not isinstance(text,str) or len(text)>100000 for text in mappings.values()):return jsonify(error='mappings must contain attack and/or mbc Markdown strings of at most 100,000 characters.'),400
        if db().execute("SELECT 1 FROM report_jobs WHERE case_id=? AND status IN ('queued','running')",(case_id,)).fetchone():return jsonify(error='Wait for report generation to finish before saving mappings.'),409
        directory.mkdir(exist_ok=True)
        for key,name in files.items():
            if key not in mappings:continue
            path=directory/name
            if mappings[key].strip():path.write_text(mappings[key],encoding='utf-8')
            else:path.unlink(missing_ok=True)
        mark_pending(case_id,'mappings/mitre-attack.md');audit(f'Saved MITRE mappings for case {case_id}')
        return {'mappings':{key:(directory/name).read_text(encoding='utf-8') if (directory/name).is_file() else '' for key,name in files.items()}}

    @api.post('/cases/<int:case_id>/archive')
    @require('cases:export')
    def export_case(case_id):
        current=case(case_id);value=body();archive_type=value.get('archive_type','standard');include_samples=value.get('include_samples',False);acknowledge=value.get('acknowledge',False)
        if archive_type not in ('standard','raw') or not isinstance(include_samples,bool) or not isinstance(acknowledge,bool):return jsonify(error='Use archive_type standard or raw and boolean include_samples/acknowledge fields.'),400
        if include_samples and not allowed('samples:export'):return jsonify(error='Including malware sample archives requires samples:export permission.'),403
        if current['owner_required'] and not current['owner_active']:return jsonify(error='Assign an active owner before export.'),409
        if current['stage'] not in (len(stages)-2,len(stages)-1):return jsonify(error='MIP export is available during Packaging & Delivery or Completed.'),409
        blockers=review_issues(case_id)
        if blockers and not acknowledge:return jsonify(error='Resolve or acknowledge outstanding review items before export.',blockers=blockers),409
        root=ensure_package(case_id);report=root/current_report(current,root)
        if archive_type=='standard' and not (report.is_file() and report.stat().st_size>0):return jsonify(error='A completed Word report is required for Standard export.'),409
        output,name=build_archive(case_id,archive_type,include_samples=include_samples)
        audit(f'Exported MIP for case {case_id}')
        response=send_file(output,as_attachment=True,download_name=name+'.zip',mimetype='application/zip');response.call_on_close(output.close)
        return response

    @api.get('/cases/<int:case_id>/report/job')
    @require('reports:read')
    def case_report_job(case_id):
        case(case_id);row=db().execute('SELECT * FROM report_jobs WHERE case_id=? ORDER BY started DESC,rowid DESC LIMIT 1',(case_id,)).fetchone()
        if not row:return {'job':None}
        try:messages=json.loads(row['progress'])
        except (TypeError,ValueError):messages=[]
        return {'job':{'id':row['id'],'status':row['status'],'messages':messages,'updated':row['updated']}}

    @api.post('/cases/<int:case_id>/report/generate')
    @require('reports:generate')
    def generate_case_report(case_id):
        editable_case(case_id)
        return report_helpers['generate'](case_id)

    @api.post('/cases/<int:case_id>/report/final')
    @require('reports:generate')
    def upload_final_report(case_id):
        editable_case(case_id)
        return report_helpers['final'](case_id)

    @api.get('/cases/<int:case_id>/report/download')
    @require('reports:read')
    def download_report(case_id):
        kind=request.args.get('format','docx')
        if kind not in ('docx','pdf'):return jsonify(error='format must be docx or pdf.'),400
        current=case(case_id);root=package(case_id);path=root/current_report(current,root)
        if kind=='pdf':path=path.with_suffix('.pdf')
        if not path.is_file() or path.is_symlink():abort(404,description='Report file not found.')
        return send_file(path,as_attachment=True,download_name=path.name)

    @api.route('/cases/<int:case_id>/report/images',methods=['GET','POST'])
    @require({'GET':'reports:read','POST':'reports:write'})
    def report_images(case_id):
        if request.method=='GET':return asset_helpers['list'](case_id)
        editable_case(case_id);result=asset_helpers['upload'](case_id)
        if isinstance(result,dict):return {**result,'url':f'/api/v1/cases/{case_id}/report/images/{result["name"]}'},201
        return result

    @api.route('/cases/<int:case_id>/report/images/<name>',methods=['GET','DELETE'])
    @require({'GET':'reports:read','DELETE':'reports:write'})
    def report_image(case_id,name):
        if request.method=='GET':return asset_helpers['get'](case_id,name)
        editable_case(case_id);result=asset_helpers['delete'](case_id,name)
        return ('',204) if isinstance(result,dict) and result.get('deleted') else result

    def template_rows():
        selected=report_helpers['settings'](g.user['id'])['template_id']
        return [{'id':row['id'],'name':row['name'],'created':row['created'],'selected':row['id']==selected} for row in db().execute('SELECT * FROM word_templates WHERE user_id=? ORDER BY created DESC,rowid DESC',(g.user['id'],))]

    @api.route('/templates',methods=['GET','POST'])
    @require('templates:manage')
    def templates():
        if request.method=='GET':return {'templates':template_rows()}
        outcome=web_result(report_helpers['upload_template'](),'Template saved',201)
        if isinstance(outcome,tuple) and outcome[1]==201:return jsonify(message=outcome[0].get_json()['message'],templates=template_rows()),201
        return outcome

    @api.put('/templates/selected')
    @require('templates:manage')
    def select_template():
        template_id=body().get('template_id','')
        if not isinstance(template_id,str):return jsonify(error='template_id must be a string.'),400
        if template_id and not db().execute('SELECT 1 FROM word_templates WHERE id=? AND user_id=?',(template_id,g.user['id'])).fetchone():abort(404)
        run('INSERT OR REPLACE INTO report_settings VALUES(?,?)',(g.user['id'],template_id))
        return {'templates':template_rows()}

    @api.route('/templates/<template_id>',methods=['GET','DELETE'])
    @require('templates:manage')
    def template_item(template_id):
        if request.method=='GET':return report_helpers['download_template'](template_id)
        if not db().execute('SELECT 1 FROM word_templates WHERE id=? AND user_id=?',(template_id,g.user['id'])).fetchone():abort(404)
        report_helpers['delete_template'](template_id);get_flashed_messages()
        return '',204

    @api.post('/cases/<int:case_id>/backup')
    @require('cases:export')
    def case_backup(case_id):
        return web_result(backup_helpers['single'](case_id))

    @api.post('/backups/export')
    @require('backups:manage')
    def export_all_cases():
        return web_result(backup_helpers['export']())

    @api.post('/backups/import')
    @api.post('/backups/import-raw')
    @require('backups:manage')
    def api_import_backup():
        if not request.files.get('backup'):return jsonify(error='Upload the archive in the multipart field "backup".'),400
        return web_result(backup_helpers['import'](),'Imported',201)

    @api.post('/backups/database')
    @require('backups:manage')
    def api_database_backup():
        return web_result(backup_helpers['database']())

    @api.get('/metrics')
    @require('metrics:read')
    def metrics():
        users,charts=metrics_data()
        return {'users':[dict(row) for row in users],'stages':charts['stages'],'completed':charts['completed']}

    @app.errorhandler(HTTPException)
    def api_unmatched_error(error):
        # Covers routing errors (404/405) and oversized uploads, which blueprint handlers never see.
        return (jsonify(error=error.description),error.code) if request.path.startswith('/api/v1/') else error

    app.register_blueprint(api)

    @app.post('/account/api-tokens')
    def create_account_api_token():
        if not g.user:abort(401)
        name=request.form.get('name','').strip()
        if not name or len(name)>80:abort(400)
        days=request.form.get('expires_in_days','').strip();expires=None
        if days:
            if not days.isdigit() or not 1<=int(days)<=3650:abort(400)
            from datetime import datetime,timedelta,timezone
            expires=(datetime.now(timezone.utc)+timedelta(days=int(days))).isoformat(timespec='seconds')
        secret,_=new_token(g.user['id'],name,expires)
        session['new_api_token']=secret
        audit('Created API token '+name)
        return redirect('/api#api-tokens')

    @app.post('/account/api-tokens/<int:token_id>/revoke')
    def revoke_account_api_token(token_id):
        if not g.user:abort(401)
        row=db().execute('SELECT * FROM api_tokens WHERE id=? AND user_id=?',(token_id,g.user['id'])).fetchone()
        if not row:abort(404)
        run('UPDATE api_tokens SET revoked=? WHERE id=?',(now(),token_id));audit('Revoked API token '+row['name'])
        return redirect('/api#api-tokens')

    @app.get('/api')
    def api_page():
        tokens=db().execute('SELECT id,name,token_prefix,created,last_used,revoked,expires FROM api_tokens WHERE user_id=? ORDER BY id DESC',(g.user['id'],)).fetchall()
        groups={}
        for rule in sorted(app.url_map.iter_rules(),key=lambda item:item.rule):
            if not rule.endpoint.startswith('api.'):continue
            permission=getattr(app.view_functions[rule.endpoint],'permission',None)
            path=rule.rule[len('/api/v1'):]
            group=path.strip('/').split('/')[0] or 'root'
            for method in sorted(rule.methods-{'HEAD','OPTIONS'}):
                needed=permission.get(method) if isinstance(permission,dict) else permission
                groups.setdefault(group,[]).append({'method':method,'path':path,'permission':needed or 'any authenticated user'})
        return render_template('api.html',api_tokens=tokens,now_utc=now(),new_api_token=session.pop('new_api_token',None),endpoint_groups=groups)