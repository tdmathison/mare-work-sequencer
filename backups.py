"""Portable case backups: nested RAW packages plus validated workbench metadata."""
import hashlib,io,json,re,shutil,stat,tempfile,zipfile,sqlite3
from pathlib import Path,PurePosixPath
from flask import request,g,render_template,send_file,flash,redirect
from indicators import load_table,validate_sections,DEFAULT_COLUMNS
from references import load_references
from reporting import SECTIONS,is_backup
from mip import CATEGORIES
SCHEMA='mare-case-backup/1'
MAX_TOTAL=2*1024**3
MAX_FILE=256*1024**2
MAX_METADATA=64*1024**2

def json_bytes(value):return json.dumps(value,ensure_ascii=False,indent=2).encode('utf-8')
def safe_name(name):
    parts=name.rstrip('/').split('/')
    if not name or name.startswith('/') or '\\' in name or ':' in name or '\x00' in name or any(part in ('','..','.') for part in parts):raise ValueError('The archive contains an unsafe path.')
    return parts

def checked_members(archive):
    members={}
    if len(archive.infolist())>100000:raise ValueError('Too many archive entries.')
    total=0
    for info in archive.infolist():
        safe_name(info.filename)
        if info.filename in members or info.flag_bits&1 or stat.S_ISLNK(info.external_attr>>16):raise ValueError('Duplicate, encrypted, or symbolic-link entries are not supported.')
        total+=info.file_size
        if info.file_size>MAX_FILE or total>MAX_TOTAL:raise ValueError('Backup exceeds the import size limits.')
        members[info.filename]=info
    return members,total

def read_json(archive,name):
    if archive.getinfo(name).file_size>MAX_METADATA:raise ValueError('Backup metadata is too large.')
    result=json.loads(archive.read(name))
    if not isinstance(result,dict):raise ValueError('Invalid backup metadata.')
    return result

def text(value,limit=1000000):
    if not isinstance(value,str) or len(value)>limit:raise ValueError('Invalid text in backup metadata.')
    return value

def records(meta,name,fields):
    values=meta.get('records',{}).get(name,[])
    if not isinstance(values,list) or len(values)>100000:raise ValueError('Invalid case records.')
    result=[]
    for row in values:
        if not isinstance(row,dict):raise ValueError('Invalid case record.')
        out={}
        for field,default in fields.items():
            value=row.get(field,default)
            if isinstance(default,int):
                if not isinstance(value,int):raise ValueError('Invalid numeric case record.')
            else:value=text(value if value is not None else '')
            out[field]=value
        result.append(out)
    return result

