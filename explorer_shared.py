"""Conservative, bounded matching of saved structured indicators. No cache or writes."""
import ipaddress
import json
import re
from collections import defaultdict
from itertools import combinations
from time import monotonic
from urllib.parse import urlsplit, urlunsplit
from flask import abort

TYPES=('md5','sha1','sha256','domain','ip','url')
HASHES={'md5':32,'sha1':40,'sha256':64}

def domain(value):
    if value.endswith('..'):raise ValueError('Invalid domain')
    value=value.rstrip('.').encode('idna').decode('ascii').lower()
    labels=value.split('.')
    if len(value)>253 or len(labels)<2 or any(not re.fullmatch(r'[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?',part) for part in labels):raise ValueError('Invalid domain')
    return value

def normalize(kind,value):
    if not isinstance(kind,str) or not isinstance(value,str):return None
    kind=kind.strip().lower();value=value.strip()
    if not value or len(value)>4000:return None
    try:
        if kind in HASHES:
            if not re.fullmatch('[a-fA-F0-9]{'+str(HASHES[kind])+'}',value):return None
            return kind,value.lower()
        if kind=='domain':return kind,domain(value)
        if kind in ('ip','ip-src','ip-dst'):
            if '%' in value:return None
            return kind,str(ipaddress.ip_address(value))
        if kind=='url':
            if any(c.isspace() or ord(c)<33 for c in value) or '\\' in value:return None
            parsed=urlsplit(value)
            if parsed.scheme.lower() not in ('http','https') or not parsed.hostname or '%' in parsed.hostname or parsed.username or parsed.password:return None
            try:host=str(ipaddress.ip_address(parsed.hostname));host='['+host+']' if ':' in host else host
            except ValueError:host=domain(parsed.hostname)
            port=parsed.port
            if port is not None and not 1<=port<=65535:return None
            if port is not None and (parsed.scheme.lower(),port) not in (('http',80),('https',443)):host+=':'+str(port)
            return kind,urlunsplit((parsed.scheme.lower(),host,parsed.path,parsed.query,parsed.fragment))
    except (ValueError,UnicodeError):return None
    return None

def shared_options(args):
    types=args.getlist('indicator_type') or list(TYPES)
    if len(types)>6 or any(t not in TYPES for t in types):abort(400)
    try:minimum=int(args.get('minimum',1))
    except ValueError:abort(400)
    if not 1<=minimum<=100:abort(400)
    return set(types),minimum

def shared_edges(connection,allowed,nodes,types,minimum,evidence=False):
    if not allowed['cases:read'] or not allowed['indicators:read']:abort(403)
    connection.execute('SAVEPOINT explorer_shared_read')
    try:return _shared_edges(connection,allowed,nodes,types,minimum,evidence)
    finally:connection.execute('RELEASE explorer_shared_read')

def _shared_edges(connection,allowed,nodes,types,minimum,evidence):
    if not allowed['cases:read'] or not allowed['indicators:read']:abort(403)
    ids={int(n['uid']) for n in nodes if n['kind']=='case'}
    if not ids:return [],False
    # Stream authorized carriers through indexed case IDs; do not materialize
    # other cases or all matching blobs before enforcing inspection bounds.
    inverted=defaultdict(set);rows_seen=0;limited=False;ordered=sorted(ids);deadline=monotonic()+.5
    for start in range(0,len(ordered),400):
        chunk=ordered[start:start+400];slots=','.join('?' for _ in chunk)
        records=connection.execute(f'SELECT c.id,s.sections,t.rows FROM cases c LEFT JOIN indicator_sections s ON s.case_id=c.id LEFT JOIN indicator_tables t ON t.case_id=c.id WHERE c.id IN ({slots}) ORDER BY c.id',chunk)
        for record in records:
            raw=record['sections'] or record['rows'] or '[]'
            if len(raw)>16*1024*1024:limited=True;continue
            try:
                decoded=json.loads(raw)
                rows=(row for section in decoded for row in section['rows']) if record['sections'] else iter(decoded)
                unique=set()
                for row in rows:
                    rows_seen+=1
                    if rows_seen>200000 or (rows_seen%128==0 and monotonic()>deadline):limited=True;break
                    if not isinstance(row,list) or len(row)<2:continue
                    item=normalize(row[0],row[1])
                    if item and ('ip' if item[0] in ('ip-src','ip-dst') else item[0]) in types:unique.add(item)
            except (ValueError,TypeError,KeyError):limited=True;continue
            for item in unique:
                if len(inverted)>=100000 and item not in inverted:limited=True;continue
                inverted[item].add(record['id'])
            if rows_seen>200000 or monotonic()>deadline:limited=True;break
        if rows_seen>200000 or monotonic()>deadline:limited=True;break
    pairs={};comparisons=0
    for item,cases in sorted(inverted.items()):
        if len(cases)>100:limited=True;continue
        for pair in combinations(sorted(cases),2):
            comparisons+=1
            if comparisons>100000 or (comparisons%256==0 and monotonic()>deadline):limited=True;break
            if pair not in pairs:
                if len(pairs)>=2000:limited=True;continue
                pairs[pair]={'count':0,'indicators':[]}
            match=pairs[pair];match['count']+=1
            if evidence and len(match['indicators'])<200:match['indicators'].append({'type':item[0],'value':item[1]})
        if comparisons>100000 or monotonic()>deadline:limited=True;break
    edges=[]
    for (a,b),match in sorted(pairs.items()):
        if match['count']<minimum:continue
        label=('At least ' if limited else '')+str(match['count'])+' shared indicators'
        edges.append(dict(id=f'shared:case:{a}:case:{b}',source=f'case:{a}',target=f'case:{b}',computed=True,explanation=label+' · overlap does not establish common attribution',count=match['count'],**({'indicators':match['indicators'],'evidence_limited':match['count']>len(match['indicators'])} if evidence else {})))
    return edges,limited

def register_shared(app,db,require,graph):
    @app.get('/data-explorer/shared-indicators')
    def explorer_shared_indicators():
        from flask import jsonify,request
        allowed=require();kinds=request.args.getlist('type') or ('case','family','actor')
        if kinds==['none']:kinds=()
        if any(k not in ('case','family','actor') for k in kinds):abort(400)
        data,status=graph(db(),allowed,request.args.get('q','')[:200],kinds)
        if status!=200:return jsonify(data),status
        types,minimum=shared_options(request.args);edges,limited=shared_edges(db(),allowed,data['nodes'],types,minimum)
        return jsonify(edges=edges,limited=limited,note='Computed overlap only; no common attribution. Limits: 500 ms matching, 200,000 rows, 100,000 pair contributions, 2,000 edges; indicators shared by more than 100 cases are omitted.'),200,{'Cache-Control':'private, no-store'}
