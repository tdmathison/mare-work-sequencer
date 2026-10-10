"""Local validated IOC operations and formatters. No sample execution or DNS."""
import ipaddress
import json
import re
from decimal import Decimal
from pathlib import Path
from urllib.parse import urlsplit
from xml.dom import minidom, Node

LIMIT = 2 * 1024 * 1024
REGISTRY = json.loads((Path(__file__).parent/'resources/ip-special-purpose.json').read_text())
NETWORKS = sorted([(ipaddress.ip_network(row['network']), row['global']) for row in REGISTRY['networks']], key=lambda row: row[0].prefixlen, reverse=True)
TOKEN = re.compile(r'[\w.:%-]+', re.UNICODE)
DOMAIN = re.compile(r'(?<![\w@.-])(?:[^\W_][\w-]*\.)+[^\W_][\w-]*(?![\w.-])', re.UNICODE)
EMAIL = re.compile(r"(?<![\w.!#$%&'*+/=?^`{|}~-])[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@(?:[^\W_][\w-]*\.)+[^\W_][\w-]*", re.UNICODE)
URL = re.compile(r'(?i)\b(?:https?|ftp)://[^\s<>"\x00-\x1f]+')


def address(value):
    try:
        if '%' in value: return None  # Scope identifiers are local interface metadata.
        return ipaddress.ip_address(value)
    except ValueError: return None


def domain(value):
    try:
        result = value.rstrip('.').encode('idna').decode('ascii').lower()
    except UnicodeError: return None
    labels = result.split('.')
    if len(result)>253 or len(labels)<2 or not re.fullmatch(r'(?:[a-z]{2,63}|xn--[a-z0-9-]{2,59})',labels[-1]): return None
    if any(not re.fullmatch(r'[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?',label) for label in labels): return None
    return result


def ip_spans(text):
    for match in TOKEN.finditer(text):
        token = match.group()
        # A terminal sentence dot isn't part of an address, but extra octets are.
        if token.endswith('.') and not token.endswith('..'): token=token[:-1]
        ip = address(token)
        if not ip and token.count(':')==1:
            host,port=token.split(':')
            candidate=address(host)
            if candidate and candidate.version==4 and port.isdigit() and 0<=int(port)<=65535:
                token=host;ip=candidate
        if ip: yield match.start(), match.start()+len(token), str(ip), 'ip'


def email_spans(text):
    for match in EMAIL.finditer(text):
        value=match.group().rstrip('.')
        local,host=value.rsplit('@',1)
        if len(local)<=64 and not local.startswith('.') and not local.endswith('.') and '..' not in local and domain(host):
            yield match.start(),match.start()+len(value),value,'email'


def domain_spans(text):
    emails=list(email_spans(text))
    for match in DOMAIN.finditer(text):
        if any(a<=match.start()<b for a,b,_,_ in emails): continue
        value=domain(match.group())
        if value: yield match.start(),match.end(),value,'domain'


def url_spans(text):
    for match in URL.finditer(text):
        value=match.group().rstrip('.,;!\'')
        for left,right in [('(',')'),('[',']'),('{','}')]:
            while value.endswith(right) and value.count(right)>value.count(left): value=value[:-1]
        try:
            parsed=urlsplit(value)
            host=parsed.hostname
            if not host or not (address(host) or domain(host)) or parsed.port is not None and not 0<=parsed.port<=65535: continue
        except ValueError: continue
        yield match.start(),match.start()+len(value),value,'url'


def unique(values, insensitive=False):
    seen=set();result=[]
    for value in values:
        key=value.casefold() if insensitive else value
        if key not in seen: seen.add(key);result.append(value)
    return '\n'.join(result)


def globally_reachable(ip):
    if ip.is_multicast: return False
    for network,globally in NETWORKS:
        if ip.version==network.version and ip in network: return globally
    return ip.version==4 or ip in ipaddress.ip_network('2000::/3')


