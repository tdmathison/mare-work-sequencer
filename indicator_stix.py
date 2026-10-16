"""Local-only STIX conversion. Import never fetches references or executes patterns."""
import copy
import hashlib
import json
import re
import time
import uuid
from datetime import datetime, timezone, timedelta
from stix2 import parse
from stix2.v21 import Bundle, Indicator, Grouping
from stix2patterns.v21.pattern import Pattern
from stix2patterns.inspector import INDEX_STAR
from stix2patterns.v21.grammars.STIXPatternListener import STIXPatternListener
from indicator_types import CATALOG, BY_NAME, canonical_type, analyze, inspect_sections

MAX_BYTES=4*1024*1024
MAX_OBJECTS=2000
MAX_PATTERN=4096
MAX_SECONDS=5


def timestamp():return datetime.now(timezone.utc).isoformat(timespec='milliseconds').replace('+00:00','Z')


def reconcile_rows(sections,current):
    """Match explicit local row identities first, then unchanged old row content."""
    previous={meta['id']:meta for section in current for meta in section.get('row_meta',[])}
    by_content={}
    for section in current:
        for row,meta in zip(section['rows'],section.get('row_meta',[])):
            by_content.setdefault(json.dumps(row,ensure_ascii=False),[]).append(meta)
    used=set();now=timestamp()
    for section in sections:
        supplied=section.get('row_meta',[]);metadata=[]
        for index,row in enumerate(section['rows']):
            result=analyze(row);row[:]=result['row']
            candidate=(supplied[index] or {}) if index<len(supplied) else {}
            old=previous.get(candidate.get('id'))
            if old and old['id'] in used:old=None
            if old is None:
                old=next((m for m in by_content.get(json.dumps(row,ensure_ascii=False),[]) if m['id'] not in used),None)
            content=json.dumps(row,ensure_ascii=False,sort_keys=True)
            digest=hashlib.sha256(content.encode()).hexdigest()
            meta=copy.deepcopy(old) if old else {'id':'indicator--'+str(uuid.uuid4()),'created':now,'modified':now}
            if meta.get('digest')!=digest:
                next_time=(datetime.fromisoformat(meta['modified'].replace('Z','+00:00'))+timedelta(milliseconds=1)).isoformat(timespec='milliseconds').replace('+00:00','Z')
                meta['modified']=max(now,next_time) if old else now
            meta['digest']=digest;metadata.append(meta);used.add(meta['id'])
        section['row_meta']=metadata
        previous_section=next((old for old in current if old['id']==section['id']),{})
        group=copy.deepcopy(previous_section.get('stix_meta'))
        group_content=[section['title'],section['description'],[meta['id'] for row,meta in zip(section['rows'],metadata) if any(value.strip() for value in row)]]
        digest=hashlib.sha256(json.dumps(group_content,ensure_ascii=False,sort_keys=True).encode()).hexdigest()
        if group is None:group={'id':'grouping--'+str(uuid.uuid4()),'created':now,'modified':now}
        elif group['digest']!=digest:
            next_time=(datetime.fromisoformat(group['modified'].replace('Z','+00:00'))+timedelta(milliseconds=1)).isoformat(timespec='milliseconds').replace('+00:00','Z')
            group['modified']=max(now,next_time)
        group['digest']=digest;section['stix_meta']=group
    return sections


