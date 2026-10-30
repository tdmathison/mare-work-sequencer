"""Actual deployment-worker checks; never substitute host subprocess execution."""
import base64
import os
import threading
import time
from pathlib import Path
import pytest
from app import app
from plugin_fixtures import browser,metadata,package_entries,install,post
from plugin_runtime.supervisor import Supervisor,UnixServer,Handler
import plugin_store as store

pytestmark=pytest.mark.skipif(not os.environ.get('MARE_TEST_PLUGIN_IMAGE'),reason='Requires reviewed image and Linux rootless engine with enforced cgroup limits')


def supervisor(folder):
    return Supervisor(folder,os.environ['MARE_TEST_PLUGIN_IMAGE'],'https://example.invalid',os.environ.get('MARE_TEST_WORKER_ENGINE','docker'))


def completed(worker,result):
    job=worker.jobs[result['id']]
    assert job.cleaned.wait(timeout=80)
    result=job.poll()
    assert not job.folder.exists()
    return result


def test_actual_filesystem_network_identity_and_streams(tmp_path):
    worker=supervisor(tmp_path/'jobs');entries=package_entries()
    entries['main.py']['body']=b'''import os,socket
from pathlib import Path

def run(context):
    assert os.getuid()==10001
    for path in ('/data/workflow.sqlite3','/var/run/docker.sock','/run/podman/podman.sock','/Users','/app'):
        assert not Path(path).exists()
    try:
        Path('/etc/isolation-write').write_text('blocked')
    except OSError:
        pass
    else:
        raise AssertionError('root filesystem writable')
    try:
        socket.create_connection(('1.1.1.1',443),timeout=1)
    except OSError:
        pass
    else:
        raise AssertionError('network available')
    assert not any('SECRET' in key or 'TOKEN' in key or 'API_KEY' in key for key in os.environ)
    assert context.dry_run is False
    print('Hello World')
    context.log('Hello diagnostic')
'''
    result=completed(worker,worker.create(dict(mode='run',context={},archive=base64.b64encode(store.archive(entries)).decode(),token='')))
    assert result['status']=='Succeeded' and result['exit_code']==0
    assert 'Hello World' in result['stdout'] and 'Hello diagnostic' in result['stderr']
    assert 'Hello diagnostic' not in result['stdout']


@pytest.mark.parametrize('behavior,expected',[('raise RuntimeError("Expected plugin failure")','Failed'),('import time; time.sleep(120)','Timed out')])
def test_actual_exception_timeout_and_cleanup(tmp_path,behavior,expected):
    worker=supervisor(tmp_path/'jobs');entries=package_entries()
    entries['main.py']['body']=('def run(context):\n '+behavior+'\n').encode()
    result=completed(worker,worker.create(dict(mode='run',context={},archive=base64.b64encode(store.archive(entries)).decode(),token='')))
    assert result['status']==expected
    if expected=='Failed':assert 'Expected plugin failure' in result['stderr'] and result['exit_code']!=0


def test_actual_folder_plugin_application_lifecycle(tmp_path,monkeypatch):
    # Keep Unix socket names below platform limits.
    worker=supervisor(tmp_path/'jobs');socket=str(tmp_path/'worker.sock')
    server=UnixServer(socket,Handler);server.supervisor=worker
    threading.Thread(target=server.serve_forever,daemon=True).start()
    monkeypatch.setenv('MARE_PLUGIN_WORKER_SOCKET',socket)
    folder=tmp_path/'plugins';install(folder);monkeypatch.setitem(app.config,'PLUGINS_DIR',folder)
    try:
        client,_=browser()
        assert post(client,'/plugins/discovery').json['registered']==['hello_plugin']
        assert post(client,'/plugins/registry/hello_plugin/enable',{'enabled':True}).status_code==200
        started=post(client,'/plugins/registry/hello_plugin/run');assert started.status_code==202,started.text
        deadline=time.monotonic()+80
        while time.monotonic()<deadline:
            result=client.get('/plugins/executions/'+started.json['id']).json
            if result['status'] not in ('Starting','Running'):break
            time.sleep(.1)
        assert result['status']=='Succeeded'
        assert 'Hello World' in result['stdout'] and 'Hello diagnostic' in result['stderr']
        assert not any((tmp_path/'jobs').iterdir())
        entries=package_entries();entries['main.py']['body']=b'def run(context):\n import time; time.sleep(120)\n'
        started=worker.create(dict(mode='run',context={},archive=base64.b64encode(store.archive(entries)).decode(),token=''))
        worker.jobs[started['id']].stop()
        assert completed(worker,started)['status']=='Canceled'
    finally:
        server.shutdown();server.server_close()
