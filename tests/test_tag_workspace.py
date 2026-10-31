from flask import template_rendered
import pytest
from app import app,db,run
from tagging import create,now
from test_tagging import fixture


def view(client,path):
    contexts=[]
    def capture(sender,template,context,**kwargs):contexts.append(context)
    with template_rendered.connected_to(capture,app):response=client.get(path)
    assert response.status_code==200,response.text
    return response,contexts[-1]


def populated():
    client,cid,uid=fixture('Administrator')
    with app.app_context():
        ids={name:create(db(),name)[0] for name in ('MAL_LINKED','MAL_MISSING','TA_LINKED','TA_MISSING','GENERAL')}
        closed=run("INSERT INTO cases(number,name,stage,created) VALUES('TAG-CLOSED','Completed intelligence',3,'2026')").lastrowid
        for case_id in (cid,closed):db().execute('INSERT INTO case_tags VALUES(?,?,?,?)',(case_id,ids['MAL_LINKED'],now(),uid))
        db().execute('INSERT INTO case_tags VALUES(?,?,?,?)',(closed,ids['TA_LINKED'],now(),uid));db().commit()
    for route,name,tag in [('/malware-families/new','Linked family','MAL_LINKED'),('/threat-actors/new','Linked actor','TA_LINKED')]:
        assert client.post(route,data={'csrf':'tag-test','name':name,'tag':tag}).status_code==302
    return client,cid,uid,ids


def test_namespace_filters_actual_links_and_prefilled_creation_are_read_only():
    client,_,_,ids=populated()
    with app.app_context():before=[db().execute('SELECT count(*) FROM '+t).fetchone()[0] for t in ('tags','malware_families','threat_actors')]
    for prefix,kind,label,route,profile_name in [('MAL','malware','malware family','/malware-families/','Linked family'),('TA','actors','threat actor','/threat-actors/','Linked actor')]:
        response,context=view(client,'/tags?namespace='+kind+'&q='+prefix.lower())
        assert {t['id'] for t in context['tags']}=={ids[prefix+'_LINKED'],ids[prefix+'_MISSING']}
        response,context=view(client,f'/tags/{ids[prefix+"_LINKED"]}')
        assert context['tag']['profile']['exists'] and profile_name in response.text
        assert context['tag']['profile']['url'].startswith(route)
        assert f'Create {label} profile' not in response.text
        response,context=view(client,f'/tags/{ids[prefix+"_MISSING"]}')
        assert f'Create {label} profile' in response.text
        target=context['tag']['profile']['create_url']
        assert 'tag_id='+str(ids[prefix+'_MISSING']) in target
        assert 'value="'+prefix+'_MISSING"' in client.get(target).text
    response,context=view(client,f'/tags/{ids["GENERAL"]}')
    assert not context['tag']['profile']['create_url']
    assert 'Create malware family profile' not in response.text and 'Create threat actor profile' not in response.text
    assert client.get('/tags?namespace=invalid').status_code==400
    with app.app_context():assert [db().execute('SELECT count(*) FROM '+t).fetchone()[0] for t in ('tags','malware_families','threat_actors')]==before


def test_accessible_history_includes_completed_distinct_counts_and_permissions():
    client,_,uid,ids=populated()
    response,context=view(client,f'/tags/{ids["MAL_LINKED"]}?tab=history')
    assert context['tag']['uses']==2 and len(context['cases'])==2
    assert {c['stage'] for c in context['cases']}=={1,3}
    assert 'Completed intelligence' in response.text and 'is-completed' in response.text
    assert all(c['id'] for c in context['cases'])
    with app.app_context():
        db().execute("INSERT INTO roles VALUES('Tag reader','',0)")
        db().execute("INSERT INTO role_permissions VALUES('Tag reader','tags:read')")
        db().execute("UPDATE users SET role='Tag reader' WHERE id=?",(uid,));db().commit()
    response,context=view(client,f'/tags/{ids["MAL_LINKED"]}?tab=history')
    assert context['tag']['uses']==0 and context['cases']==[]
    assert all(t['uses']==0 for t in context['tags'])
    assert 'Completed intelligence' not in response.text and 'TAG-CLOSED' not in response.text
    assert 'Case history requires Case read permission' in response.text
    response,context=view(client,f'/tags/{ids["TA_MISSING"]}')
    assert context['tag']['profile']['create_url'] is None
    assert 'data-tag-create>' not in response.text and 'id="tag-edit"' not in response.text
    with app.app_context():db().execute("DELETE FROM role_permissions WHERE role_name='Tag reader'");db().commit()
    assert client.get('/tags').status_code==403


def test_pagination_deep_links_empty_usage_and_filtered_selection():
    client,cid,uid=fixture('Administrator')
    with app.app_context():
        ids=[create(db(),f'OTHER_{index:03}')[0] for index in range(65)]
        for index in range(55):
            case_id=db().execute('INSERT INTO cases(number,name,stage,created) VALUES(?,?,?,?)',(f'HISTORY-{index:03}','Long title '+('word '*50),index%4,'2026')).lastrowid
            db().execute('INSERT OR IGNORE INTO case_tags VALUES(?,?,?,?)',(case_id,ids[-1],now(),uid))
        db().commit()
    _,context=view(client,f'/tags/{ids[-1]}?tab=history')
    assert context['tag']['id']==ids[-1] and context['page']==2 and context['pages']==2
    assert context['tag']['uses']==55 and len(context['cases'])==50 and context['case_pages']==2
    _,selected=view(client,f'/tags/{ids[-1]}?page=1')
    assert selected['tag']['id']==ids[-1] and selected['page']==2
    _,context=view(client,f'/tags/{ids[-1]}?tab=history&case_page=2')
    assert context['tag']['uses']==55 and len(context['cases'])==5
    response,context=view(client,f'/tags/{ids[0]}?tab=history')
    assert context['tag']['uses']==0 and 'No Cases currently use this tag.' in response.text
    response,context=view(client,f'/tags/{ids[0]}?q=NO_MATCH')
    assert context['tag'] is None and 'No tag selected' in response.text
    assert client.get('/tags/999999').status_code==404


def test_workspace_crud_preserves_identity_associations_and_filter_context():
    client,cid,_,ids=populated()
    tid=ids['MAL_LINKED']
    response=client.post(f'/tags/{tid}/rename',data={'csrf':'tag-test','name':'mal_renamed','workspace':'1','namespace':'malware','q':'MAL_'})
    assert response.status_code==302 and f'/tags/{tid}?' in response.location and 'namespace=malware' in response.location
    _,context=view(client,response.location)
    assert context['tag']['id']==tid and context['tag']['name']=='MAL_RENAMED' and context['tag']['uses']==2
    assert context['tag']['profile']['name']=='Linked family'
    client.post(f'/tags/{tid}/delete',data={'csrf':'tag-test','confirm':'1','workspace':'1'})
    with app.app_context():assert db().execute('SELECT 1 FROM tags WHERE id=?',(tid,)).fetchone()
    other=ids['GENERAL']
    response=client.post(f'/tags/{other}/delete',data={'csrf':'tag-test','workspace':'1'})
    assert f'/tags/{other}' in response.location
    response=client.post(f'/tags/{other}/delete',data={'csrf':'tag-test','confirm':'1','workspace':'1','namespace':'other'})
    assert response.location.startswith('/tags?')
    _,context=view(client,response.location)
    assert context['tag'] is None
    assert client.post('/tags/create',data={'csrf':'tag-test','name':'NEW_CUSTOM','workspace':'1'}).location.startswith('/tags/')