def build_bundle(sections):
    report=inspect_sections(sections)
    if not report['available']:return None,report
    objects=[]
    for section in sections:
        if any(any(cell.strip() for cell in row) for row in section['rows']) and len(section.get('row_meta',[]))!=len(section['rows']):
            report.update(available=False,issues=[{'section':section['title'],'row':0,'reason':'Save the table to initialize STIX row identities.'}]);return None,report
        members=[];times=[]
        for row,meta in zip(section['rows'],section.get('row_meta',[])):
            result=analyze(row)
            if result.get('blank'):continue
            if result.get('error'):raise ValueError(result['error'])
            item=Indicator(id=meta['id'],created=meta['created'],modified=meta['modified'],valid_from=meta['created'],
                           pattern_type='stix',pattern_version='2.1',pattern=result['pattern'],
                           description=row[2] or None,labels=[f'misp:type="{result["row"][0]}"'])
            objects.append(item);members.append(item.id);times.append(meta['modified'])
        if members:
            group=section.get('stix_meta',{})
            group_id=group.get('id','grouping--'+str(uuid.uuid5(uuid.UUID(members[0].split('--')[1]),section['id'])))
            objects.append(Grouping(id=group_id,name=section['title'],description=section['description'] or None,
                                    context='unspecified',object_refs=members,created=group.get('created',min(times)),modified=group.get('modified',max(times))))
    if report['count'] and not any(obj.type=='indicator' for obj in objects):
        report.update(available=False,issues=[{'section':'Table','row':0,'reason':'Save the table to initialize STIX row identities.'}]);return None,report
    # Bundle IDs are derived from exact object content, not the export clock.
    key=uuid.uuid5(uuid.NAMESPACE_URL,json.dumps([json.loads(obj.serialize()) for obj in objects],sort_keys=True))
    bundle=Bundle(id='bundle--'+str(key),objects=objects)
    parse(bundle.serialize(),version='2.1')
    return bundle.serialize(pretty=True),report


class Shape(STIXPatternListener):
    def __init__(self):self.unsafe=False;self.equalities=0
    def visitTerminal(self,node):
        # Tokens, not a textual regex: quoted literal words cannot alter control flow.
        if node.getText() in ('OR','FOLLOWEDBY','NOT','!=','<','>','<=','>=','LIKE','MATCHES','IN','ISSUBSET','ISSUPERSET','EXISTS'):
            self.unsafe=True
    def enterPropTestEqual(self,ctx):self.equalities+=1


def unquote(value):
    if not isinstance(value,str) or not value.startswith("'") or not value.endswith("'"):
        raise ValueError('Only string equality literals are supported.')
    result=[];index=1
    while index<len(value)-1:
        if value[index]=='\\':
            index+=1
            if index>=len(value)-1 or value[index] not in ("'",'\\'):raise ValueError('Unsupported string escape.')
        result.append(value[index]);index+=1
    return ''.join(result)


def path_key(path):return path.replace("'",'')


def from_pattern(pattern,description='',hint=None):
    if not isinstance(pattern,str) or len(pattern)>MAX_PATTERN:raise ValueError('Pattern limit is 4,096 characters.')
    if pattern.count('(')+pattern.count('[')>64:raise ValueError('Pattern nesting/complexity limit exceeded.')
    compiled=Pattern(pattern);shape=Shape();compiled.walk(shape);inspection=compiled.inspect()
    if shape.unsafe or inspection.qualifiers or inspection.observation_ops:raise ValueError('Boolean alternatives, negations, observation combinations and temporal qualifiers cannot be represented faithfully as IOC rows.')
    tests=[]
    for object_type,comparisons in inspection.comparisons.items():
        for path,operator,literal in comparisons:
            if operator!='=':raise ValueError('Only equality patterns are supported.')
            joined=''
            for part in path:
                if isinstance(part,int):raise ValueError('Indexed list positions cannot be generalized to wildcard IOC rows.')
                elif part is INDEX_STAR:joined+='[*]'
                else:
                    if not isinstance(part,str) or not re.fullmatch(r'[A-Za-z0-9_-]+',part):raise ValueError('Quoted property keys containing punctuation require explicit review.')
                    joined+=('.' if joined else '')+part
            tests.append((object_type+':'+joined,unquote(literal)))
    if shape.equalities!=len(tests) or not tests:raise ValueError('Unsupported comparison shape.')
    # Exactly one catalog pattern, or its approved same-object composite; never
    # flatten arbitrary ANDs into independent rows.
    candidates=[]
    for item in CATALOG:
        paths=[path_key(path) for path in item['paths']]
        if len(paths)!=len(tests) or set(paths)!=set(path for path,value in tests):continue
        values=dict(tests)
        if len(values)!=len(tests):continue
        ordered=[values[path] for path in paths]
        if item['name'].startswith('ip-'):
            if ordered[0] not in ('ipv4-addr','ipv6-addr'):continue
            row=[item['name'],ordered[1],description]
            checked=analyze(row)
            if checked.get('pattern') and checked['key'][1][0]!=ordered[0]:continue
        else:
            if len(ordered)>1 and any('|' in value for value in ordered):raise ValueError('Composite components contain a delimiter and cannot be represented unambiguously.')
            row=[item['name'],'|'.join(ordered),description]
        candidates.append(row)
    if candidates:
        return next((row for row in candidates if row[0]==canonical_type(hint or '')),candidates[0])
    if len(tests)==1:
        path,value=tests[0]
        if path in ('ipv4-addr:value','ipv6-addr:value','email-addr:value'):
            return ['IP' if path.startswith('ipv') else 'email',value,description]
        # A real extractable scalar remains correctable without inventing a type.
        return [path,value,description]
    raise ValueError('This composite pattern has no faithful canonical table representation; it was not split into rows.')


