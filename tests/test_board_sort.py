"""Per-account board sorting shared by table and card rendering."""
from contextlib import contextmanager
from urllib.parse import parse_qs, urlsplit

import pytest
from flask import template_rendered
from werkzeug.security import generate_password_hash
import app as application
from app import app, db, run


@contextmanager
def rendered():
    contexts=[]
    def capture(sender, template, context, **extra):contexts.append(context)
    template_rendered.connect(capture,app)
    try:yield contexts
    finally:template_rendered.disconnect(capture,app)


@pytest.fixture
def board(monkeypatch):
    with app.app_context():
        alice=run("INSERT INTO users(username,password,role,forced) VALUES(?,?,'User',0)",('alpha',generate_password_hash('board-password-123'))).lastrowid
        zed=run("INSERT INTO users(username,password,role,forced) VALUES(?,?,'User',0)",('Zed',generate_password_hash('board-password-123'))).lastrowid
        ids=[]
        for number,title,owner,creator,stage in [('002','zulu',zed,alice,2),('010','Alpha',alice,zed,0),('001','middle',None,None,3)]:
            ids.append(run('INSERT INTO cases(number,name,created,owner,creator,stage) VALUES(?,?,\'now\',?,?,?)',('MARE-2026-'+number,title,owner,creator,stage)).lastrowid)
    counts=dict(zip(ids,[2,0,1]))
    monkeypatch.setattr(application,'readiness',lambda cid:[{'status':'Populated' if index<counts[cid] else 'Pending','label':'Category'} for index in range(2)])
    client=app.test_client()
    with client.session_transaction() as session:session.update(uid=alice,version=1,csrf='sort-token')
    return client,alice,zed,ids


@pytest.mark.parametrize('column,order',[('number',[2,0,1]),('title',[1,2,0]),('owner',[1,2,0]),('creator',[0,2,1]),('stage',[1,0,2]),('reviewed',[1,2,0])])
def test_every_column_orders_both_views_and_persists(board,column,order):
    client,uid,other,ids=board
    for direction,indices in [('asc',order),('desc',order[::-1])]:
        response=client.post('/account/board-sort',data={'csrf':'sort-token','column':column,'direction':direction})
        assert response.status_code==302
        with app.app_context():
            saved=db().execute('SELECT board_sort,board_sort_direction FROM users WHERE id=?',(uid,)).fetchone()
            assert tuple(saved)==(column,direction)
            assert db().execute('SELECT board_sort FROM users WHERE id=?',(other,)).fetchone()[0]=='newest'
        for view in ['table','cards']:
            with rendered() as contexts:
                response=client.get('/?view='+view)
            assert response.status_code==200
            assert [case['id'] for case in contexts[-1]['cases']]==[ids[index] for index in indices]
            if view=='table':
                html=response.get_data(as_text=True)
                assert html.count('class="mip-sort-button"')==6
                assert html.count('aria-sort="'+('ascending' if direction=='asc' else 'descending')+'"')==1
                assert 'MIP Dashboard' in html and 'Dashbaord' not in html
    # A fresh login/session still reads the account's persisted sorting.
    fresh=app.test_client();fresh.get('/login')
    with fresh.session_transaction() as session:csrf=session['csrf']
    assert fresh.post('/login',data={'csrf':csrf,'username':'alpha','password':'board-password-123'}).status_code==302
    with rendered() as contexts:fresh.get('/')
    assert [case['id'] for case in contexts[-1]['cases']]==[ids[index] for index in order[::-1]]


def test_sort_validation_csrf_filters_and_default(board):
    client,uid,_,ids=board
    with rendered() as contexts:client.get('/')
    assert [case['id'] for case in contexts[-1]['cases']]==ids[::-1]
    assert client.post('/account/board-sort',data={'column':'title','direction':'asc'}).status_code==403
    for column,direction in [('actions','asc'),('title','sideways'),('name; DROP TABLE cases','asc')]:
        assert client.post('/account/board-sort',data={'csrf':'sort-token','column':column,'direction':direction}).status_code==400
    from werkzeug.datastructures import MultiDict
    response=client.post('/account/board-sort',data=MultiDict([('csrf','sort-token'),('column','title'),('direction','asc'),('q','two words & more'),('match','all'),('tag','1'),('tag','2')]))
    assert parse_qs(urlsplit(response.location).query)=={'view':['table'],'q':['two words & more'],'match':['all'],'tag':['1','2']}
    with rendered() as contexts:
        response=client.get('/?view=table&q=does-not-exist')
    assert contexts[-1]['cases']==[] and response.status_code==200
