"""Generated SDK carries the validated Case TLP enum without forcing a default."""
import json
import httpx
import pytest
from mws_sdk import MWSClient
from mws_sdk.models import CasesCreateRequest, CasesUpdateRequest
from mws_sdk.utilities import encode
from pydantic import ValidationError


def test_tlp_enum_and_omission():
    assert 'tlp' not in encode(CasesCreateRequest(name='Use configured default'))
    for value in ['TLP:RED','TLP:AMBER+STRICT','TLP:AMBER','TLP:GREEN','TLP:CLEAR']:
        assert encode(CasesCreateRequest(name='Designated',tlp=value))['tlp']==value
        assert encode(CasesUpdateRequest(tlp=value))=={'tlp':value}
    for value in ['','TLP:WHITE','TLP-AMBER','amber']:
        with pytest.raises(ValidationError): CasesCreateRequest(name='Invalid',tlp=value)


def test_create_and_update_round_trip_tlp():
    bodies=[]
    def handler(request):
        body=json.loads(request.content);bodies.append(body)
        return httpx.Response(201 if request.method=='POST' else 200,json={'case':{'id':1,'name':'Designated','tlp':body.get('tlp','TLP:GREEN')}})
    with MWSClient('https://example.test','secret',transport=httpx.MockTransport(handler)) as client:
        assert client.cases.create(data={'name':'Default'}).case.tlp=='TLP:GREEN'
        assert client.cases.create(data={'name':'Explicit','tlp':'TLP:AMBER+STRICT'}).case.tlp=='TLP:AMBER+STRICT'
        assert client.cases.update(1,data={'tlp':'TLP:RED'}).case.tlp=='TLP:RED'
    assert 'tlp' not in bodies[0]
