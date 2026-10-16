"""Canonical naming, transactional upgrades, concurrency and authenticated imports."""
import concurrent.futures
import io
import sqlite3
import uuid

import pytest
from app import app, db, backup_helpers, ROOT
from tagging import name, create, initialize, invalid_legacy, restore, portable
from case_sync import logical_snapshot, fingerprint, validate_graph
from test_tagging import fixture, rewrite_metadata
from test_case_sync import preview, apply, head
from test_backups import setup_backup_case


@pytest.mark.parametrize('raw,expected', [('malware','MALWARE'), (' Apt_29 ','APT_29'), ('sample123','SAMPLE123'), ('123_','123_'), (' x ','X'), (' '*5+'x'*120+' '*5,'X'*120)])
def test_normalization(raw, expected):
    assert name(raw) == expected


@pytest.mark.parametrize('raw', ['threat actor', 'ransomware-test', 'tag.name', 'ß', 'ı', 'ſ', 'K', 'Ａ', 'café', 'A\nB', 'a/b'])
def test_invalid_original_characters(raw):
    with pytest.raises(ValueError, match='Tags may contain only letters, numbers, and underscores.'):
        name(raw)


@pytest.mark.parametrize('raw', ['', '  ', None, 3, 'x'*121])
def test_empty_and_length(raw):
    with pytest.raises(ValueError, match='1–120'):
        name(raw)


def legacy_database(path):
    connection=sqlite3.connect(path)
    connection.row_factory=sqlite3.Row
    connection.execute('PRAGMA foreign_keys=ON')
    connection.executescript('''
    CREATE TABLE users(id INTEGER PRIMARY KEY,username TEXT);
    CREATE TABLE cases(id INTEGER PRIMARY KEY);
    CREATE TABLE schema_migrations(name TEXT PRIMARY KEY);
    CREATE TABLE audit(id INTEGER PRIMARY KEY,actor TEXT,action TEXT,created TEXT);
    CREATE TABLE tags(id INTEGER PRIMARY KEY,name TEXT NOT NULL,normalized_name TEXT NOT NULL UNIQUE,created_at TEXT NOT NULL);
    CREATE TABLE case_tags(case_id INTEGER REFERENCES cases(id),tag_id INTEGER REFERENCES tags(id) ON DELETE CASCADE,assigned_at TEXT,assigned_by INTEGER,PRIMARY KEY(case_id,tag_id));
    INSERT INTO cases VALUES(1),(2); INSERT INTO users VALUES(1,'actor');
    INSERT INTO tags VALUES(1,'malware','old-one','2025'),(2,'MALWARE','old-two','2026'),(3,'bad-name','bad-name','2024');
    INSERT INTO case_tags VALUES(1,1,'first',1),(1,2,'second',1),(2,2,'third',1),(2,3,'legacy',1);
    ''')
    return connection


def test_upgrade_preserves_ids_associations_and_invalid_legacy(tmp_path):
    con=legacy_database(tmp_path/'tags.sqlite')
    assert initialize(con)
    assert [tuple(r) for r in con.execute('SELECT id,name FROM tags ORDER BY id')]==[(1,'MALWARE'),(3,'bad-name')]
    assert [tuple(r) for r in con.execute('SELECT case_id,tag_id FROM case_tags ORDER BY 1,2')]==[(1,1),(2,1),(2,3)]
    assert con.execute('SELECT assigned_at FROM case_tags WHERE case_id=1 AND tag_id=1').fetchone()[0]=='first'
    assert invalid_legacy(con)[0]['id']==3
    before=[tuple(r) for r in con.execute('SELECT * FROM tags')]
    initialize(con)
    assert before==[tuple(r) for r in con.execute('SELECT * FROM tags')]
    assert not con.execute('PRAGMA foreign_key_check').fetchall()
    assert create(con,' Malware ')==(1,False)
    con.execute("UPDATE tags SET name='BAD_NAME',normalized_name='BAD_NAME' WHERE id=3")
    assert invalid_legacy(con)==[]
    with pytest.raises(sqlite3.IntegrityError):
        con.execute("INSERT INTO tags(name,normalized_name,created_at) VALUES('bad.name','BAD.NAME','2026')")
    con.close()


