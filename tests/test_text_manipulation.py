from dataclasses import replace
import pytest
from app import app, db, run
from text_manipulation import process


def result(op,text):return process(op,text)['text']


def test_ip_validation_and_order():
    text='x 999.1.2.3 1.2.3.4.5 ::ffff:192.0.2.1 [2001:DB8::1] 8.8.8.8 2001:db8:0:0:0:0:0:1 8.8.8.8 1.1.1.1'
    assert result('ipv4','Connection 8.8.8.8:443')=='8.8.8.8'
    assert result('ipv4',text)=='8.8.8.8\n1.1.1.1'
    assert result('ipv6',text)=='::ffff:c000:201\n2001:db8::1'
    assert result('all-ips',text)=='8.8.8.8\n1.1.1.1\n::ffff:c000:201\n2001:db8::1'
    assert result('cidrs','192.168.1.50/24 192.168.1.0/24 1.2.3.4/33 999.2.3.4/8 2001:db8::/32')=='192.168.1.0/24'
    assert result('ips-domains','a.example.org ::1 1.1.1.1 a.example.org')=='a.example.org\n::1\n1.1.1.1'


def test_domains_urls_emails():
    assert result('domains','User@EXAMPLE.com https://例子.测试/path X.foo-bar.com 1.2.3.4 bad..com -bad.com')=='xn--fsqu00a.xn--0zwm56d\nx.foo-bar.com'
    assert result('emails','USER.name+tag@example.org user.name+tag@EXAMPLE.org other@example.net')=='USER.name+tag@example.org\nother@example.net'
    assert result('urls','See (https://example.org/a_(b)?q=1,2#frag), ftp://example.com/a and https://[2001:db8::1]:8443/path')=='https://example.org/a_(b)?q=1,2#frag\nftp://example.com/a\nhttps://[2001:db8::1]:8443/path'


def test_iana_classification_and_numeric_sort():
    nonglobal=['10.1.2.3','127.0.0.1','169.254.1.1','100.64.0.1','192.0.2.1','198.18.0.1','224.1.1.1','250.0.0.1','::','::1','fc00::1','fe80::1','2001:db8::1','ff02::1','3fff::1']
    text='\n'.join(nonglobal+['8.8.8.8','2606:4700:4700::1111','192.0.0.9','log 10.1.2.3','999.1.2.3'])
    assert result('non-routable',text)=='8.8.8.8\n2606:4700:4700::1111\n192.0.0.9\nlog 10.1.2.3\n999.1.2.3'
    sorted_ips=process('ip-sort','11.1.1.1\n::2\n2.2.2.2\nbad\n::1\n2.2.2.2')
    assert sorted_ips['text']=='2.2.2.2\n2.2.2.2\n11.1.1.1\n::1\n::2\nbad' and sorted_ips['warning']


def test_defang_refang_round_trip():
    text='IP 8.8.8.8 and 2001:db8::1 URL https://EXAMPLE.com/a?q=1.2#x domain example.org irrelevant a[.]b'
    safe=result('defang',text)
    assert 'hxxps://EXAMPLE[.]com/a?q=1.2#x' in safe and '2001[:]db8[:][:]1' in safe
    assert result('defang',safe)==safe
    assert result('refang',safe)==text


def test_formatting_preserves_content_and_rejects_invalid_input():
    assert result('json','{"a":9007199254740993,"f":0.12345678901234567890}')=='{\n    "a": 9007199254740993,\n    "f": 0.12345678901234567890\n}'
    assert '<r>\n    <a x="y"/>' in result('xml','<?xml version="1.0"?><r><a x="y"/><b/></r>')
    assert result('xml','<p>Hello <b>world</b> !</p>')=='<p>Hello <b>world</b> !</p>'
    assert result('xml','<p xml:space="preserve">  <b/> </p>')=='<p xml:space="preserve">  <b/> </p>'
    assert result('python','x=[1,2,3]\n')=='x = [1, 2, 3]\n'
    for op,text in [('json','{'),('json','NaN'),('json','{"x":1,"x":2}'),('xml','<broken>'),('xml','<!DOCTYPE x [<!ENTITY x SYSTEM "file:///etc/passwd">]><x>&x;</x>'),('python','def broken(:')]:
        with pytest.raises(ValueError):result(op,text)


def test_routes_auth_csrf_registry_and_validation():
    assert app.test_client().get('/tools/text-manipulation/app/').status_code==302
    with app.app_context():uid=run("INSERT INTO users(username,password,role,forced) VALUES('text-user','unused','User',0)").lastrowid
    client=app.test_client()
    with client.session_transaction() as session:session.update(uid=uid,version=1,csrf='text-token')
    assert b'tool-tab-text-manipulation' in client.get('/tools').data
    assert client.get('/tools/text-manipulation/app/').status_code==200
    assert client.post('/tools/text-manipulation/process',data={'operation':'ipv4','text':'1.1.1.1'}).status_code==403
    response=client.post('/tools/text-manipulation/process',data={'csrf':'text-token','operation':'ipv4','text':'1.1.1.1'})
    assert response.json['text']=='1.1.1.1' and response.headers['Cache-Control']=='no-store'
    assert client.post('/tools/text-manipulation/process',data={'csrf':'text-token','operation':'bogus','text':'x'}).status_code==400
    assert client.post('/tools/text-manipulation/process',data={'csrf':'text-token','operation':'xml','text':'x'* (2*1024*1024+1)}).status_code==413
    tool=app.extensions['analyst_tools']['text-manipulation']
    app.extensions['analyst_tools']['text-manipulation']=replace(tool,enabled=False)
    try:assert client.get('/tools/text-manipulation/app/').status_code==404
    finally:app.extensions['analyst_tools']['text-manipulation']=tool
