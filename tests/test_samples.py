import io,zipfile
import pyzipper
from docx import Document
from werkzeug.security import generate_password_hash
from app import app,db,run,ensure_package,package
from reporting import OUTPUT

def test_samples_are_encrypted_and_only_in_mal_archives():
    with app.app_context():
        uid=run("INSERT INTO users(username,password,role,forced) VALUES(?,?,?,0)",('sample-admin',generate_password_hash('password-long-123'),'Administrator')).lastrowid
        cid=run("INSERT INTO cases(number,name,created,stage) VALUES('SAMPLE-1','Sample case','2026',2)").lastrowid
        root=ensure_package(cid)
        (root/OUTPUT).parent.mkdir(parents=True,exist_ok=True)
        Document().save(root/OUTPUT)
    client=app.test_client()
    with client.session_transaction() as session:session.update(uid=uid,version=1,csrf='sample-token')
    def post(url,**data):return client.post(url,data={'csrf':'sample-token',**data})
    assert b'value="infected"' in client.get('/account').data
    source=b'harmless test sample bytes'
    upload=post(f'/cases/{cid}/upload',category='samples',ajax='1',file=(io.BytesIO(source),'demo.exe'))
    assert upload.status_code==200 and upload.json['path']=='samples/demo.exe.zip'
    sample=package(cid)/upload.json['path']
    with pyzipper.AESZipFile(sample) as archive:
        assert archive.getinfo('demo.exe').flag_bits&1
        archive.setpassword(b'infected')
        assert archive.read('demo.exe')==source
    assert client.get(f'/cases/{cid}/assets?category=samples').json['files'][0]['path']=='samples/demo.exe.zip'
    assert post('/account/sample-password',sample_archive_password='new sample secret').status_code==302
    changed=post(f'/cases/{cid}/upload',category='samples',ajax='1',file=(io.BytesIO(source),'second.exe'))
    with pyzipper.AESZipFile(package(cid)/changed.json['path']) as archive:
        archive.setpassword(b'new sample secret')
        assert archive.read('second.exe')==source
    standard=post(f'/cases/{cid}/archive',archive_type='standard',acknowledge='1')
    assert standard.status_code==200 and '-MAL' not in standard.headers['Content-Disposition']
    with zipfile.ZipFile(io.BytesIO(standard.data)) as archive:assert not any('/samples/' in name and not name.endswith('/samples/') for name in archive.namelist())
    dangerous=post(f'/cases/{cid}/archive',archive_type='standard',acknowledge='1',include_samples='1')
    assert dangerous.status_code==200 and '-MAL' in dangerous.headers['Content-Disposition']
    with zipfile.ZipFile(io.BytesIO(dangerous.data)) as archive:
        sample_bytes=archive.read(next(name for name in archive.namelist() if name.endswith('/samples/demo.exe.zip')))
        with pyzipper.AESZipFile(io.BytesIO(sample_bytes)) as encrypted:
            encrypted.setpassword(b'infected')
            assert encrypted.read('demo.exe')==source
    raw=post(f'/cases/{cid}/archive',archive_type='raw',acknowledge='1',include_samples='1')
    assert raw.status_code==200 and '-RAW-MAL' in raw.headers['Content-Disposition']
    with zipfile.ZipFile(io.BytesIO(raw.data)) as archive:
        nested=archive.read(next(name for name in archive.namelist() if name.endswith('/samples/second.exe.zip')))
        with pyzipper.AESZipFile(io.BytesIO(nested)) as encrypted:
            encrypted.setpassword(b'new sample secret')
            assert encrypted.read('second.exe')==source