def test_upgrade_rolls_back_entire_migration(tmp_path):
    con=legacy_database(tmp_path/'tags.sqlite')
    con.execute("CREATE TRIGGER fail_delete BEFORE DELETE ON tags BEGIN SELECT RAISE(ABORT,'forced failure'); END")
    with pytest.raises(sqlite3.IntegrityError, match='forced failure'):
        initialize(con)
    assert con.execute('SELECT name FROM tags WHERE id=1').fetchone()[0]=='malware'
    assert con.execute('SELECT count(*) FROM case_tags').fetchone()[0]==4
    assert not con.execute("SELECT 1 FROM schema_migrations WHERE name='uppercase-ascii-tags-v1'").fetchone()
    con.close()


def test_concurrent_canonical_creation(tmp_path):
    path=tmp_path/'concurrent.sqlite'
    con=legacy_database(path);initialize(con);con.close()
    def insert(index):
        connection=sqlite3.connect(path,timeout=10)
        try:
            with connection:
                return create(connection, ['apt_29','APT_29','Apt_29'][index%3])
        finally:
            connection.close()
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        results=list(pool.map(insert,range(16)))
    assert len({tid for tid,changed in results})==1
    assert sum(changed for tid,changed in results)==1


def test_json_case_endpoints_reuse_and_manager_rename_conflict():
    client,cid,_=fixture('Administrator')
    for value in ('malware',' Malware ', 'MALWARE'):
        response=client.post(f'/cases/{cid}/tags/create', data={'csrf':'tag-test','name':value},headers={'Accept':'application/json'})
        assert response.status_code==200
        assert len(response.json['tags'])==1 and response.json['tags'][0]['name']=='MALWARE'
    tid=response.json['tags'][0]['id']
    invalid=client.post(f'/cases/{cid}/tags/create',data={'csrf':'tag-test','name':'bad-name'},headers={'Accept':'application/json'})
    assert invalid.status_code==400 and invalid.json['error']=='Tags may contain only letters, numbers, and underscores.'
    client.post('/tags/create',data={'csrf':'tag-test','name':'Other'})
    renamed=client.post(f'/tags/{tid}/rename',data={'csrf':'tag-test','name':'other'},follow_redirects=True)
    assert b'That tag name already exists' in renamed.data
    with app.app_context():
        assert db().execute('SELECT name FROM tags WHERE id=?',(tid,)).fetchone()[0]=='MALWARE'
        assert len(portable(db(),cid)['tags'])==1
    assert client.get('/tags/search?q=malware').json['exact_id']==tid
    client.post('/tags/create',data={'csrf':'tag-test','name':'I'})
    assert client.get('/tags/search?q=ı').json['exact_id'] is None


def test_invalid_legacy_remains_editable_and_snapshot_safe():
    client,cid,_=fixture('Administrator')
    with app.app_context():
        con=db()
        con.execute('DROP TRIGGER tags_canonical_insert')
        con.execute("INSERT INTO tags(id,name,normalized_name,created_at) VALUES(77,'old-tag','old-tag','2026')")
        con.execute("INSERT INTO tags(id,name,normalized_name,created_at) VALUES(78,'Café','café','2026')")
        con.execute('INSERT INTO case_tags VALUES(?,?,?,NULL)',(cid,77,'2026'))
        con.commit()
        initialize(con)
        before=app.extensions['case_sync'].reconcile(cid)['revision_uuid']
    assert client.get('/tags/search?q=café').json['tags'][0]['name']=='Café'
    page=client.get('/tags')
    assert b'Invalid legacy tags retained' in page.data and b'old-tag' in page.data
    client.post(f'/tags/77/rename',data={'csrf':'tag-test','name':'old_tag'})
    with app.app_context():
        assert db().execute('SELECT name FROM tags WHERE id=77').fetchone()[0]=='OLD_TAG'
        assert app.extensions['case_sync'].reconcile(cid)['revision_uuid']!=before