def xml_format(text):
    # Reject all DTD/entity declarations before parsing; no resolver or expansion.
    if re.search(r'<!\s*(?:DOCTYPE|ENTITY)\b',text,re.I): raise ValueError('XML DTDs and entity declarations are not supported.')
    try: doc=minidom.parseString(text)
    except Exception: raise ValueError('Invalid XML.') from None
    def render(node,depth=0,preserve=False):
        if depth>150: raise ValueError('XML nesting exceeds 150 levels.')
        if node.nodeType!=Node.ELEMENT_NODE: return node.toxml()
        preserve=preserve or node.getAttribute('xml:space')=='preserve'
        mixed=any(child.nodeType in (Node.TEXT_NODE,Node.CDATA_SECTION_NODE) and child.data.strip() for child in node.childNodes)
        if preserve or mixed or not node.childNodes: return node.toxml()
        # Preserve existing whitespace-only content too; indent only element-only trees.
        if any(child.nodeType==Node.TEXT_NODE for child in node.childNodes): return node.toxml()
        opening=node.cloneNode(False).toxml()
        if opening.endswith('/>'): opening=opening[:-2]+'>'
        return opening+'\n'+'\n'.join('    '*(depth+1)+render(child,depth+1,preserve) for child in node.childNodes)+'\n'+'    '*depth+f'</{node.tagName}>'
    declaration=re.match(r'\s*(<\?xml[^?]*\?>)',text)
    return ((declaration.group(1)+'\n') if declaration else '')+'\n'.join(render(child) for child in doc.childNodes if child.nodeType!=Node.TEXT_NODE)


