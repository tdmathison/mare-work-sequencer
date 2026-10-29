import json
from datetime import datetime, timezone
from app import app, db
from actor_dashboard import snapshot, FIELDS, LIBRARY_SIZE
from dashboard_directory import DASHBOARDS
from tagging import create
from test_family_dashboard import case
from test_dashboard_directory import login_client


def actor(name='Actor', tag='TA_ACTOR', updated='2026-10-01T12:00:00Z', identity='actor'):
    tid=create(db(),tag)[0]
    db().execute('''INSERT INTO threat_actors(id,name,tag_id,aliases,short_description,long_description,
      attribution_notes,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?)''',
      (identity,name,tid,'["PRIVATE_ALIAS"]','<img src=x onerror=alert(1)>','PRIVATE_LONG','PRIVATE_NOTES','2026',updated))
    return identity,tid


def test_anonymous_links_public_projection_no_writes_and_protected_management(monkeypatch):
    client=app.test_client()
    assert client.get('/dashboards/threat-actors').status_code==200
    html=client.get('/dashboards/threat-actors').text
    assert 'THREAT ACTOR RESEARCH' in html and 'Track the actors. Connect the research.' in html
    assert 'aria-current="page">Threat Actors</span>' in html
    assert 'class="wall-login" href="/login">Login</a>' in html
    for path in ('/login','/dashboards','/dashboards/cases','/dashboards/malware-families'):
        assert 'href="/dashboards/threat-actors"' in client.get(path).text
    entry=next(item for item in DASHBOARDS if item.identifier=='actors')
    assert entry.endpoint=='actor_dashboard' and entry.availability=='implemented' and entry.visibility=='public'
    for path in ('/threat-actors','/threat-actors/private','/threat-actors/private/edit','/threat-actors/private/reports/private/download','/cases/1','/threat-actors/families/search'):
        assert client.get(path).status_code==302
    assert client.post('/dashboards/threat-actors/data').status_code in (403,405)
    assert client.get('/api/v1/cases').status_code==401
    with app.app_context():
        aid,tid=actor()
        case('PRIVATE_NUMBER',1,[tid])
        db().execute("INSERT INTO actor_osint VALUES('osint',?,'PRIVATE_ARTICLE','https://example.com/PRIVATE_URL',1)",(aid,))
        db().execute('''INSERT INTO actor_reports(id,actor_id,title,original_filename,description,storage_ref,size,file_type,sha256,uploaded_at)
          VALUES('report',?,'PRIVATE_TITLE','PRIVATE_FILENAME','PRIVATE_DESCRIPTION','PRIVATE_PATH',1,'PRIVATE_TYPE','PRIVATE_HASH','2026')''',(aid,))
        db().commit()
        before=db().total_changes
        monkeypatch.setattr('family_reports.verify_report',lambda *args,**kwargs: (_ for _ in ()).throw(AssertionError('Public request read a report file')))
        result=snapshot(db())
        assert db().total_changes==before
    response=client.get('/dashboards/threat-actors/data')
    assert response.status_code==200 and response.headers['Cache-Control']=='no-store'
    assert set(result)=={'updated_at','timezone','metrics','featured','investigations','tracked','pagination','library_pagination'}
    assert set(response.json['featured'])==set(FIELDS)
    assert all(set(row)==set(FIELDS) for row in response.json['tracked']+response.json['investigations'])
    assert 'PRIVATE' not in response.text and '/threat-actors' not in response.text
    assert 'aliases' not in response.text and 'known_families' not in response.text
    assert response.json['featured']['short_description']=='<img src=x onerror=alert(1)>'
    for params in ('page=-1','page=bad','library_page=-1','library_page=1000001','page=1.5'):
        assert client.get('/dashboards/threat-actors/data?'+params).status_code==400
    auth=login_client()
    assert 'class="wall-login" href="/">Return</a>' in auth.get('/dashboards/threat-actors').text
    assert 'Threat Actors</h3>' in auth.get('/dashboards').text