def test_restore_and_authenticated_api_import_reject_invalid_tags():
    from test_api import make_user
    uid,headers=make_user('tag-api-admin')
    client=app.test_client()
    with client.session_transaction() as session:
        session.update(uid=uid,version=1,csrf='tag-test')
    response=client.post('/api/v1/cases',headers=headers,json={'name':'tag import fixture'})
    cid=response.json['case']['id']
    with app.app_context():
        restore(db(),{'schema_version':1,'tags':['apt_29']},cid);db().commit()
    raw=client.post(f'/api/v1/cases/{cid}/backup',headers=headers).data
    bad=rewrite_metadata(raw,lambda meta:meta['tagging'].update(tags=['bad.name']))
    rejected=client.post('/api/v1/backups/import-raw',headers=headers,data={'backup':(io.BytesIO(bad),'bad.zip')})
    assert rejected.status_code==400 and 'Invalid incoming tag' in rejected.json['error']
    review=client.get('/api/v1/backups/review/'+rejected.json['operation'],headers=headers)
    assert 'bad.name' in review.json['outcomes'][0]['reason']
    with app.app_context():
        assert portable(db(),cid)['tags']==['APT_29']
        with pytest.raises(ValueError):restore(db(),{'schema_version':1,'tags':['INVALID NAME']},cid)


def legacy_casing_archive(blob, foreign=False):
    """Create a coherent older-style revision, keeping its raw mixed-case hash."""
    import tempfile
    from werkzeug.datastructures import FileStorage
    changed=rewrite_metadata(blob,lambda meta:meta['tagging'].update(tags=['Malware']))
    with app.app_context(), tempfile.TemporaryDirectory(dir=ROOT) as temporary:
        plans,_=backup_helpers['stage_upload'](FileStorage(io.BytesIO(changed),filename='legacy.zip'),True,temporary)
        folder,validated,_=plans[0]
        computed=fingerprint(logical_snapshot(validated,folder/'mip'))
    def revision(meta):
        sync=meta['sync'];previous=sync['revision_uuid'];key=str(uuid.uuid4())
        node={'uuid':key,'parents':[] if foreign else [previous], 'fingerprint':computed,
              'created':'2026-01-01T00:00:00+00:00','installation':sync['exporter_uuid']}
        sync['revisions']=([node] if foreign else sync['revisions']+[node])
        sync['revision_uuid']=key
        if foreign:sync['case_uuid']=str(uuid.uuid4())
    return rewrite_metadata(changed,revision)


@pytest.mark.parametrize('foreign',[False,True])
def test_sync_casing_equivalence_and_raw_revision_validation(foreign):
    client,cid,uid,post=setup_backup_case()
    with app.app_context():
        restore(db(),{'schema_version':1,'tags':['MALWARE']},cid);db().commit()
    raw=post(f'/cases/{cid}/backup').data
    legacy=legacy_casing_archive(raw,foreign)
    operation,plan=preview(client,legacy)
    assert plan['items'][0]['preview']['classification']==('new' if foreign else 'unchanged')
    outcomes=apply(client,operation)
    assert outcomes[0]['action']==('Imported new' if foreign else 'Unchanged'),outcomes
    destination=cid
    if foreign:
        with app.app_context():destination=db().execute('SELECT max(id) FROM cases').fetchone()[0]
    before=head(destination)
    with app.app_context():
        sync=app.extensions['case_sync']
        assert portable(db(),destination)['tags']==['MALWARE']
        assert db().execute('SELECT count(*) FROM tags').fetchone()[0]==1
        exported=sync.export(destination)
        validate_graph(exported,fingerprint(sync.snapshot(destination)))
    operation,plan=preview(client,legacy)
    assert plan['items'][0]['preview']['classification']=='unchanged'
    assert apply(client,operation)[0]['action']=='Unchanged'
    assert head(destination)==before
    corrupt=rewrite_metadata(legacy,lambda meta:meta['sync']['revisions'][-1].update(fingerprint='0'*64))
    operation,plan=preview(client,corrupt)
    assert plan['items'][0]['preview']['classification']=='invalid'
    assert 'fingerprint' in plan['items'][0]['preview']['reason']