def validate_metadata(meta):
    if meta.get('schema')!='mare-case-state/1':raise ValueError('Unsupported case metadata version.')
    c=meta['case'];text(c['name'],200);text(c.get('description',''));text(c.get('number',''),200)
    if not c['name'].strip() or c.get('stage') not in range(4):raise ValueError('Invalid source case.')
    if c.get('external_system','') not in ('','Vortex','XSIAM','JIRA'):raise ValueError('Invalid external case system.')
    text(c.get('external_number',''),200)
    if bool(c.get('external_system'))!=bool(c.get('external_number')):raise ValueError('Invalid external case reference.')
    from reporting import valid_report_path
    if c.get('report_path') and not valid_report_path(c['report_path']):raise ValueError('Invalid current report path.')
    sections=validate_sections(meta['indicators']['sections'])
    refs=meta['references']['rows']
    if not isinstance(refs,list) or len(refs)>10000 or any(not isinstance(r,list) or len(r)!=2 or any(not isinstance(v,str) or len(v)>4000 for v in r) for r in refs):raise ValueError('Invalid references table.')
    clean={
      'notes':records(meta,'notes',{'title':'','body':'','author':'','created':'','include_export':0}),
      'tasks':records(meta,'tasks',{'title':'','body':'','state':'Not Started','priority':'Normal','created':''}),
      'history':records(meta,'history',{'stage':0,'author':'','created':'','outcome':'Done','reason':''}),
      'deferred':records(meta,'deferred',{'stage':0,'reason':'','resolved':0}),
      'readiness':records(meta,'readiness',{'category':'','status':'Pending','reason':''}),
      'artifacts':records(meta,'artifacts',{'path':'','description':''})}
    for row in clean['notes']:
        if row['include_export'] not in (0,1):raise ValueError('Invalid note state.')
    for row in clean['tasks']:
        if row['state'] not in ('Not Started','In Progress','Completed') or row['priority'] not in ('Low','Normal','High','Critical'):raise ValueError('Invalid task state.')
        text(row['title'],200)
    for row in clean['history']+clean['deferred']:
        if row['stage'] not in range(4):raise ValueError('Invalid history stage.')
    for row in clean['deferred']:
        if row['resolved'] not in (0,1):raise ValueError('Invalid deferred state.')
    if len({r['category'] for r in clean['readiness']})!=len(clean['readiness']) or len({r['stage'] for r in clean['deferred']})!=len(clean['deferred']):raise ValueError('Duplicate case records.')
    for row in clean['readiness']:
        if row['category'] not in CATEGORIES or row['status'] not in ('Pending','Populated','Not applicable'):raise ValueError('Invalid readiness category.')
    if len({r['path'] for r in clean['artifacts']})!=len(clean['artifacts']):raise ValueError('Duplicate artifact paths.')
    images=meta.get('images',[])
    if not isinstance(images,list) or len(images)>10000:raise ValueError('Invalid report image metadata.')
    names=set()
    for image in images:
        if (image['section'] not in SECTIONS and image['section']!='task-draft' and not re.fullmatch(r'task-[0-9]+',image['section'])) or not re.fullmatch(r'report-image-[a-f0-9]{32}\.png',image['name']) or image['name'] in names or not isinstance(image['figure'],int) or image['figure']<1:raise ValueError('Invalid report image metadata.')
        names.add(image['name'])
    sequence=meta.get('figure_sequence',0)
    if not isinstance(sequence,int) or not 0<=sequence<9223372036854775807:raise ValueError('Invalid figure sequence.')
    return c,sections,refs,clean,images,max([sequence]+[i['figure'] for i in images])

