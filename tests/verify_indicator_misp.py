"""Optional offline MISP conversion probe; run with an isolated misp-stix venv."""
import json
import sys
import socket

def no_network(*args,**kwargs):
    raise AssertionError("MISP verification must remain offline")
socket.socket.connect=no_network
from pathlib import Path
from stix2 import parse
from misp_stix_converter import InternalSTIX2toMISPParser

parser=InternalSTIX2toMISPParser()
parser.load_stix_bundle(parse(Path(sys.argv[1]).read_text(),version='2.1'))
parser.parse_stix_bundle()
events=parser.misp_events
if not isinstance(events,list):events=[events]
result={'events':[], 'attributes':[], 'errors':dict(parser.errors), 'warnings':parser.warnings}
for event in events:
    data=json.loads(event.to_json());data=data.get('Event',data)
    result['events'].append(data.get('info'))
    result['attributes'].extend(data.get('Attribute',[]))
print(json.dumps(result))
