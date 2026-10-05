import json,os,shutil,subprocess,sys
from pathlib import Path
import pytest

@pytest.mark.parametrize('override',['','relative-content','absolute'])
def test_moved_installation_data_independent_of_launch_directory(tmp_path,override):
    source=Path(__file__).resolve().parents[1]
    installed=tmp_path/'mare-work-sequencer'
    shutil.copytree(source,installed,ignore=shutil.ignore_patterns('data','.venv','__pycache__','.pytest_cache','.git'))
    launch=tmp_path/'other-launch-directory';launch.mkdir()
    env={**os.environ,'PYTHONPATH':str(installed)};env.pop('MARE_DATA_DIR',None)
    expected=installed/'data'
    if override=='relative-content':env['MARE_DATA_DIR']=override;expected=installed/override
    elif override=='absolute':expected=tmp_path/'explicit-data';env['MARE_DATA_DIR']=str(expected)
    result=subprocess.run([sys.executable,'-c','import json;from app import ROOT;print(json.dumps(str(ROOT)))'],cwd=launch,env=env,check=True,text=True,capture_output=True)
    assert Path(json.loads(result.stdout))==expected
    assert (expected/'workflow.sqlite3').is_file() and (expected/'session.key').is_file()
    assert not (launch/'data').exists()
    assert sorted(p.name for p in tmp_path.iterdir())==sorted(['mare-work-sequencer','other-launch-directory']+(['explicit-data'] if override=='absolute' else []))
