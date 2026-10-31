"""Read-only Tags profile workspace adapters over the existing catalog and CRUD."""
from flask import abort, render_template, request, url_for
from case_queries import CASE_ELIGIBILITY
from tagging import catalog, invalid_legacy

PAGE_SIZE = 50
NAMESPACES = {'all':'All', 'malware':'Malware', 'actors':'Threat actors', 'other':'Other'}


def namespace(value):
    return 'malware' if value.startswith('MAL_') else 'actors' if value.startswith('TA_') else 'other'


def register_workspace(app, db, allowed, require):
    def visible_catalog(query, sort):
        return catalog(db(),query,sort,case_access=allowed('cases:read'))

    def workspace(tid=None):
        require('tags:read')
        query = request.args.get('q','')[:200]
        sort = request.args.get('sort','name')
        kind = request.args.get('namespace','all')
        tab = request.args.get('tab','overview')
        if sort not in ('name','most','least') or kind not in NAMESPACES or tab not in ('overview','history'):abort(400)
        try:
            page=max(1,int(request.args.get('page','1')))
            case_page=max(1,int(request.args.get('case_page','1')))
        except ValueError:abort(400)
        all_tags=visible_catalog('',sort)
        families={r['tag_id']:dict(r) for r in db().execute('SELECT id,tag_id,name FROM malware_families')}
        actors={r['tag_id']:dict(r) for r in db().execute('SELECT id,tag_id,name FROM threat_actors')}
        def association(tag):
            ns=namespace(tag['name'])
            table,endpoint,label,prefix=(families,'families','malware family','MAL_') if ns=='malware' else (actors,'actors','threat actor','TA_')
            linked=table.get(tag['id']) if ns!='other' else None
            # register_profiles uses tags:read/manage for both profile types.
            can_read=allowed('tags:read')
            return dict(exists=bool(linked),name=linked['name'] if linked and can_read else None,
                url=url_for(endpoint+'_workspace',fid=linked['id'],tab='overview') if linked and can_read else None,
                create_url=url_for(endpoint+'_edit',tag_id=tag['id']) if ns!='other' and not linked and allowed('tags:manage') and can_read and len(tag['name'])>len(prefix) else None,
                label=label,status=('Linked '+label if can_read else 'Profile access restricted') if linked else 'No linked '+label if ns!='other' else 'Case tag')
        for tag in all_tags:
            tag['namespace']=namespace(tag['name']);tag['type_label']=NAMESPACES[tag['namespace']]
            tag['profile']=association(tag);tag['protected']=tag['id'] in families or tag['id'] in actors
        requested=next((t for t in all_tags if t['id']==tid),None) if tid is not None else None
        if tid is not None and requested is None:abort(404)
        matches={t['id'] for t in visible_catalog(query,sort)}
        filtered=[t for t in all_tags if t['id'] in matches and (kind=='all' or t['namespace']==kind)]
        pages=max(1,(len(filtered)+PAGE_SIZE-1)//PAGE_SIZE)
        if requested in filtered:page=filtered.index(requested)//PAGE_SIZE+1
        page=min(page,pages)
        entries=filtered[(page-1)*PAGE_SIZE:page*PAGE_SIZE]
        tag=requested if requested in entries else entries[0] if entries else None
        cases=[];case_pages=max(1,((tag['uses'] if tag else 0)+PAGE_SIZE-1)//PAGE_SIZE)
        case_page=min(case_page,case_pages)
        if tag and tab=='history' and allowed('cases:read'):
            cases=[dict(r) for r in db().execute('''SELECT DISTINCT c.id,c.number,c.name,c.stage FROM cases c
                JOIN case_tags ct ON ct.case_id=c.id WHERE ct.tag_id=? AND ('''+CASE_ELIGIBILITY+''')
                ORDER BY c.id DESC LIMIT ? OFFSET ?''',(tag['id'],PAGE_SIZE,(case_page-1)*PAGE_SIZE))]
        def directory_url(**changes):
            values=dict(q=query,namespace=kind,sort=sort,page=page);values.update(changes)
            return url_for('tags_manager',**values)
        def tag_url(identity=None,**changes):
            values=dict(q=query,namespace=kind,sort=sort,page=page,tab=tab);values.update(changes)
            return url_for('tag_detail',tid=identity if identity is not None else tag['id'],**values)
        return render_template('tags.html',tags=entries,tag=tag,all_tags=all_tags,invalid_tags=invalid_legacy(db()),
            query=query,sort=sort,namespace=kind,namespaces=NAMESPACES,tab=tab,page=page,pages=pages,total=len(filtered),
            cases=cases,can_cases=allowed('cases:read'),case_page=case_page,case_pages=case_pages,
            directory_url=directory_url,tag_url=tag_url,selected_url=tag_url() if tag else directory_url())

    app.add_url_rule('/tags','tags_manager',workspace)
    app.add_url_rule('/tags/<int:tid>','tag_detail',workspace)
