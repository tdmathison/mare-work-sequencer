"""SDK -> in-process WSGI REST integration. No live URL or production opt-in exists."""
import io
import json
import zipfile
import pytest
httpx = pytest.importorskip("httpx")
pytest.importorskip("mws_sdk")
from app import app,db
from test_api import make_user, word_template, make_png
from test_explorer_research import configuration
from mws_sdk import MWSClient, MWSConflictError, MWSAuthorizationError


def test_sdk_end_to_end_case_investigation_and_exports(tmp_path):
    uid,headers=make_user('sdk-integration')
    secret=headers['Authorization'].removeprefix('Bearer ')
    with MWSClient('http://isolated.test',secret,transport=httpx.WSGITransport(app=app),retries=0) as sdk:
        assert sdk.authentication.me().user.id==uid
        record=sdk.cases.create(data={'name':'SDK isolated investigation'}).case
        cid=record.id
        with pytest.raises(MWSConflictError):sdk.cases.advance(cid,data={'expected':0})
        sdk.cases.update(cid,data={'owner_id':uid})
        sdk.cases.advance(cid,data={'expected':0})
        task=sdk.tasks.create(cid,data={'title':'Validate sample'}).task
        sdk.tasks.update(cid,task.id,data={'state':'Completed'})
        assert list(sdk.tasks.iter_all(cid))[0].state=='Completed'
        sdk.notes.create(cid,data={'title':'Findings','body':'Observed a command interpreter.'})
        sdk.notes.update_draft(cid,data={'body':'Draft observation'})
        assert sdk.notes.get_draft(cid).draft.body=='Draft observation'
        sdk.indicators.update(cid,data={'revision':0,'rows':[['domain','example.test','Observed']]})
        table=sdk.indicators.get(cid)
        assert table.sections[0].id=='default'
        with pytest.raises(MWSConflictError):sdk.indicators.update(cid,data={'revision':0,'rows':[]})
        preview=sdk.indicators.preview_import(cid,data={'section_id':'default','format':'csv','csv':'filename,payload.exe,Observed'})
        assert preview.revision==1
        sdk.indicators.import_rows(cid,data={'revision':1,'section_id':'default','accepted_rows':[['filename','payload.exe','Observed']]})
        sdk.indicators.download_stix(cid,destination=tmp_path/'indicators.json')
        assert json.loads((tmp_path/'indicators.json').read_text())['type']=='bundle'
        sdk.references.update(cid,data={'revision':0,'rows':[['https://example.test/report','Research']]})
        sdk.reports.update(cid,data={'sections':{'executive_summary':'Analysis found an information stealer.'}})
        sdk.reports.update_mappings(cid,data={'mappings':{'attack':'Observed T1059 command execution.','mbc':'Observed behavior.'}})
        upload=tmp_path/'artifact.txt';upload.write_text('Saved analysis artifact')
        sdk.assets.upload(cid,data={'category':'scripts'},files={'file':upload})
        sdk.assets.download(cid,'scripts/artifact.txt',destination=tmp_path/'download.txt')
        assert (tmp_path/'download.txt').read_text()==upload.read_text()
        image=sdk.reports.upload_image(cid,data={'section':'executive_summary'},files={'image':('image.png',io.BytesIO(make_png()),'image/png')})
        sdk.reports.download_image(cid,image.name,destination=tmp_path/'image.png')
        sdk.templates.upload(files={'template':('report.docx',io.BytesIO(word_template()))})
        from docx import Document
        document=Document();document.add_paragraph('Analyst-authored report');report=io.BytesIO();document.save(report)
        sdk.reports.upload(cid,files={'report':('report.docx',io.BytesIO(report.getvalue()))})
        sdk.reports.download(cid,destination=tmp_path/'report.docx')
        assert (tmp_path/'report.docx').read_bytes()==report.getvalue()
        coverage=sdk.coverage.get(params={'scope':'all'})
        assert coverage.rows[0].indicators.count==2 and coverage.rows[0].report.state=='present'
        sdk.explorer.create_view(data={'name':'SDK view','configuration':configuration(cid)})
        assert sdk.explorer.list_views().views[0]['name']=='SDK view'
        assert sdk.tools.list().tools and sdk.plugins.capabilities().plugin_registry is False
        assert sdk.tools.process_text(data={'operation':'domains','text':'EXAMPLE.TEST'}).text=='example.test'
        assert sdk.metrics.get().stages
        sdk.cases.advance(cid,data={'expected':1})
        for kind in ('raw','standard'):
            archive=sdk.packages.export(cid,data={'archive_type':kind,'acknowledge':True},destination=tmp_path/(kind+'.zip'))
            with zipfile.ZipFile(archive) as z:
                names=z.namelist()
                assert any(name.endswith('/scripts/artifact.txt') for name in names)
                assert any(name.endswith('/manifest.json') for name in names)
                assert any(name.endswith('.docx') for name in names)==(kind=='raw')
        sdk.tasks.delete(cid,task.id)
        sdk.notes.delete_draft(cid)
        sdk.cases.delete(cid)
        assert sdk.cases.list().total==0


def test_sdk_profile_models_and_permissions():
    uid,headers=make_user('sdk-profile-integration')
    with MWSClient('http://isolated.test',headers['Authorization'][7:],transport=httpx.WSGITransport(app=app),retries=0) as sdk:
        sdk.families.create(data={'name':'Family','tag':'MAL_INTEGRATION','aliases':['Other name']})
        profile=sdk.families.list().profiles[0]
        assert profile.aliases==['Other name']
        sdk.actors.create(data={'name':'Actor','tag':'TA_INTEGRATION','known_families':[profile.id]})
        current=sdk.families.get(profile.id).profile
        assert current.associations
        sdk.families.update(current.id,data={'version':current.version,'aliases':[]})
        assert sdk.families.get(current.id).profile.aliases==[]
        with app.app_context():
            db().execute("INSERT INTO roles(name) VALUES('sdk-no-access')")
            db().execute("UPDATE users SET role='sdk-no-access' WHERE id=?",(uid,));db().commit()
        with pytest.raises(MWSAuthorizationError):sdk.families.list()