def import_document(raw):
    if len(raw)>MAX_BYTES:raise ValueError('STIX uploads are limited to 4 MiB.')
    try:data=json.loads(raw.decode('utf-8-sig'))
    except (ValueError,UnicodeError,RecursionError) as exc:raise ValueError('Upload a valid UTF-8 STIX 2.1 JSON document.') from exc
    if not isinstance(data,dict):raise ValueError('Expected a STIX 2.1 object or Bundle.')
    objects=data.get('objects',[]) if data.get('type')=='bundle' else [data]
    if not isinstance(objects,list) or len(objects)>MAX_OBJECTS:raise ValueError('STIX documents may contain at most 2,000 objects.')
    if any(not isinstance(item,dict) or not isinstance(item.get('type'),str) for item in objects):raise ValueError('Every STIX object requires a type.')
    if data.get('type')=='bundle':
        try:
            if not isinstance(data.get('id'),str) or not data['id'].startswith('bundle--'):raise ValueError()
            uuid.UUID(data['id'][8:])
        except ValueError:raise ValueError('STIX Bundles require a valid bundle--UUID identifier.')
    index={};rows=[];skipped=[];started=time.monotonic()
    for obj in objects:
        if len(json.dumps(obj))>256*1024:raise ValueError('An individual STIX object exceeds 256 KiB.')
        identifier=obj.get('id')
        try:
            if not isinstance(identifier,str) or not identifier.startswith(obj['type']+'--'):raise ValueError()
            uuid.UUID(identifier.split('--',1)[1])
        except (ValueError,AttributeError):raise ValueError('Every STIX 2.1 object requires a valid type--UUID identifier.')
        if identifier:

            if identifier in index:raise ValueError('Duplicate STIX object IDs in uploaded document.')
            index[identifier]=obj
    def skip(obj,reason):skipped.append({'id':obj.get('id','(no ID)'),'type':obj['type'],'reason':reason})
    def local(reference):
        if not isinstance(reference,str) or reference not in index:raise ValueError('Observable reference is missing from this uploaded document; external references are never fetched.')
        return index[reference]
    for obj in objects:
        if time.monotonic()-started>MAX_SECONDS:raise ValueError('STIX import processing limit exceeded; split the document.')
        kind=obj['type']
        try:
            if obj.get('spec_version','2.1')!='2.1':raise ValueError('Only STIX 2.1 objects are supported.')
            if kind=='indicator':
                if any(key not in obj for key in ('created','modified','valid_from','pattern','pattern_type')):raise ValueError('Malformed Indicator: created, modified, valid_from, pattern and pattern_type are required.')
                if obj.get('pattern_type')!='stix':raise ValueError('Non-STIX patterns (including YARA/Sigma) are not IOC values.')
                if obj.get('revoked') or obj.get('valid_until') or obj.get('object_marking_refs') or obj.get('granular_markings'):raise ValueError('Revocation, expiry or marking semantics need review before conversion.')
                if len(obj.get('pattern',''))>MAX_PATTERN:raise ValueError('Pattern limit is 4,096 characters.')
                # Standards library validates required fields and the pattern grammar.
                parsed=parse(obj,version='2.1',allow_custom=True)
                if parsed.valid_from>datetime.now(timezone.utc):raise ValueError('Future validity starts require review; the table cannot preserve that detection window.')
                hints=[label[11:-1] for label in obj.get('labels',[]) if label.startswith('misp:type="') and label.endswith('"')]
                rows.append(from_pattern(obj['pattern'],obj.get('description',''),hints[0] if hints else None))
            elif kind in ('domain-name','url','mac-addr','ipv4-addr','ipv6-addr','email-addr','mutex','file','windows-registry-key','x509-certificate','network-traffic','email-message'):
                parse(obj,version='2.1',allow_custom=True)
                if obj.get('defanged') or obj.get('object_marking_refs') or obj.get('granular_markings'):raise ValueError('Defanged/marked observables require explicit analyst review.')
                description=obj.get('description','')
                tests=[]
                if kind in ('domain-name','url','mac-addr','ipv4-addr','ipv6-addr','email-addr'):tests=[(kind+':value',obj['value'])]
                elif kind=='mutex':tests=[('mutex:name',obj['name'])]
                elif kind in ('file','x509-certificate'):
                    hashes=obj.get('hashes',{})
                    if len(hashes)>1:raise ValueError('Multiple simultaneous hash constraints cannot be flattened into independent rows.')
                    if kind=='file' and obj.get('name'):tests.append(('file:name',obj['name']))
                    tests.extend((kind+':hashes.'+key,value) for key,value in hashes.items())
                elif kind=='windows-registry-key':
                    tests=[('windows-registry-key:key',obj['key'])]
                    if obj.get('values'):
                        if len(obj['values'])!=1 or set(obj['values'][0])-{'data'}:raise ValueError('Registry value names/types or multiple values cannot be represented in a key|data row.')
                        tests.append(('windows-registry-key:values[*].data',obj['values'][0]['data']))
                elif kind=='network-traffic':
                    roles=[role for role in ('src','dst') if role+'_ref' in obj]
                    if len(roles)!=1 or any(key in obj for key in ('src_port','dst_port','extensions')):raise ValueError('Traffic tuples, ports and extensions cannot be split into unrelated address rows.')
                    target=local(obj[roles[0]+'_ref'])
                    if target['type'] not in ('ipv4-addr','ipv6-addr'):raise ValueError('Traffic reference must identify an uploaded IP observable.')
                    tests=[('network-traffic:'+roles[0]+'_ref.type',target['type']),('network-traffic:'+roles[0]+'_ref.value',target['value'])]
                elif kind=='email-message':
                    roles=[role for role in ('from_ref','to_refs','subject','body_multipart') if role in obj]
                    if len(roles)!=1:raise ValueError('Multi-field email content cannot be flattened without losing its constraints.')
                    role=roles[0]
                    if role=='subject':tests=[('email-message:subject',obj['subject'])]
                    elif role in ('from_ref','to_refs'):
                        refs=[obj['from_ref']] if role=='from_ref' else obj['to_refs']
                        if len(refs)!=1:raise ValueError('Multiple recipients require review.')
                        target=local(refs[0])
                        if target['type']!='email-addr':raise ValueError('Expected an uploaded email-addr reference.')
                        tests=[('email-message:'+('from_ref.value' if role=='from_ref' else 'to_refs[*].value'),target['value'])]
                    else:
                        parts=obj['body_multipart']
                        if len(parts)!=1:raise ValueError('Multiple MIME parts require review.')
                        target=local(parts[0].get('body_raw_ref'))
                        if target['type']!='file' or not target.get('name'):raise ValueError('Attachment needs an uploaded file name.')
                        tests=[('email-message:body_multipart[*].body_raw_ref.name',target['name'])]
                if not tests:raise ValueError('No supported scalar indicator value was supplied.')
                from indicator_types import literal
                rows.append(from_pattern('['+' AND '.join(path+' = '+literal(value) for path,value in tests)+']',description))
            else:skip(obj,'Context/unsupported STIX object; no independent IOC row was invented.')
        except Exception as error:
            skip(obj,str(error)[:500])
    if len(rows)>10000:raise ValueError('Import exceeds 10,000 rows.')
    return rows,skipped
