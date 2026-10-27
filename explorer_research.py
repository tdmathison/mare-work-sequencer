"""Bounded authorization-first evidence and paths for the authenticated Explorer."""
from collections import defaultdict, deque
from time import monotonic
from flask import abort, request, jsonify, url_for

MAX_AUTHORIZED=1600
MAX_DEPTH=8
MAX_PATHS=12
MAX_SECONDS=.25

def shortest_paths(nodes,edges,source,target,max_depth=MAX_DEPTH):
    known={n['id'] for n in nodes}
    if source not in known or target not in known:raise ValueError('Choose two available, distinct entity objects.')
    if source==target:raise ValueError('Choose two distinct objects.')
    adjacency=defaultdict(set)
    for e in edges:adjacency[e['source']].add(e['target']);adjacency[e['target']].add(e['source'])
    distance={source:0};parents=defaultdict(list);queue=deque([source]);limited=False;started=monotonic()
    while queue:
        if monotonic()-started>MAX_SECONDS:limited=True;break
        node=queue.popleft();depth=distance[node]
        if target in distance and depth>=distance[target]:continue
        if depth>=max_depth:limited=True;continue
        for other in sorted(adjacency[node]):
            if other not in distance:distance[other]=depth+1;queue.append(other)
            if distance[other]==depth+1:parents[other].append(node)
    paths=[]
    if target in distance:
        stack=[(target,[target])]
        while stack:
            if len(paths)>=MAX_PATHS or monotonic()-started>MAX_SECONDS:limited=True;break
            node,path=stack.pop()
            if node==source:paths.append(list(reversed(path)));continue
            for parent in reversed(parents[node]):stack.append((parent,path+[parent]))
    return {'paths':paths,'limited':limited,'max_depth':max_depth,'max_paths':MAX_PATHS,'runtime_seconds':MAX_SECONDS}