def register_backups(app,ROOT,db,case,package,ensure_package,build_archive,allocate,audit,now):
    def case_metadata(cid):
        c=case(cid)
        data={'schema':'mare-case-state/1','case':{key:c[key] for key in ('number','name','description','stage','external_system','external_number','created','report_path')},'records':{},'indicators':load_table(db,cid),'references':load_references(db,cid)}
        owner=db().execute('SELECT username,user_uuid FROM users WHERE id=?',(c['owner'],)).fetchone()
        data['case']['assigned_user']=dict(owner) if owner else None
        for key in ('description','external_system','external_number'):data['case'][key]=data['case'][key] or ''
        for table in ('notes','tasks','history','deferred','readiness','artifacts'):
            data['records'][table]=[{k:row[k] for k in row.keys() if k not in ('id','case_id','usage')} for row in db().execute(f'SELECT * FROM {table} WHERE case_id=?',(cid,))]
        data['records']['artifacts']=[r for r in data['records']['artifacts'] if (package(cid)/r['path']).is_file() and r['path'].split('/')[0] in CATEGORIES and not is_backup(r['path'])]
        data['images']=[dict(row) for row in db().execute('SELECT section,name,figure FROM report_images WHERE case_id=?',(cid,)) if (package(cid)/'reports/sections/assets'/row['name']).is_file()]
        seq=db().execute('SELECT value FROM figure_sequence WHERE case_id=?',(cid,)).fetchone();data['figure_sequence']=seq[0] if seq else 0
        return data
    def case_backup(cid,email_safe=False):
        raw,name=build_archive(cid,'raw');out=tempfile.SpooledTemporaryFile(max_size=8*1024**2)
        try:
            meta=case_metadata(cid);renamed={}
            with zipfile.ZipFile(raw) as source:
                manifest=read_json(source,name+'/manifest.json')
                if email_safe:
                    for item in manifest['files']:
                        if item['path'].lower().endswith('.py'):renamed[item['path']]=item['path'][:-3]+'_py.txt'
                    paths=[renamed.get(item['path'],item['path']) for item in manifest['files']]
                    if len(paths)!=len(set(paths)):raise ValueError('Python filename conversion would overwrite another file. Rename the conflicting asset first.')
                    for record in meta['records']['artifacts']:record['path']=renamed.get(record['path'],record['path'])
                    meta['file_name_encoding']='python-email-v1'
                data=json_bytes(meta)
                if len(data)>MAX_METADATA:raise ValueError('Case metadata exceeds the backup limit.')
                with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED) as target:
                    for info in source.infolist():
                        if info.filename==name+'/manifest.json':continue
                        rel=info.filename[len(name)+1:];destination=name+'/'+renamed.get(rel,rel)
                        with source.open(info) as src,target.open(destination,'w') as dst:shutil.copyfileobj(src,dst)
                    for item in manifest['files']:item['path']=renamed.get(item['path'],item['path'])
                    target.writestr(name+'/case-data.json',data)
                    manifest['files'].append({'path':'case-data.json','sha256':hashlib.sha256(data).hexdigest(),'size':len(data)})
                    target.writestr(name+'/manifest.json',json_bytes(manifest))
            if out.tell()>MAX_FILE:raise ValueError('The case ZIP exceeds the 256 MiB import limit.')
            out.seek(0)
            with zipfile.ZipFile(out) as archive:checked_members(archive)
            out.seek(0);return out,name
        except Exception:out.close();raise
        finally:raw.close()

    @app.post('/cases/<int:cid>/backup')
    def backup_single_export(cid):
        case(cid)
        if db().execute("SELECT 1 FROM report_jobs WHERE case_id=? AND status IN ('queued','running')",(cid,)).fetchone():flash('Wait for report generation to finish before backing up this case.');return redirect('/')
        try:out,name=case_backup(cid,True)
        except ValueError as exc:flash(str(exc));return redirect('/')
        audit(f'Backed up RAW case {cid} with Python filenames converted for email')
        response=send_file(out,as_attachment=True,download_name=name+'-backup.zip',mimetype='application/zip');response.call_on_close(out.close);return response

    @app.post('/account/database-backup')
    def database_backup():
        if g.user['role']!='Administrator':
            from flask import abort
            abort(403)
        connection=db();connection.execute('BEGIN IMMEDIATE')
        out=tempfile.SpooledTemporaryFile(max_size=8*1024**2)
        try:
            if connection.execute("SELECT 1 FROM report_jobs WHERE status IN ('queued','running')").fetchone():connection.rollback();out.close();flash('Wait for report generation to finish before creating the database backup.');return redirect('/account')
            with tempfile.TemporaryDirectory(prefix='mare-database-') as directory:
                snapshot=Path(directory)/'workflow.sqlite3'
                # Read through a second connection while the write reservation prevents database changes.
                source=sqlite3.connect(ROOT/'workflow.sqlite3');destination=sqlite3.connect(snapshot)
                try:source.backup(destination)
                finally:source.close();destination.close()
                with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED) as archive:
                    archive.write(snapshot,'data/workflow.sqlite3')
                    for file in sorted(ROOT.rglob('*')):
                        rel=file.relative_to(ROOT)
                        if file.is_symlink() or not file.is_file() or rel.parts[0].startswith(('case-import-','report-jobs')) or file.name in ('.backup.lock','workflow.sqlite3','workflow.sqlite3-wal','workflow.sqlite3-shm','workflow.sqlite3-journal'):continue
                        archive.write(file,Path('data')/rel)
            connection.commit();out.seek(0);audit('Created full database and MIP content backup')
            response=send_file(out,as_attachment=True,download_name='MARE-installation-backup-'+now()[:19].replace(':','-')+'.zip',mimetype='application/zip');response.call_on_close(out.close);return response
        except Exception:connection.rollback();out.close();raise

    @app.get('/import-export')
    def import_export_page():return render_template('import_export.html',case_count=db().execute('SELECT count(*) FROM cases').fetchone()[0])
    @app.post('/import-export/export')
    def backup_export():
        if db().execute("SELECT 1 FROM report_jobs WHERE status IN ('queued','running')").fetchone():flash('Wait for report generation to finish before exporting the backup.');return redirect('/import-export')
        out=tempfile.SpooledTemporaryFile(max_size=8*1024**2)
        try:
            index={'schema':SCHEMA,'created':now(),'cases':[]};total=0
            with zipfile.ZipFile(out,'w',zipfile.ZIP_STORED) as outer:
                for row in db().execute('SELECT id FROM cases ORDER BY id').fetchall():
                    cid=row['id'];inner,name=case_backup(cid)
                    try:
                        inner.seek(0)
                        with zipfile.ZipFile(inner) as check:_,size=checked_members(check)
                        total+=size
                        if total>MAX_TOTAL or len(index['cases'])>=1000:raise ValueError('Backup exceeds the import limits (1,000 cases or 2 GiB expanded).')
                        inner.seek(0);path=f'cases/{cid}.zip';digest=hashlib.sha256();length=0
                        with outer.open(path,'w') as destination:
                            while chunk:=inner.read(1024**2):destination.write(chunk);digest.update(chunk);length+=len(chunk)
                        if length>MAX_FILE:raise ValueError('A case package exceeds 256 MiB compressed.')
                        index['cases'].append({'path':path,'size':length,'sha256':digest.hexdigest()})
                    finally:inner.close()
                outer.writestr('backup.json',json_bytes(index))
            if out.tell()>1024**3:raise ValueError('Backup exceeds the 1 GiB upload limit.')
            out.seek(0);audit('Exported full RAW case backup: '+str(len(index['cases']))+' cases')
            response=send_file(out,as_attachment=True,download_name='MARE-case-backup-'+now()[:19].replace(':','-')+'.zip',mimetype='application/zip');response.call_on_close(out.close);return response
        except ValueError as exc:out.close();flash(str(exc));return redirect('/import-export')
        except Exception:out.close();raise

    @app.post('/import-export/import-raw')
    @app.post('/import-export/import')
    def backup_import():
        upload=request.files.get('backup')
        if not upload:flash('Choose a MARE case backup ZIP.');return redirect('/import-export')
        created=[];connection=db()
        try:
            with tempfile.TemporaryDirectory(dir=ROOT,prefix='case-import-') as temporary:
                temporary=Path(temporary);incoming=temporary/'backup.zip';upload.save(incoming);plans=[];total=0
                single=request.path.endswith('/import-raw')
                if single:
                    raw_upload=temporary/'single.zip';incoming.rename(raw_upload)
                    digest=hashlib.sha256();size=0
                    with raw_upload.open('rb') as source:
                        while chunk:=source.read(1024**2):digest.update(chunk);size+=len(chunk)
                    with zipfile.ZipFile(incoming,'w',zipfile.ZIP_STORED) as wrapper:
                        wrapper.write(raw_upload,'cases/1.zip')
                        wrapper.writestr('backup.json',json_bytes({'schema':SCHEMA,'cases':[{'path':'cases/1.zip','sha256':digest.hexdigest(),'size':size}]}))
                with zipfile.ZipFile(incoming) as outer:
                    members,_=checked_members(outer);index=read_json(outer,'backup.json')
                    entries=index.get('cases')
                    if index.get('schema')!=SCHEMA or not isinstance(entries,list) or len(entries)>1000:raise ValueError('Use an archive created by Export all cases.')
                    paths=[e['path'] for e in entries]
                    if len(paths)!=len(set(paths)) or set(members)!=set(paths+['backup.json']):raise ValueError('Unexpected or duplicate files in backup archive.')
                    for n,entry in enumerate(entries):
                        path=entry['path']
                        if not re.fullmatch(r'cases/[0-9]+\.zip',path):raise ValueError('Invalid case package path.')
                        raw=temporary/f'{n}.zip';digest=hashlib.sha256();size=0
                        with outer.open(path) as src,raw.open('wb') as dst:
                            while chunk:=src.read(1024**2):dst.write(chunk);digest.update(chunk);size+=len(chunk)
                        if digest.hexdigest()!=entry['sha256'] or size!=entry['size']:raise ValueError('Case package checksum failed.')
                        with zipfile.ZipFile(raw) as archive:
                            files,expanded=checked_members(archive);total+=expanded
                            if total>MAX_TOTAL:raise ValueError('Backup exceeds the 2 GiB expanded limit.')
                            manifests=[p for p in files if p.endswith('/manifest.json') and len(safe_name(p))==2]
                            if len(manifests)!=1:raise ValueError('A RAW case manifest is missing.')
                            manifest=read_json(archive,manifests[0]);prefix=manifests[0].split('/')[0]
                            if manifest.get('schema')!='mare-mip/2.0' or manifest.get('archive_type')!='raw' or manifest.get('package_id')!=prefix:raise ValueError('Only RAW case packages are supported.')
                            declared={};actual=set()
                            for item in manifest['files']:
                                rel=item['path'];safe_name(rel)
                                if rel in declared:raise ValueError('Duplicate manifest paths.')
                                declared[rel]=item
                            folder=temporary/f'case-{n}'/'mip';folder.mkdir(parents=True)
                            for filename,info in files.items():
                                parts=safe_name(filename)
                                if parts[0]!=prefix or len(parts)<2:raise ValueError('Unexpected RAW package root.')
                                rel='/'.join(parts[1:])
                                if rel not in ('README.md','manifest.json','case-data.json') and (parts[1] not in CATEGORIES or is_backup(rel)):raise ValueError('Unsupported RAW package content.')
                                if parts[1] in CATEGORIES and len(parts)==2 and not info.is_dir():raise ValueError('Package categories must be directories.')
                                if info.is_dir():continue
                                if rel=='manifest.json':continue
                                actual.add(rel)
                                if rel not in declared:raise ValueError('Unlisted package file.')
                                digest=hashlib.sha256();size=0;destination=folder/rel
                                destination.parent.mkdir(parents=True,exist_ok=True)
                                with archive.open(info) as src,destination.open('wb') as dst:
                                    while chunk:=src.read(1024**2):dst.write(chunk);digest.update(chunk);size+=len(chunk)
                                if digest.hexdigest()!=declared[rel]['sha256'] or size!=declared[rel]['size']:raise ValueError('RAW package file checksum failed.')
                            if actual!=set(declared):raise ValueError('Missing RAW package file.')
                            meta=read_json(archive,prefix+'/case-data.json');validated=validate_metadata(meta)
                            for image in validated[4]:
                                if not (folder/'reports/sections/assets'/image['name']).is_file():raise ValueError('A registered report image is missing.')
                            for artifact in validated[3]['artifacts']:
                                safe_name(artifact['path'])
                                if artifact['path'] not in actual:raise ValueError('Artifact metadata references a missing file.')
                            if single or meta.get('file_name_encoding')=='python-email-v1':
                                renames={rel:rel[:-7]+'.py' for rel in actual if rel.endswith('_py.txt')}
                                if len({renames.get(rel,rel) for rel in actual})!=len(actual):raise ValueError('Python filename restoration would overwrite another file.')
                                for original,replacement in renames.items():(folder/original).rename(folder/replacement)
                                for artifact in validated[3]['artifacts']:artifact['path']=renames.get(artifact['path'],artifact['path'])
                            for generated in ('README.md','case-data.json'):(folder/generated).unlink(missing_ok=True)
                            for category in CATEGORIES:(folder/category).mkdir(exist_ok=True)
                            plans.append((folder.parent,validated))
                connection.execute('BEGIN IMMEDIATE')
                for folder,(c,sections,refs,rows,images,sequence) in plans:
                    number=allocate(connection)
                    identity=c.get('assigned_user');owner=None
                    if isinstance(identity,dict) and isinstance(identity.get('user_uuid'),str) and isinstance(identity.get('username'),str):
                        match=connection.execute('SELECT id FROM users WHERE user_uuid=? AND username=?',(identity['user_uuid'],identity['username'])).fetchone()
                        if match:owner=match[0]
                    cid=connection.execute('INSERT INTO cases(number,name,description,stage,created,owner,external_system,external_number,creator,creator_username,owner_required) VALUES(?,?,?,?,?,?,?,?,?,?,1)',(number,c['name'],c.get('description',''),c['stage'],now(),owner,c.get('external_system',''),c.get('external_number',''),g.user['id'],g.user['username'])).lastrowid
                    connection.execute('UPDATE cases SET report_path=? WHERE id=?',(c.get('report_path',''),cid))
                    for table,values in rows.items():
                        for record in values:
                            if table=='tasks':record['done']=int(record['state']=='Completed')
                            if table=='artifacts':record['usage']=''
                            keys=list(record);sql=f'INSERT INTO {table}(case_id,'+','.join(keys)+') VALUES('+','.join('?' for _ in range(len(keys)+1))+')'
                            connection.execute(sql,[cid]+[record[key] for key in keys])
                    flat=[row for section in sections for row in section['rows']]
                    connection.execute('INSERT INTO indicator_tables VALUES(?,?,?,0)',(cid,json.dumps(DEFAULT_COLUMNS),json.dumps(flat)))
                    connection.execute('INSERT INTO indicator_sections VALUES(?,?)',(cid,json.dumps(sections)))
                    connection.execute('INSERT INTO reference_tables VALUES(?,?,0)',(cid,json.dumps(refs)))
                    for image in images:
                        if image['section'].startswith('task-'):
                            task=connection.execute('SELECT id FROM tasks WHERE case_id=? AND instr(body,?)>0 ORDER BY id LIMIT 1',(cid,image['name'])).fetchone()
                            image['section']=f'task-{task[0]}' if task else 'task-draft'
                        connection.execute('INSERT INTO report_images(case_id,section,name,figure) VALUES(?,?,?,?)',(cid,image['section'],image['name'],image['figure']))
                    connection.execute('INSERT INTO figure_sequence VALUES(?,?)',(cid,sequence))
                    destination=ROOT/'cases'/str(cid)
                    if destination.exists():raise ValueError('An existing case directory conflicts with this import.')
                    destination.parent.mkdir(exist_ok=True);folder.rename(destination);created.append(destination)
                    connection.execute('INSERT INTO audit(actor,action,created) VALUES(?,?,?)',(g.user['username'],f'Imported case {number} from {c.get("number", "unknown")} (source stage {c["stage"]})',now()))
                connection.commit()
            flash(f'Imported {len(plans)} cases. Cases retain their exported stage. Assign an owner where unmatched to resume work.');return redirect('/')
        except (ValueError,KeyError,TypeError,zipfile.BadZipFile,UnicodeError,RuntimeError,RecursionError,OverflowError,OSError) as exc:
            connection.rollback()
            for folder in created:shutil.rmtree(folder)
            flash('Import failed; no cases were added. '+str(exc));return redirect('/import-export')
        except Exception:
            connection.rollback()
            for folder in created:shutil.rmtree(folder)
            raise

    return {'case_backup':case_backup}
