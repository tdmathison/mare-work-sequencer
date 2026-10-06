import io,re,secrets
from pathlib import Path
from flask import request,send_file,abort
from reporting import SECTIONS,is_backup
from mip import OPTIONAL_TEMPLATES,REPORT_TEMPLATE

REPORT_EDITOR_MARKDOWN={f'reports/sections/{key}.md' for key in SECTIONS}
REPORT_EDITOR_MARKDOWN.add('reports/sections/threat_overview.md')
PROTECTED_REPORT_MARKDOWN=REPORT_EDITOR_MARKDOWN|{'reports/indicators-of-compromise.md'}
INTERNAL_REPORT_SCAFFOLDS={'reports/executive-summary.md':OPTIONAL_TEMPLATES['reports/executive-summary.md'],'reports/malware-analysis-report.md':REPORT_TEMPLATE}

def hidden_internal_markdown(rel,path):
    if rel in PROTECTED_REPORT_MARKDOWN:return True
    template=INTERNAL_REPORT_SCAFFOLDS.get(rel)
    return template is not None and path.read_text(errors='replace').strip()==template.strip()

def register_assets(app,db,case,package,ensure_package,safe_path,mark_pending,audit):
    with app.app_context():
        db().execute('CREATE TABLE IF NOT EXISTS report_images(case_id INTEGER,section TEXT,name TEXT,PRIMARY KEY(case_id,name))')
        if 'figure' not in {r[1] for r in db().execute('PRAGMA table_info(report_images)')}:
            db().execute('ALTER TABLE report_images ADD COLUMN figure INTEGER')
            counts={}
            for row in db().execute('SELECT rowid,case_id FROM report_images ORDER BY rowid').fetchall():
                counts[row['case_id']]=counts.get(row['case_id'],0)+1
                db().execute('UPDATE report_images SET figure=? WHERE rowid=?',(counts[row['case_id']],row['rowid']))
        db().execute('CREATE TABLE IF NOT EXISTS figure_sequence(case_id INTEGER PRIMARY KEY,value INTEGER NOT NULL)')
        db().execute('INSERT OR IGNORE INTO figure_sequence SELECT case_id,MAX(figure) FROM report_images GROUP BY case_id')
        db().commit()
    def busy(cid):return db().execute("SELECT 1 FROM report_jobs WHERE case_id=? AND status IN ('queued','running')",(cid,)).fetchone()
    def remove_image(cid,name):
        path=safe_path(cid,'reports/sections/assets/'+name)
        path.unlink(missing_ok=True)
        for key in SECTIONS:
            section=package(cid)/'reports/sections'/f'{key}.md'
            if section.exists():section.write_text(re.sub(r'!\[[^\]]*\]\(assets/'+re.escape(name)+r'(?:\s+"[^"]*")?\)','',section.read_text()))
        for task in db().execute('SELECT id,body FROM tasks WHERE case_id=?',(cid,)).fetchall():
            body=re.sub(r'!\[[^\]]*\]\(assets/'+re.escape(name)+r'(?:\s+"[^"]*")?\)','',task['body'] or '')
            if body!=task['body']:db().execute('UPDATE tasks SET body=? WHERE id=?',(body,task['id']))
        db().execute('DELETE FROM report_images WHERE case_id=? AND name=?',(cid,name));db().commit()
        mark_pending(cid,'reports/sections/assets/'+name)
    @app.get('/cases/<int:cid>/report-images')
    def report_images(cid):
        case(cid)
        return {'images':[dict(row) for row in db().execute('SELECT section,name,figure FROM report_images WHERE case_id=? ORDER BY rowid',(cid,)) if (package(cid)/'reports/sections/assets'/row['name']).is_file()]}
    @app.get('/cases/<int:cid>/report-images/<name>')
    def report_image(cid,name):
        case(cid)
        if not re.fullmatch(r'report-image-[a-f0-9]{32}\.png',name):abort(404)
        path=safe_path(cid,'reports/sections/assets/'+name)
        if not path.is_file():abort(404)
        return send_file(path,mimetype='image/png')
    @app.post('/cases/<int:cid>/report-images')
    def upload_report_image(cid):
        case(cid)
        if busy(cid):return {'error':'Wait for report generation to finish before changing images.'},409
        section=request.form.get('section','')
        if section not in SECTIONS and section!='task-draft' and not re.fullmatch(r'task-[0-9]+',section):return {'error':'Choose a report section.'},400
        if section.startswith('task-') and section!='task-draft' and not db().execute('SELECT 1 FROM tasks WHERE id=? AND case_id=?',(int(section[5:]),cid)).fetchone():return {'error':'Task not found.'},404
        file=request.files.get('image')
        if not file:return {'error':'Choose an image.'},400
        raw=file.read(10*1024*1024+1)
        if len(raw)>10*1024*1024:return {'error':'Images are limited to 10 MiB.'},400
        try:
            from PIL import Image,ImageOps
            with Image.open(io.BytesIO(raw)) as image:
                if image.width*image.height>20000000:raise ValueError('Too large')
                image.load();image=ImageOps.exif_transpose(image)
                clean=image.convert('RGBA' if image.mode in ('RGBA','LA','P') else 'RGB')
                options={key:image.info[key] for key in ('dpi','icc_profile') if key in image.info}
                encoded=io.BytesIO();clean.save(encoded,format='PNG',**options)
        except Exception:return {'error':'Upload a readable image of at most 20 megapixels.'},400
        ensure_package(cid);folder=package(cid)/'reports/sections/assets';folder.mkdir(parents=True,exist_ok=True)
        name='report-image-'+secrets.token_hex(16)+'.png';(folder/name).write_bytes(encoded.getvalue())
        with db():
            db().execute('INSERT INTO figure_sequence VALUES(?,1) ON CONFLICT(case_id) DO UPDATE SET value=value+1',(cid,))
            figure=db().execute('SELECT value FROM figure_sequence WHERE case_id=?',(cid,)).fetchone()[0]
            db().execute('INSERT INTO report_images(case_id,section,name,figure) VALUES(?,?,?,?)',(cid,section,name,figure))
        mark_pending(cid,'reports/sections/assets/'+name);audit(f'Added report image for case {cid}')
        return {'figure':figure,'name':name,'markdown_url':'assets/'+name,'url':f'/cases/{cid}/report-images/{name}','section':section}
    @app.post('/cases/<int:cid>/report-images/<name>/delete')
    def delete_report_image(cid,name):
        case(cid)
        if busy(cid):return {'error':'Wait for report generation to finish before deleting images.'},409
        if not db().execute('SELECT 1 FROM report_images WHERE case_id=? AND name=?',(cid,name)).fetchone():abort(404)
        remove_image(cid,name);audit(f'Deleted report image for case {cid}')
        return {'deleted':True}
    @app.get('/cases/<int:cid>/assets')
    def asset_list(cid):
        case(cid);category=request.args.get('category','supporting')
        from mip import CATEGORIES
        if category not in CATEGORIES:abort(400)
        root=ensure_package(cid)
        files=[]
        for path in sorted((root/category).rglob('*')):
            rel=path.relative_to(root).as_posix()
            if not path.is_file() or path.is_symlink() or is_backup(rel):continue
            if hidden_internal_markdown(rel,path):continue
            files.append({'path':rel,'size':path.stat().st_size})
        return {'files':files}
    @app.post('/cases/<int:cid>/assets/delete')
    def delete_asset(cid):
        case(cid);rel=request.form.get('path','')
        from mip import CATEGORIES
        if rel.split('/')[0] not in CATEGORIES:abort(400)
        if busy(cid):return {'error':'Wait for report generation to finish before deleting assets.'},409
        path=safe_path(cid,rel)
        if not path.is_file():abort(404)
        if rel in PROTECTED_REPORT_MARKDOWN:abort(400)
        template=INTERNAL_REPORT_SCAFFOLDS.get(rel)
        if template is not None and path.read_text(errors='replace').strip()==template.strip():abort(400)
        if rel.startswith('reports/sections/assets/'):remove_image(cid,path.name)
        else:path.unlink();mark_pending(cid,rel)
        db().execute('DELETE FROM artifacts WHERE case_id=? AND path=?',(cid,rel));db().commit()
        audit(f'Deleted case asset {cid}: {rel}')
        return {'deleted':True}
