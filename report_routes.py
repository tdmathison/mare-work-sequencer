import os
import json
import secrets
import time
import threading
import shutil
from pathlib import Path
from flask import request, g, redirect, flash, abort, send_file
from indicators import load_table, report_table
from references import load_references
from reporting import SECTIONS, TOKENS, OUTPUT, report_filename, current_report, template_sections, fill_template, is_backup, validate_docx, md_table, convert_docx_to_pdf


def register_reporting(app, ROOT, db, run, case, package, ensure_package, mark_pending, audit, now):
    with app.app_context():
        db().executescript('''
        CREATE TABLE IF NOT EXISTS report_settings(user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,template_id TEXT DEFAULT '');
        CREATE TABLE IF NOT EXISTS word_templates(id TEXT PRIMARY KEY,user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,name TEXT,created TEXT);
        CREATE TABLE IF NOT EXISTS report_jobs(id TEXT PRIMARY KEY,case_id INTEGER REFERENCES cases(id),user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,status TEXT,progress TEXT,started INTEGER,updated INTEGER);
        CREATE UNIQUE INDEX IF NOT EXISTS one_report_job_per_case ON report_jobs(case_id) WHERE status IN ('queued','running');
        ''')
        if db().execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='ai_settings'").fetchone():
            db().execute('INSERT OR IGNORE INTO report_settings SELECT user_id,template_id FROM ai_settings')
            db().execute('DROP TABLE ai_settings')
        db().commit()
    (ROOT/'api-keys.key').unlink(missing_ok=True)

    def settings(uid):
        row = db().execute('SELECT * FROM report_settings WHERE user_id=?', (uid,)).fetchone()
        return dict(row) if row else {'template_id': ''}

    def manual(cid):
        root = ensure_package(cid)
        result = {}
        for key in TOKENS:
            path = root/'reports/sections'/f'{key}.md'
            if key == 'key_findings' and not path.exists():
                path = root/'reports/sections/threat_overview.md'
            result[key] = path.read_text() if path.exists() else ''
        return result

    def expired():
        cutoff = int(time.time())-900
        run("UPDATE report_jobs SET status='failed',progress=? WHERE status IN ('queued','running') AND updated<?",
            (json.dumps(['Job interrupted or timed out. The existing report was preserved. Retry generation.']), cutoff))

    def job_data(cid):
        expired()
        row = db().execute('SELECT * FROM report_jobs WHERE case_id=? ORDER BY started DESC,rowid DESC LIMIT 1', (cid,)).fetchone()
        if not row:
            return None
        return {'id': row['id'], 'status': row['status'], 'messages': json.loads(row['progress']), 'updated': row['updated']}

    def report_outputs(cid):
        root = package(cid)
        word = Path(current_report(case(cid), root))
        return [{'path': path.as_posix(), 'size': (root/path).stat().st_size} for path in (word, word.with_suffix('.pdf')) if (root/path).is_file()]

    def mitre_mappings(cid):
        root = package(cid)/'mappings'
        return {key: (root/filename).read_text(encoding='utf-8') if (root/filename).is_file() else '' for key, filename in (('attack', 'mitre-attack.md'), ('mbc', 'mitre-mbc.md'))}

    @app.context_processor
    def report_context():
        if not g.get('user'):
            return {}
        s = settings(g.user['id'])
        return {'report_config': {'template_id': s['template_id']}, 'word_templates': db().execute('SELECT * FROM word_templates WHERE user_id=? ORDER BY created DESC', (g.user['id'],)).fetchall(), 'report_sections': TOKENS, 'template_sections': TOKENS}

    @app.post('/account/templates')
    def upload_template():
        f = request.files.get('template')
        if not f or not f.filename.lower().endswith('.docx'):
            flash('Upload a DOCX Word template.')
            return redirect('/account')
        directory = ROOT/'users'/str(g.user['id'])/'templates'
        directory.mkdir(parents=True, exist_ok=True)
        tid = secrets.token_hex(16)
        path = directory/(tid+'.docx')
        f.save(path)
        try:
            if path.stat().st_size > 10*1024*1024:
                raise ValueError('Template limit is 10 MiB.')
            found = template_sections(path)
            missing = set(TOKENS)-found
            if missing:
                raise ValueError('Missing report sections: '+', '.join(TOKENS[k] for k in sorted(
                    missing))+'. Add matching headings or standalone placeholders shown below.')
        except Exception as exc:
            path.unlink(missing_ok=True)
            flash(str(exc) if isinstance(exc, ValueError)
                  else 'The Word template could not be read.')
            return redirect('/account')
        run('INSERT INTO word_templates VALUES(?,?,?,?)',
            (tid, g.user['id'], Path(f.filename).name[:200], now()))
        run('INSERT OR REPLACE INTO report_settings VALUES(?,?)',
            (g.user['id'], tid))
        audit('Uploaded own Word template')
        flash('Template saved and selected.')
        return redirect('/account')

    @app.get('/account/templates/<tid>')
    def download_template(tid):
        row = db().execute('SELECT * FROM word_templates WHERE id=? AND user_id=?',
                           (tid, g.user['id'])).fetchone()
        if not row:
            abort(404)
        return send_file(ROOT/'users'/str(g.user['id'])/'templates'/(tid+'.docx'), as_attachment=True, download_name=row['name'])

    @app.post('/account/templates/<tid>/delete')
    def delete_template(tid):
        row = db().execute('SELECT * FROM word_templates WHERE id=? AND user_id=?',
                           (tid, g.user['id'])).fetchone()
        if not row:
            abort(404)
        run('DELETE FROM word_templates WHERE id=?', (tid,))
        run("UPDATE report_settings SET template_id='' WHERE user_id=? AND template_id=?",
            (g.user['id'], tid))
        (ROOT/'users'/str(g.user['id'])/'templates' /
         (tid+'.docx')).unlink(missing_ok=True)
        flash('Template removed.')
        return redirect('/account')

    @app.get('/cases/<int:cid>/report-data')
    def report_data(cid):
        c = case(cid)
        root = package(cid)
        path = current_report(c, root)
        return {'sections': manual(cid), 'sources': [], 'skipped': [], 'job': job_data(cid), 'report_exists': (root/path).exists(), 'report_path': path, 'report_files': report_outputs(cid), 'pdf_converter_available': bool(shutil.which('libreoffice') or shutil.which('soffice')), 'mitre_mappings': mitre_mappings(cid)}

    def persist_sections(cid, form=None):
        form = form or request.form
        root = ensure_package(cid)/'reports/sections'
        root.mkdir(exist_ok=True)
        for key in TOKENS:
            if key not in SECTIONS:
                continue
            value = form.get(key, form.get('threat_overview', '')
                             if key == 'key_findings' else '')
            if len(value) > 100000:
                abort(413)
            (root/(key+'.md')).write_text(value)
        mark_pending(cid, 'reports/sections')
        return manual(cid)

    @app.post('/cases/<int:cid>/report-sections')
    def save_report_sections(cid):
        case(cid)
        if request.form.get('automatic') == '1' and all(request.form.get(key, '') == manual(cid).get(key, '') for key in SECTIONS):
            return {'saved': True}
        persist_sections(cid, request.form)
        audit(f'Saved report sections for case {cid}')
        return {'saved': True} if request.form.get('ajax') == '1' else redirect(f'/cases/{cid}')

    @app.post('/cases/<int:cid>/mitre-mappings')
    def save_mitre_mappings(cid):
        case(cid)
        if db().execute("SELECT 1 FROM report_jobs WHERE case_id=? AND status IN ('queued','running')", (cid,)).fetchone():
            return {'error': 'Wait for report generation to finish before saving MITRE mappings.'}, 409
        root = ensure_package(cid)/'mappings'
        root.mkdir(exist_ok=True)
        values = {'attack': request.form.get(
            'mitre_attack_markdown', ''), 'mbc': request.form.get('mitre_mbc_markdown', '')}
        if any(len(value) > 100000 for value in values.values()):
            abort(413)
        for key, filename in (('attack', 'mitre-attack.md'), ('mbc', 'mitre-mbc.md')):
            path = root/filename
            value = values[key]
            if value.strip():
                path.write_text(value, encoding='utf-8')
            else:
                path.unlink(missing_ok=True)
        mark_pending(cid, 'mappings/mitre-attack.md')
        audit(f'Saved MITRE mappings for case {cid}')
        return {'saved': True, 'mappings': mitre_mappings(cid)}

    @app.get('/cases/<int:cid>/report-job')
    def report_job(cid):
        c = case(cid)
        root = package(cid)
        path = current_report(c, root)
        return {'job': job_data(cid), 'report_exists': (root/path).exists(), 'report_path': path, 'report_files': report_outputs(cid)}

    def worker(jid, cid, uid, template, snapshot, sections, mode, expected_digest, indicator_snapshot, reference_snapshot, previous_path, output_path, generate_pdf):
        import hashlib

        def progress(message, status='running'):
            row = db().execute('SELECT progress FROM report_jobs WHERE id=?', (jid,)).fetchone()
            messages = json.loads(row['progress'])
            messages.append(message)
            run('UPDATE report_jobs SET progress=?,status=?,updated=? WHERE id=?',
                (json.dumps(messages), status, int(time.time()), jid))
        with app.app_context():
            try:
                progress('Formatting saved Markdown locally.')
                generated = {key: sections.get(key, '').strip() or 'No applicable findings recorded.' for key in (
                    'mitre_attack_mapping', 'mitre_mbc_mapping', 'indicators_of_compromise', 'appendices')}
                for key, name in [('mitre_attack_mapping', 'mitre-attack.md'), ('mitre_mbc_mapping', 'mitre-mbc.md')]:
                    path = package(cid)/'mappings'/name
                    if path.exists():
                        generated[key] = path.read_text(encoding='utf-8')
                generated['appendices'] = sections.get(
                    'appendices', '').strip()
                if load_references(db, cid) != reference_snapshot:
                    raise ValueError(
                        'References changed during generation. Retry with the updated references.')
                generated['indicators_of_compromise'] = md_table(
                    indicator_snapshot['columns'], indicator_snapshot['rows']) if indicator_snapshot['rows'] else 'No indicators have been recorded in the Indicators tab.'
                if report_table(load_table(db, cid)) != indicator_snapshot:
                    raise ValueError(
                        'The indicator table changed during generation. Retry using the updated table.')
                if case(cid)['stage'] not in (1, 2):
                    raise ValueError(
                        'This case is locked. Reopen it before generating a report.')
                if manual(cid) != sections:
                    raise ValueError(
                        'The saved manual report sections changed during generation. The existing report was preserved; retry using the updated sections.')
                report_case = case(cid)
                temp = snapshot/'report.docx'
                fill_template(template, temp, {**sections, **generated}, report_case['number'], report_case['name'], indicators=indicator_snapshot, references=reference_snapshot, assets_root=package(
                    cid)/'reports/sections', external_system=report_case['external_system'], external_number=report_case['external_number'])
                progress('Populating the Word template and saving the report.')
                pdf_temp = snapshot/'report.pdf'
                if generate_pdf:
                    progress('Rendering the report as PDF.')
                    convert_docx_to_pdf(temp, pdf_temp)
                (package(cid)/'reports/indicators-of-compromise.md').unlink(missing_ok=True)
                target = package(cid)/previous_path
                digest = hashlib.sha256(
                    target.read_bytes()).hexdigest() if target.exists() else ''
                if digest != expected_digest:
                    raise ValueError(
                        'The existing report changed during generation. It was preserved; retry after review.')
                if target.exists() and mode == 'backup':
                    folder = package(cid)/'reports/backups'
                    folder.mkdir(exist_ok=True)
                    stamp = now().replace(':', '').replace('+', '_')
                    backup = folder/(stamp+'-'+jid[:8]+'-'+target.name)
                    shutil.copy2(target, backup)
                    progress(
                        'Previous report backed up. Backups are excluded from MIP exports and previews.')
                destination = package(cid)/output_path
                if destination != target and destination.exists():
                    raise ValueError(
                        'The new report filename already exists. Rename that asset before generating.')
                os.replace(temp, destination)
                if generate_pdf:
                    os.replace(pdf_temp, destination.with_suffix('.pdf'))
                else:
                    destination.with_suffix('.pdf').unlink(missing_ok=True)
                if target != destination:
                    target.unlink(missing_ok=True)
                    target.with_suffix('.pdf').unlink(missing_ok=True)
                run('UPDATE cases SET report_path=? WHERE id=?', (output_path, cid))
                if previous_path != output_path:
                    run('DELETE FROM artifacts WHERE case_id=? AND path=?',
                        (cid, previous_path))
                mark_pending(cid, output_path)
                run('INSERT INTO audit(actor,action,created) VALUES(?,?,?)',
                    (str(uid), f'Generated Word report for case {cid}', now()))
                complete = 'Complete. The Word report and its PDF are saved in reports. ' if generate_pdf else 'Complete. The Word report is saved in reports without a PDF. Upload a manually converted PDF to Reports/ when ready. '
                progress(
                    complete+'Finish editing in Word, then upload the final copy before delivery.', 'completed')
            except Exception as exc:
                message = str(exc).strip() or type(exc).__name__
                if not isinstance(exc, ValueError):
                    message = type(exc).__name__+': '+message
                message = message[:500]
                progress(message, 'failed')
            finally:
                shutil.rmtree(snapshot, ignore_errors=True)

    @app.post('/cases/<int:cid>/generate-report')
    def generate_report(cid):
        import hashlib
        c = case(cid)
        uid = g.user['id']
        s = settings(uid)
        data = request.get_json(
            silent=True) if request.is_json else request.form
        if not hasattr(data, 'get'):
            return {'error': 'Request body must be an object.'}, 400
        if isinstance(data, dict) and isinstance(data.get('sections'), dict):
            data = {**data, **data['sections']}
        generation_mode = data.get('generation_mode', 'manual')
        if generation_mode != 'manual':
            return {'error': 'Only local Word report generation is supported.'}, 400
        if not s['template_id']:
            return {'error': 'Select a Word template in Settings first.'}, 400
        template_row = db().execute('SELECT * FROM word_templates WHERE id=? AND user_id=?',
                                    (s['template_id'], uid)).fetchone()
        if not template_row:
            return {'error': 'Select an available template in Settings.'}, 400
        root = ensure_package(cid)
        previous_path = current_report(c, root)
        output_path = 'reports/'+report_filename(c)
        target = root/previous_path
        mode = data.get('previous', '')
        generate_pdf = data.get('generate_pdf', '1') not in ('0', False)
        if output_path != previous_path and (root/output_path).exists():
            return {'error': 'The new report filename already exists. Rename that asset before generating.'}, 409
        if target.exists() and mode not in ('backup', 'overwrite'):
            return {'error': 'Choose whether to back up the existing report before replacement.', 'needs_choice': True}, 409
        expired()
        connection = db()
        connection.execute('BEGIN IMMEDIATE')
        try:
            if connection.execute("SELECT 1 FROM report_jobs WHERE case_id=? AND status IN ('queued','running')", (cid,)).fetchone():
                connection.rollback()
                return {'error': 'A report is already being generated for this case.'}, 409
            jid = secrets.token_hex(16)
            connection.execute('INSERT INTO report_jobs VALUES(?,?,?,?,?,?,?)', (jid, cid, uid, 'queued', json.dumps(
                ['Queued report generation.']), int(time.time()), int(time.time())))
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        snapshot = ROOT/'report-jobs'/jid
        snapshot.mkdir(parents=True, exist_ok=True)
        try:
            sections = persist_sections(cid, data)
            if not any(v.strip() for v in sections.values()):
                raise ValueError(
                    'Enter manual report content before generating a report.')
            template = snapshot/'template.docx'
            shutil.copy2(ROOT/'users'/str(uid)/'templates' /
                         (s['template_id']+'.docx'), template)
            expected = hashlib.sha256(
                target.read_bytes()).hexdigest() if target.exists() else ''
            thread = threading.Thread(target=worker, args=(jid, cid, uid, template, snapshot, sections, mode, expected, report_table(
                load_table(db, cid)), load_references(db, cid), previous_path, output_path, generate_pdf), daemon=True)
            thread.start()
            audit(f'Started report generation for case {cid}')
            return {'job_id': jid}, 202
        except Exception as exc:
            run("UPDATE report_jobs SET status='failed',progress=? WHERE id=?", (json.dumps(
                ['Could not start report generation. '+(str(exc) if isinstance(exc, ValueError) else 'Check saved settings and template.')]), jid))
            shutil.rmtree(snapshot, ignore_errors=True)
            return {'error': str(exc) if isinstance(exc, ValueError) else 'Could not start report generation.'}, 400

    @app.post('/cases/<int:cid>/final-report')
    def upload_final_report(cid):
        case(cid)
        f = request.files.get('report')
        if not f or not f.filename.lower().endswith('.docx'):
            return {'error': 'Select the edited DOCX report.'}, 400
        import tempfile
        directory = ROOT/'report-jobs'
        directory.mkdir(exist_ok=True)
        fd, name = tempfile.mkstemp(suffix='.docx', dir=directory)
        os.close(fd)
        temp = Path(name)
        pdf_temp = temp.with_suffix('.pdf')
        try:
            f.save(temp)
            if temp.stat().st_size > 20*1024*1024:
                raise ValueError('Final report limit is 20 MiB.')
            validate_docx(temp)
            generate_pdf = request.form.get('generate_pdf', '1') != '0'
            if generate_pdf:
                convert_docx_to_pdf(temp, pdf_temp)
            expired()
            connection = db()
            connection.execute('BEGIN IMMEDIATE')
            if connection.execute("SELECT 1 FROM report_jobs WHERE case_id=? AND status IN ('queued','running')", (cid,)).fetchone():
                connection.rollback()
                return {'error': 'Wait for active report generation to finish before uploading an edited copy.'}, 409
            c = case(cid)
            root = ensure_package(cid)
            path = current_report(c, root)
            if not c['report_path'] and not (root/path).exists():
                path = 'reports/'+report_filename(c)
            target = root/path
            if target.exists() and request.form.get('backup') == '1':
                folder = package(cid)/'reports/backups'
                folder.mkdir(exist_ok=True)
                shutil.copy2(target, folder/(now().replace(':', '').replace('+',
                             '_')+'-'+secrets.token_hex(4)+'-'+target.name))
            os.replace(temp, target)
            if generate_pdf:
                os.replace(pdf_temp, target.with_suffix('.pdf'))
            else:
                target.with_suffix('.pdf').unlink(missing_ok=True)
            connection.execute(
                'UPDATE cases SET report_path=? WHERE id=?', (path, cid))
            connection.commit()
            mark_pending(cid, path)
            audit(f'Uploaded edited Word report for case {cid}')
            return {'saved': True, 'report_exists': True, 'report_path': path, 'report_files': report_outputs(cid)}
        except ValueError as exc:
            return {'error': str(exc)}, 400
        except Exception:
            return {'error': 'The edited report could not be saved. Check that it is a valid DOCX.'}, 400
        finally:
            if db().in_transaction:
                db().rollback()
            temp.unlink(missing_ok=True)
            pdf_temp.unlink(missing_ok=True)
    return {'manual': manual, 'settings': settings, 'generate': generate_report, 'final': upload_final_report, 'outputs': report_outputs, 'upload_template': upload_template, 'download_template': download_template, 'delete_template': delete_template}