def process(operation,text):
    warning=''
    ips=list(ip_spans(text))
    if operation in ('ipv4','ipv6','all-ips','ips-domains'):
        if operation=='ipv4': rows=[r for r in ips if address(r[2]).version==4]
        elif operation=='ipv6': rows=[r for r in ips if address(r[2]).version==6]
        elif operation=='all-ips': rows=sorted(ips,key=lambda r:address(r[2]).version)
        else: rows=sorted(ips+list(domain_spans(text)),key=lambda r:r[0])
        output=unique(r[2] for r in rows)
    elif operation=='cidrs':
        values=[]
        for match in re.finditer(r'(?<![\w.:/])(?:\d+\.){3}\d+/\d+(?![\w./])',text):
            try:
                network=ipaddress.IPv4Network(match.group(),strict=False);values.append(str(network))
            except ValueError: pass
        output=unique(values)
    elif operation=='domains': output=unique(r[2] for r in domain_spans(text))
    elif operation=='urls': output=unique(r[2] for r in url_spans(text))
    elif operation=='emails': output=unique((r[2] for r in email_spans(text)),True)
    elif operation=='non-routable':
        output='\n'.join(line for line in re.split(r'\r\n|\r|\n',text) if not (address(line.strip()) and not globally_reachable(address(line.strip()))))
    elif operation=='ip-sort':
        good=[];bad=[]
        for line in re.split(r'\r\n|\r|\n',text):
            ip=address(line.strip())
            if ip: good.append((ip.version,int(ip),line))
            else: bad.append(line)
        output='\n'.join([r[2] for r in sorted(good,key=lambda r:r[:2])]+bad)
        if bad: warning=f'{len(bad)} invalid IP lines retained at the bottom.'
    elif operation in ('defang','refang'):
        if operation=='refang':
            # Recover original offsets by scanning defanged tokens and validating their refanged forms.
            def restore_token(match):
                token=match.group();plain=token.replace('[.]','.').replace('[:]',':')
                plain=re.sub(r'^hxxp', 'http',plain,flags=re.I)
                return plain if address(plain.strip('[]')) or domain(plain) or list(url_spans(plain)) else token
            output=re.sub(r'(?i)(?:hxxps?|https?|ftp)://[^\s<>"\']+|[\w.\[\]:%-]+',restore_token,text)
        else:
            spans=list(url_spans(text))+ips+list(domain_spans(text));spans.sort(key=lambda r:(r[0],-(r[1]-r[0])))
            result=[];cursor=0
            for start,end,value,kind in spans:
                if start<cursor: continue
                raw=text[start:end]
                if kind=='url':
                    parsed=urlsplit(raw);authority=raw.split('://',1)[1].split('/',1)[0].split('?',1)[0].split('#',1)[0]
                    host=parsed.hostname
                    host_start=authority.rfind('@')+1+authority[authority.rfind('@')+1:].lower().find(host.lower())
                    safe_host=authority[host_start:host_start+len(host)].replace('.','[.]').replace(':','[:]')
                    safe_authority=authority[:host_start]+safe_host+authority[host_start+len(host):]
                    raw=raw[:raw.index('://')+3]+safe_authority+raw[raw.index('://')+3+len(authority):]
                    raw=re.sub(r'^http',lambda m:'hxxp' if m.group().islower() else 'HXXP',raw,flags=re.I)
                else: raw=raw.replace('.','[.]').replace(':','[:]')
                result.append(text[cursor:start]+raw);cursor=end
            output=''.join(result)+text[cursor:]
    elif operation=='json':
        def encode(value,depth=0):
            if depth>150: raise ValueError('JSON nesting exceeds 150 levels.')
            if isinstance(value,(dict,list)):
                items=[json.dumps(k,ensure_ascii=False)+': '+encode(v,depth+1) for k,v in value.items()] if isinstance(value,dict) else [encode(v,depth+1) for v in value]
                left,right=('{','}') if isinstance(value,dict) else ('[',']')
                return left+('\n'+'    '*(depth+1)+(',\n'+'    '*(depth+1)).join(items)+'\n'+'    '*depth if items else '')+right
            if isinstance(value,Decimal): return str(value)
            return json.dumps(value,ensure_ascii=False,allow_nan=False)
        def object_pairs(pairs):
            result={}
            for key,value in pairs:
                if key in result: raise ValueError('Duplicate JSON object key.')
                result[key]=value
            return result
        try: output=encode(json.loads(text,object_pairs_hook=object_pairs,parse_float=Decimal,parse_constant=lambda value: (_ for _ in ()).throw(ValueError('Invalid JSON constant.'))))
        except (ValueError,TypeError): raise ValueError('Invalid JSON.') from None
    elif operation=='xml': output=xml_format(text)
    elif operation=='python':
        import black
        try: output=black.format_file_contents(text,fast=False,mode=black.Mode())
        except black.NothingChanged: output=text
        except (black.InvalidInput,AssertionError): raise ValueError('Invalid or unsupported Python source.') from None
    else: raise ValueError('Unknown text operation.')
    return {'text':output,'warning':warning or ('No matching indicators found.' if not output and operation in ('ipv4','ipv6','all-ips','cidrs','domains','ips-domains','urls','emails') else '')}


def register_text_tool(app,db,require_tool):
    from flask import request,render_template,make_response
    @app.get('/tools/text-manipulation/app/')
    def tools_text_manipulation():
        require_tool(app,db,'text-manipulation')
        response=make_response(render_template('text_manipulation.html'))
        response.headers['Cache-Control']='no-store'
        response.headers['Content-Security-Policy']="default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; connect-src 'self'; worker-src 'self'; object-src 'none'; frame-ancestors 'self'; base-uri 'none'"
        return response
    @app.post('/tools/text-manipulation/process')
    def tools_text_process():
        require_tool(app,db,'text-manipulation')
        if request.content_length and request.content_length>LIMIT+4096:return {'error':'Text exceeds the 2 MiB limit.'},413
        data=dict(request.form)
        if not isinstance(data,dict) or not isinstance(data.get('text'),str) or not isinstance(data.get('operation'),str):return {'error':'Invalid text request.'},400
        if len(data['text'].encode('utf-8'))>LIMIT:return {'error':'Text exceeds the 2 MiB limit.'},413
        try:result=process(data['operation'],data['text'])
        except ValueError as exc:return {'error':str(exc)},400
        except RecursionError:return {'error':'Input nesting exceeds formatter limits.'},400
        response=make_response(result);response.headers['Cache-Control']='no-store';return response
