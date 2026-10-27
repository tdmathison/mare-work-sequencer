"""Both profile editors operate on the same stable, portable relationship."""
import copy
import json
import uuid
import pytest
from app import app, db, ROOT
from tagging import create as create_tag
from family_portable import export_library, export_profiles, restore_library, validate_library
from threat_actors import associations, family_associations, initialize
from test_threat_actors import setup, create as actor_create, edit as actor_edit, actor_record, post
from test_malware_families import create as family_create, edit as family_edit, profile


def linked(fid):
    with app.app_context():
        return {r['actor_uuid'] for r in family_associations(db(), fid)}


def test_create_edit_remove_both_sides_and_reload_preserves_text_tags_and_history():
    c,*_=setup()
    a=actor_create(c,name='Actor A')
    b=actor_create(c,name='Actor B',tag='TA_SECOND')
    with app.app_context():
        tags=[tuple(r) for r in db().execute('SELECT * FROM case_tags')]
    f=family_create(c,known_actors=[a,b],long_description='Existing narrative\n<script>safe</script>')
    assert linked(f)=={a,b}
    html=c.get('/malware-families/'+f).text
    assert 'Known Threat Actors' in html and 'Actor A · TA_TEST' in html
    assert '/threat-actors/'+b in html and '&lt;script&gt;safe&lt;/script&gt;' in html
    for aid in (a,b):
        assert '/malware-families/'+f in c.get('/threat-actors/'+aid).text
    assert family_edit(c,f,known_actors=[b],known_actors_present='1',long_description='Existing narrative').status_code==302
    assert linked(f)=={b}
    assert 'No families associated.' in c.get('/threat-actors/'+a).text
    assert actor_edit(c,a,known_families=[f]).status_code==302
    assert linked(f)=={a,b}
    assert actor_edit(c,b,known_families=[]).status_code==302
    assert linked(f)=={a}
    assert family_edit(c,f,known_actors_present='1').status_code==302
    assert linked(f)==set()
    assert 'No actors associated.' in c.get('/malware-families/'+f).text
    with app.app_context():
        assert tags==[tuple(r) for r in db().execute('SELECT * FROM case_tags')]
        assert db().execute('SELECT count(*) FROM actor_families').fetchone()[0]==0


def test_validation_permissions_and_cross_editor_conflicts():
    c,uid,*_=setup();a=actor_create(c);f=family_create(c,known_actors=[a])
    bad=str(uuid.uuid4())
    response=family_edit(c,f,known_actors=[bad],known_actors_present='1')
    assert response.status_code==409 and f'value="{bad}"' in response.text
    assert linked(f)=={a}
    assert family_edit(c,f,known_actors=[a,a]).status_code==400
    assert family_edit(c,f,known_actors=['not-an-id']).status_code==400
    assert post(c,'/malware-families/new',name='Rolled back',tag='MAL_ROLLBACK',known_actors=[bad]).status_code==409
    with app.app_context():
        assert not db().execute("SELECT 1 FROM tags WHERE name='MAL_ROLLBACK'").fetchone()
        assert not db().execute("SELECT 1 FROM malware_families WHERE name='Rolled back'").fetchone()
    assert family_edit(c,f,name='',known_actors=[a]).status_code==400
    assert f'value="{a}"' in family_edit(c,f,name='',known_actors=[a]).text
    old_family=profile(f)['version'];old_actor=actor_record(a)['version']
    assert family_edit(c,f,known_actors_present='1').status_code==302
    assert actor_edit(c,a,version=old_actor,known_families=[f]).status_code==409
    assert actor_edit(c,a,known_families=[f]).status_code==302
    assert family_edit(c,f,version=old_family,known_actors_present='1').status_code==409
    assert linked(f)=={a}
    with app.app_context():
        create_tag(db(),'TA_NO_PROFILE')
        db().execute("UPDATE users SET role='Restricted' WHERE id=?",(uid,));db().commit()
    assert c.get('/malware-families/actors/search').status_code==403
    assert post(c,'/malware-families/'+f+'/edit',name='Denied',tag='MAL_EXISTING',known_actors_present='1').status_code==403
    with app.app_context():
        db().execute("UPDATE users SET role='Administrator' WHERE id=?",(uid,));db().commit()
    response=c.get('/malware-families/actors/search?q=TA_')
    assert response.headers['Cache-Control']=='private, no-store'
    assert [row['id'] for row in response.json['actors']]==[a]
    assert c.get('/malware-families/actors/search?q=NO_PROFILE').json=={'actors':[]}
    assert app.test_client().get('/malware-families/actors/search').status_code==302