def register_research(app,db,require,graph,snapshot_categories):
    def dataset(all_data=False,matching=True):
        allowed=require();kinds=request.args.getlist('type') or ('case','family','actor')
        if kinds==['none']:kinds=()
        if any(k not in ('case','family','actor') for k in kinds):abort(400)
        result,status=graph(db(),allowed,'' if all_data else request.args.get('q','')[:200],('case','family','actor') if all_data else kinds,limit=MAX_AUTHORIZED if all_data else 400,edge_limit=20000)
        if status!=200:abort(status,description=result['error'])
        if matching and request.args.get('shared')=='1':
            from explorer_shared import shared_edges,shared_options
            types,minimum=shared_options(request.args);computed,limited=shared_edges(db(),allowed,result['nodes'],types,minimum)
            result['edges'].extend(computed);result['shared_limited']=limited
        return result,allowed
    def category_evidence(source,target):
        bits=target.split(':')
        if len(bits)!=3 or bits[0]!='case' or not bits[1].isdigit() or len(bits[1])>18 or source!='case:'+bits[1]:return None
        groups,_=snapshot_categories(int(bits[1]));group=groups.get(bits[2])
        if not group:abort(404)
        record=db().execute('SELECT number,name FROM cases WHERE id=?',(int(bits[1]),)).fetchone()
        return {'source':{'id':source,'label':record['number']+' · '+record['name'],'url':url_for('detail',cid=int(bits[1]))},'target':{'id':target,'label':group['label'],'url':url_for('detail',cid=int(bits[1]),tab='package')},'relationship_type':'Standard MIP category','computed':False,'reason':group['definition'],'evidence':[{'label':f"{group['count']} included items in the saved Standard package",'url':url_for('detail',cid=int(bits[1]),tab='package')}]}
    def evidence_node(identity,allowed):
        bits=identity.split(':')
        if len(bits)!=2:return None
        kind,uid=bits
        if kind=='case' and allowed['cases:read']:
            if not uid.isdigit() or len(uid)>19 or int(uid)>9223372036854775807:return None
            row=db().execute('SELECT id,name,number FROM cases WHERE id=?',(int(uid),)).fetchone()
            if not row:return None
            return dict(id=identity,uid=row['id'],kind=kind,name=row['name'],number=row['number'],label=row['number']+' · '+row['name'],url=url_for('detail',cid=row['id']))
        if kind in ('family','actor') and allowed['tags:read']:
            table,prefix=('malware_families','MAL_') if kind=='family' else ('threat_actors','TA_')
            row=db().execute(f'SELECT f.id,f.name,f.tag_id,t.name tag FROM {table} f JOIN tags t ON t.id=f.tag_id WHERE f.id=? AND substr(t.name,1,?)=? AND length(t.name)>?',(uid,len(prefix),prefix,len(prefix))).fetchone()
            if not row:return None
            return dict(id=identity,uid=row['id'],kind=kind,name=row['name'],tag=row['tag'],tag_id=row['tag_id'],label=row['name'],url=url_for('families_workspace' if kind=='family' else 'actors_workspace',fid=row['id']))
        return None
    @app.get('/data-explorer/evidence')
    def explorer_evidence():
        allowed=require();source=request.args.get('source','');target=request.args.get('target','')
        if len(source)>160 or len(target)>160:abort(400)
        if target.count(':')==2:
            result=category_evidence(source,target)
            if result:return jsonify(result),200,{'Cache-Control':'private, no-store'}
        if source.count(':')==2:
            result=category_evidence(target,source)
            if result:return jsonify(result),200,{'Cache-Control':'private, no-store'}
        a=evidence_node(source,allowed);b=evidence_node(target,allowed)
        if not a or not b or source==target:abort(404)
        computed=False;indicators=[];evidence_limited=False
        if a['kind']!='case' and b['kind']=='case':a,b=b,a
        if a['kind']=='case' and b['kind'] in ('family','actor'):
            if not db().execute('SELECT 1 FROM case_tags WHERE case_id=? AND tag_id=?',(a['uid'],b['tag_id'])).fetchone():abort(404)
            kind='Case tag assignment';reason='Case carries '+b['tag']
        elif {a['kind'],b['kind']}=={'family','actor'}:
            family=a if a['kind']=='family' else b;actor=a if a['kind']=='actor' else b
            if not db().execute('SELECT 1 FROM actor_families WHERE actor_id=? AND family_id=?',(actor['uid'],family['uid'])).fetchone():abort(404)
            kind='Configured profile association';reason='Configured profile association'
        elif a['kind']==b['kind']=='case' and request.args.get('shared')=='1':
            from explorer_shared import shared_edges,shared_options
            types,minimum=shared_options(request.args);edges,_=shared_edges(db(),allowed,[a,b],types,minimum,evidence=True)
            if not edges:abort(404)
            edge=edges[0];kind='Shared indicators';reason=edge['explanation'];indicators=edge['indicators'];computed=True;evidence_limited=edge['evidence_limited']
        else:abort(404)
        evidence=[{'label':a['label'],'url':a['url']},{'label':b['label'],'url':b['url']}]
        return jsonify(source=a,target=b,relationship_type=kind,computed=computed,reason=reason,evidence=evidence,indicators=indicators,evidence_limited=evidence_limited),200,{'Cache-Control':'private, no-store'}
    @app.get('/data-explorer/connection-objects')
    def explorer_connection_objects():
        data,_=dataset(request.args.get('scope')=='all',matching=False);return jsonify(nodes=[{k:n[k] for k in ('id','kind','label')} for n in data['nodes']]),200,{'Cache-Control':'private, no-store'}
    @app.get('/data-explorer/connections')
    def explorer_connections():
        data,_=dataset(request.args.get('scope')=='all')
        if request.args.get('scope')!='all' and 'ids' in request.args:
            import json
            try:
                ids=json.loads(request.args['ids'])
                if not isinstance(ids,list) or len(ids)>400 or not all(isinstance(n,str) for n in ids):raise ValueError('Invalid visible graph scope.')
            except (ValueError,AssertionError):abort(400)
            ids=set(ids);data['nodes']=[n for n in data['nodes'] if n['id'] in ids];data['edges']=[e for e in data['edges'] if e['source'] in ids and e['target'] in ids]
        try:
            depth=int(request.args.get('depth',MAX_DEPTH))
            if not 1<=depth<=MAX_DEPTH:raise ValueError('Depth must be 1–8.')
            paths=shortest_paths(data['nodes'],data['edges'],request.args.get('source',''),request.args.get('target',''),depth);paths['limited']=paths['limited'] or data.get('edge_limited',False)
        except (ValueError,AssertionError) as exc:return {'error':str(exc) or 'Invalid depth.'},400
        wanted={node for path in paths['paths'] for node in path}
        return jsonify(**paths,nodes=[n for n in data['nodes'] if n['id'] in wanted],edges=[e for e in data['edges'] if e['source'] in wanted and e['target'] in wanted],scope='all authorized entity data' if request.args.get('scope')=='all' else 'current filtered entity graph',shared_limited=data.get('shared_limited',False)),200,{'Cache-Control':'private, no-store'}
