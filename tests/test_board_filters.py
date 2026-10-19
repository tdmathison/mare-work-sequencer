"""Metric shortcuts and manual stage filters use the same board query state."""
from urllib.parse import parse_qs, urlsplit
import pytest
import app as application
from app import app, db, run
from test_board_sort import board, rendered
from authorization import initialize_roles
from tagging import create


def test_stage_filters_and_metric_links(board,monkeypatch):
    client,uid,_,ids=board
    with app.app_context():
        new=run("INSERT INTO cases(number,name,created,stage) VALUES('004','Analysis','now',1)").lastrowid
    previous=application.readiness
    monkeypatch.setattr(application,'readiness',lambda cid: [] if cid==new else previous(cid))
    for stages,expected in [([],set(ids+[new])),(['0'],{ids[1]}),(['1','2'],{new,ids[0]}),(['3'],{ids[2]}),(['0','3'],{ids[1],ids[2]})]:
        for view in ['table','cards']:
            with rendered() as contexts:
                response=client.get('/',query_string=[('view',view)]+[('stage',stage) for stage in stages])
            assert response.status_code==200
            assert {case['id'] for case in contexts[-1]['cases']}==expected
            assert contexts[-1]['selected_stages']==list(map(int,stages))
            metrics=contexts[-1]['board_metrics']
            assert [item['count'] for item in metrics]==[4,1,2,1]
            assert [parse_qs(urlsplit(item['url']).query).get('stage',[]) for item in metrics]==[[],['0'],['1','2'],['3']]
    with rendered() as contexts:client.get('/?view=table&q=Alpha&stage=3')
    metrics=contexts[-1]['board_metrics']
    assert parse_qs(urlsplit(metrics[0]['url']).query)=={'view':['table']}
    assert parse_qs(urlsplit(metrics[1]['url']).query)['q']==['Alpha']
    assert contexts[-1]['cases']==[]
    response=client.post('/account/board-sort',data={'csrf':'sort-token','column':'title','direction':'asc','stage':['0','3']})
    assert parse_qs(urlsplit(response.location).query)['stage']==['0','3']


@pytest.mark.parametrize('query',['stage=4','stage=-1','stage=anything','stage=01','stage=0&stage=0&stage=0&stage=0&stage=0'])
def test_invalid_stages_are_rejected(board,query):
    assert board[0].get('/?'+query).status_code==400


def test_stage_search_and_tag_filters_combine_without_changing_permissions(board):
    client,uid,_,ids=board
    with app.app_context():
        initialize_roles(db())
        tid,_=create(db(),'FILTER_TEST')
        run('INSERT INTO case_tags(case_id,tag_id,assigned_at,assigned_by) VALUES(?,?,\'now\',?)',(ids[0],tid,uid))
    with rendered() as contexts:
        response=client.get('/',query_string={'stage':'2','tag':tid,'q':'zulu','match':'all'})
    assert response.status_code==200 and [c['id'] for c in contexts[-1]['cases']]==[ids[0]]
    assert client.get('/',query_string={'stage':'0','tag':tid}).status_code==200
    with app.app_context():run("DELETE FROM role_permissions WHERE role_name='User' AND permission='tags:read'")
    response=client.get('/?stage=0')
    assert response.status_code==200 and b'board-stage-filters' in response.data
    assert b'data-filter-search' not in response.data
    assert client.get('/',query_string={'stage':'2','tag':tid}).status_code==403