def test_rename_relink_delete_and_ordering_integrity():
    c,*_=setup();a=actor_create(c);f=family_create(c,known_actors=[a])
    other=family_create(c,name='Other',tag='MAL_OTHER',known_actors=[a])
    assert actor_edit(c,a,name='Renamed',tag='TA_RELINKED').status_code==302
    assert 'Renamed · TA_RELINKED' in c.get('/malware-families/'+f).text
    assert family_edit(c,f,name='New family',tag='MAL_RELINKED').status_code==302
    assert 'New family · MAL_RELINKED' in c.get('/threat-actors/'+a).text
    assert post(c,'/malware-families/'+f+'/delete',version=profile(f)['version'],confirm_name='New family').status_code==302
    with app.app_context():
        assert [row['family_id'] for row in associations(db(),a)]==[other]
        data=export_library(db(),ROOT);validate_library(data,ROOT)
        assert data['actors'][0]['known_families'][0]['position']==1
    version=profile(other)['version']
    assert post(c,'/threat-actors/'+a+'/delete',version=actor_record(a)['version'],confirm_name='Renamed').status_code==302
    assert linked(other)==set() and profile(other)['version']>version
    with app.app_context():
        assert db().execute("SELECT 1 FROM tags WHERE name='TA_RELINKED'").fetchone()
        assert db().execute("SELECT 1 FROM tags WHERE name='MAL_RELINKED'").fetchone()
        assert db().execute('SELECT 1 FROM malware_families WHERE id=?',(other,)).fetchone()


def test_v1_migration_preserves_existing_links_and_is_repeatable():
    c,*_=setup();f=family_create(c);a=actor_create(c,known_families=[f])
    with app.app_context():
        before=[tuple(r) for r in db().execute('SELECT * FROM actor_families')]
        db().execute('DROP INDEX actor_family_reverse')
        db().execute('DROP TRIGGER family_actor_deleted')
        db().execute("DELETE FROM schema_migrations WHERE name='profile-associations-v2'")
        db().commit()
        initialize(db());initialize(db())
        assert before==[tuple(r) for r in db().execute('SELECT * FROM actor_families')]
        assert db().execute("SELECT count(*) FROM schema_migrations WHERE name='profile-associations-v2'").fetchone()[0]==1
        assert not db().execute('PRAGMA foreign_key_check').fetchall()
    assert linked(f)=={a}


def test_complete_v3_backup_upgrades_associations_without_losing_records(tmp_path):
    import io
    import sqlite3
    from test_malware_families import make_backup
    from installation_backup import restore_installation
    from backup_workspace import schema
    c,*_=setup();f=family_create(c);a=actor_create(c,known_families=[f])
    with app.app_context():
        db().execute('DROP INDEX actor_family_reverse')
        db().execute('DROP TRIGGER family_actor_deleted')
        db().execute('DROP TRIGGER actor_family_deleted')
        db().execute('''CREATE TRIGGER actor_family_deleted BEFORE DELETE ON malware_families
          BEGIN UPDATE threat_actors SET version=version+1 WHERE id IN
          (SELECT actor_id FROM actor_families WHERE family_id=OLD.id); END''')
        db().execute("DELETE FROM schema_migrations WHERE name='profile-associations-v2'")
        db().commit()
    try:
        archive=make_backup(c)
    finally:
        with app.app_context():initialize(db())
    destination=tmp_path/'restored'
    restore_installation(io.BytesIO(archive),destination)
    with sqlite3.connect(destination/'workflow.sqlite3') as connection:
        assert connection.execute('SELECT actor_id,family_id FROM actor_families').fetchall()==[(a,f)]
        assert connection.execute('SELECT count(*) FROM cases').fetchone()[0]==1
        assert schema(connection)==app.extensions['backup_workspace'].expected_schema