def test_stable_ta_counts_distinct_case_inventory_and_no_family_inference():
    from test_family_dashboard import family
    with app.app_context():
        a,at=actor('Alpha','TA_ALPHA','2026-10-01',identity='a')
        b,bt=actor('Beta','TA_BETA','2026-10-02',identity='b')
        actor('Newest idle','TA_IDLE','2026-10-20',identity='c')
        unprofiled=create(db(),'TA_UNPROFILED')[0]
        fid,ft=family()
        # This analyst association must not bring in any MAL_-only cases.
        identity=db().execute('SELECT identity FROM family_tag_identities WHERE tag_id=?',(ft,)).fetchone()[0]
        db().execute('INSERT INTO actor_families VALUES(?,?,?,?,?,?,?)',(a,fid,fid,'Family','MAL_FAMILY',identity,1))
        linked=case('PRIVATE_MULTI',1,[at,bt])
        case('PRIVATE_PACKAGING',2,[at])
        case('PRIVATE_COMPLETED',3,[bt])
        case('PRIVATE_WAITING',0,[bt])
        case('PRIVATE_INVALID_HIGH',4,[at])
        case('PRIVATE_INVALID_LOW',-1,[bt])
        case('PRIVATE_FAMILY_ONLY',1,[ft])
        case('PRIVATE_UNPROFILED',1,[unprofiled])
        db().execute("INSERT INTO actor_osint VALUES('one',?,'Article','https://example.com',1)",(a,))
        db().execute("INSERT INTO actor_reports(id,actor_id,title,original_filename,storage_ref,size,file_type,sha256,uploaded_at) VALUES('one',?,'Private','private.pdf','private/path',1,'application/pdf','private','2026')",(a,))
        data=snapshot(db())
        assert data['metrics']==dict(tracked_actors=3,actors_in_progress=2,unique_linked_cases=4,reports_collected=1)
        assert data['featured']['name']=='Beta'  # date wins among actors with work, not workload size
        assert [row['name'] for row in data['investigations']]==['Alpha','Beta']
        alpha=data['investigations'][0]
        assert (alpha['linked_cases'],alpha['in_progress'],alpha['osint_links'],alpha['reports_collected'])==(2,2,1,1)
        db().execute('DELETE FROM cases WHERE id=?',(linked,))
        assert snapshot(db())['metrics']['unique_linked_cases']==3
        db().execute('UPDATE cases SET stage=3 WHERE stage IN (1,2)')
        assert snapshot(db())['featured']['name']=='Newest idle'
        assert snapshot(db())['metrics']['actors_in_progress']==0
        db().execute('DELETE FROM threat_actors WHERE id=?',(a,))
        assert snapshot(db())['metrics']['tracked_actors']==2
        assert snapshot(db())['metrics']['reports_collected']==0
        assert snapshot(db())['metrics']['unique_linked_cases']==2


def test_empty_missing_dates_selection_ties_timezone_and_all_pages():
    with app.app_context():
        empty=snapshot(db())
        assert empty['featured'] is None and empty['tracked']==[]
        assert all(value==0 for value in empty['metrics'].values())
        _,tag=actor(updated='unknown',identity='z')
        case('one',2,[tag])
        assert snapshot(db())['featured']['updated_at'] is None
        for index in range(1,61):
            _,tag=actor(f'Actor {index:03}',f'TA_ACTOR_{index:03}',updated='2026-10-02T02:00:00+00:00',identity=f'id{index:03}')
            case(str(index),1,[tag])
        data=snapshot(db(),999,999,current=datetime(2026,10,26,tzinfo=timezone.utc),timezone_name='America/Los_Angeles')
        assert data['pagination']==dict(page=20,pages=21,page_size=3,total=61)
        assert data['library_pagination']==dict(page=2,pages=3,page_size=24,total=61)
        assert data['timezone']=='America/Los_Angeles'
        assert data['updated_at']=='2026-10-26T00:00:00+00:00'
        assert snapshot(db())['featured']['name']=='Actor 001'
        assert snapshot(db())['featured']==snapshot(db())['featured']
        names=[]
        for page in range(3):
            result=snapshot(db(),library_page=page)
            assert len(result['tracked'])<=LIBRARY_SIZE
            names.extend(row['name'] for row in result['tracked'])
        assert len(set(names))==61
        assert len(json.dumps(data))<50000


def test_invalid_namespace_excluded_consistently_and_only_fixed_queries():
    with app.app_context():
        _,valid=actor('Valid','TA_VALID',identity='valid')
        _,invalid=actor('Invalid','TA_INVALID',identity='invalid')
        case('valid',1,[valid]);case('excluded',1,[invalid])
        # Simulate an invalid legacy relationship; normal actor guards prohibit it.
        db().execute('DROP TRIGGER actor_tag_rename')
        db().execute("UPDATE tags SET name='MAL_INVALID',normalized_name='MAL_INVALID' WHERE id=?",(invalid,))
        statements=[];db().set_trace_callback(statements.append)
        try:data=snapshot(db())
        finally:db().set_trace_callback(None)
        assert data['metrics']==dict(tracked_actors=1,actors_in_progress=1,unique_linked_cases=1,reports_collected=0)
        assert {row['name'] for row in data['tracked']+data['investigations']}=={'Valid'}
        assert len([sql for sql in statements if sql.lstrip().startswith('WITH eligible')])==4