def test_selective_family_dependency_closure_and_legacy_separate_imports(tmp_path):
    c,*_=setup();a=actor_create(c);f=family_create(c,known_actors=[a])
    second=family_create(c,name='Actor dependency',tag='MAL_DEPENDENCY',known_actors=[a])
    unrelated=actor_create(c,name='Unrelated',tag='TA_UNRELATED')
    with app.app_context():
        data=export_library(db(),ROOT,include_families=True,include_actors=False)
        assert {r['id'] for r in data['actors']}=={a}
        assert {r['family_uuid'] for r in data['actors'][0]['known_families']}=={f,second}
        # Legacy family archives did not include actors; actor archives can be
        # imported separately later against those exact family/tag identities.
        legacy=copy.deepcopy(data);legacy.pop('actors')
        actor_only=dict(schema=data['schema'],families=[],actors=data['actors'])
        db().execute('DELETE FROM threat_actors');db().execute('DELETE FROM malware_families');db().commit()
        restore_library(db(),ROOT,tmp_path,legacy)
        restore_library(db(),ROOT,tmp_path,actor_only)
        assert family_associations(db(),f)[0]['actor_uuid']==a
        restore_library(db(),ROOT,tmp_path,legacy)
        assert family_associations(db(),f)[0]['actor_uuid']==a
        assert not db().execute('SELECT 1 FROM threat_actors WHERE id=?',(unrelated,)).fetchone()
        restore_library(db(),ROOT,tmp_path,actor_only)
        assert db().execute('SELECT count(*) FROM actor_families').fetchone()[0]==2


def test_separate_import_missing_or_wrong_identity_is_visible_and_retryable(tmp_path):
    from backup_areas import resolve
    c,*_=setup();f=family_create(c);a=actor_create(c,known_families=[f])
    with app.app_context():
        data=export_library(db(),ROOT)
        actor_only=dict(schema=data['schema'],families=[],actors=data['actors'])
        families=dict(schema=data['schema'],families=data['families'])
        db().execute('DELETE FROM threat_actors');db().execute('DELETE FROM malware_families');db().commit()
        (tmp_path/'family-library.json').write_text(json.dumps(actor_only))
        conflicts,_,_=resolve(db(),ROOT,tmp_path,{})
        assert any('dependency unavailable or changed' in r['label'] for r in conflicts)
        with pytest.raises(ValueError,match='dependency unavailable or changed'):
            restore_library(db(),ROOT,tmp_path,actor_only)
        assert db().execute('SELECT count(*) FROM threat_actors').fetchone()[0]==0
        restore_library(db(),ROOT,tmp_path,families)
        conflicts,_,planned=resolve(db(),ROOT,tmp_path,{})
        assert not conflicts
        restore_library(db(),ROOT,tmp_path,planned)
        assert family_associations(db(),f)[0]['actor_uuid']==a
        # An explicit wrong target identity cannot attach to a matching name/tag.
        wrong=copy.deepcopy(actor_only);wrong['actors'][0]['id']=str(uuid.uuid4())
        wrong['actors'][0]['tag']='TA_OTHER';wrong['actors'][0]['tag_identity']='e'*32
        wrong['actors'][0]['known_families'][0]['target_tag_identity']='f'*32
        with pytest.raises(ValueError,match='dependency unavailable or changed'):
            restore_library(db(),ROOT,tmp_path,wrong)


def test_family_selective_archive_roundtrip_includes_associated_actors():
    from test_backup_workspace import export,inspect,post as backup_post,wait
    from test_threat_actors import upload
    from family_reports import storage_path
    from profile_types import ACTOR
    c,*_=setup();a=actor_create(c);f=family_create(c,known_actors=[a])
    report=upload(c,a)
    original_bytes=storage_path(ROOT,report['id'],spec=ACTOR).read_bytes()
    actor_create(c,name='Not associated',tag='TA_NOT_ASSOCIATED')
    with c.session_transaction() as session:session['csrf']='backup-workspace'
    archive,job=export(c,['families'],password='')
    assert job['manifest']['dependencies']==['actors','tags']
    assert job['manifest']['counts']['threat_actors']==1
    assert job['manifest']['counts']['actor_reports']==1
    with app.app_context():
        db().execute('DELETE FROM threat_actors');db().execute('DELETE FROM malware_families');db().commit()
    storage_path(ROOT,report['id'],spec=ACTOR).unlink()
    preview=inspect(c,archive,password='')
    assert not preview['preview']['conflicts'] and not preview['preview']['blocking']
    assert backup_post(c,'/backup-restore/jobs/'+preview['id']+'/apply').status_code==202
    wait(c,preview['id'],'completed')
    assert linked(f)=={a}
    assert storage_path(ROOT,report['id'],spec=ACTOR).read_bytes()==original_bytes
