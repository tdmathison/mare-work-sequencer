"""Explicit MISP attribute ↔ STIX 2.1 pattern catalog (no fuzzy inference)."""
import ipaddress
import re
from urllib.parse import urlsplit,urlunsplit
from reporting import refang
from stix2patterns.v21.pattern import Pattern

CATALOG = []

def entry(name, label, category, paths, aliases=()):
    CATALOG.append(dict(name=name, label=label, category=category, paths=paths, aliases=list(aliases)))

entry('domain','Domain','Network',['domain-name:value'],['domain-name','dns'])
entry('hostname','Hostname','Network',['domain-name:value'],['host'])
entry('url','URL','Network',['url:value'],['uri'])
for direction in ('src','dst'):
    entry('ip-'+direction,'IP '+('source' if direction=='src' else 'destination'),'Network',[f'network-traffic:{direction}_ref.type',f'network-traffic:{direction}_ref.value'])
entry('mac-address','MAC address','Network',['mac-addr:value'],['mac','mac-addr'])
entry('filename','Filename','Files',['file:name'],['file-name'])
for algo,stix in [('md5','MD5'),('sha1','SHA-1'),('sha256','SHA-256'),('sha512','SHA-512')]:
    entry(algo,stix,'Files',[f"file:hashes.'{stix}'"],[stix])
    if algo!='sha512':entry('filename|'+algo,'Filename + '+stix,'Files',['file:name',f"file:hashes.'{stix}'"])
for direction in ('src','dst'):
    entry('email-'+direction,'Email '+('sender' if direction=='src' else 'recipient'),'Email',['email-message:'+('from_ref.value' if direction=='src' else 'to_refs[*].value')])
entry('email-subject','Email subject','Email',['email-message:subject'])
entry('email-attachment','Email attachment filename','Email',['email-message:body_multipart[*].body_raw_ref.name'])
entry('mutex','Mutex','Host artifacts',['mutex:name'])
entry('regkey','Registry key','Host artifacts',['windows-registry-key:key'],['registry-key'])
entry('regkey|value','Registry key + data','Host artifacts',['windows-registry-key:key','windows-registry-key:values[*].data'])
for algo,stix in [('sha1','SHA-1'),('sha256','SHA-256')]:
    entry('x509-fingerprint-'+algo,'Certificate '+stix,'Certificates',[f"x509-certificate:hashes.'{stix}'"])
BY_NAME={item['name']:item for item in CATALOG}
ALIASES={alias.casefold():item['name'] for item in CATALOG for alias in [item['name'],item['label'],*item['aliases']]}
HASH_LENGTH={'md5':32,'sha1':40,'sha256':64,'sha512':128}


def canonical_type(value):
    return ALIASES.get(value.strip().casefold())


def literal(value):
    return "'"+value.replace('\\','\\\\').replace("'","\\'")+"'"


def components(kind,value):
    if kind in ('domain','hostname','url','ip-src','ip-dst','email-src','email-dst'):value=refang(value).strip()
    elif kind in HASH_LENGTH or kind.startswith('x509-fingerprint-') or kind=='mac-address':value=value.strip()
    if not value.strip() or any(ord(char)<32 for char in value):raise ValueError('Enter a nonblank value without control characters.')
    if '|' in kind:
        if value.count('|')!=1:raise ValueError('Composite values require exactly one unambiguous | separator.')
        left,right=value.split('|')
        first,second=kind.split('|')
        return [components(first,left)[0],components(second,right)[0] if first=='filename' else components('mutex',right)[0]]
    algo=kind.removeprefix('x509-fingerprint-')
    if algo in HASH_LENGTH:
        if not re.fullmatch('[0-9a-fA-F]{'+str(HASH_LENGTH[algo])+'}',value):raise ValueError(f'{kind} requires {HASH_LENGTH[algo]} hexadecimal characters.')
        return [value.lower()]
    if kind.startswith('ip-'):
        try:address=ipaddress.ip_address(value)
        except ValueError:raise ValueError('Enter one IPv4 or IPv6 address, without a port or range.')
        return ['ipv4-addr' if address.version==4 else 'ipv6-addr',str(address)]
    if kind in ('domain','hostname'):
        try:ipaddress.ip_address(value)
        except ValueError:pass
        else:raise ValueError('Use an explicit ip-src or ip-dst type for an IP address.')
        try:encoded=value.rstrip('.').encode('idna').decode('ascii')
        except UnicodeError:raise ValueError('Invalid DNS name.')
        if len(encoded)>253 or any(not re.fullmatch(r'[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?',label) for label in encoded.split('.')):raise ValueError('Invalid DNS name.')
        return [encoded.lower()]
    if kind=='url':
        try:parsed=urlsplit(value);hostname=parsed.hostname;parsed.port
        except ValueError:raise ValueError('Invalid URL.')
        if parsed.scheme.lower() not in ('http','https','ftp') or not hostname or any(c.isspace() for c in value):raise ValueError('Enter an absolute HTTP, HTTPS, or FTP URL.')
        if '\\' in value:raise ValueError('URL backslashes must be percent-encoded.')
        try:
            host='['+str(ipaddress.IPv6Address(hostname))+']' if ':' in hostname else components('hostname',hostname)[0]
        except ValueError:raise ValueError('Invalid URL hostname.')
        userinfo=parsed.netloc[:parsed.netloc.rfind('@')+1] if '@' in parsed.netloc else ''
        port=':'+str(parsed.port) if parsed.port is not None else ''
        value=urlunsplit((parsed.scheme.lower(),userinfo+host+port,parsed.path,parsed.query,parsed.fragment))
    if kind=='mac-address':
        if not re.fullmatch(r'(?:[0-9a-fA-F]{2}:){5}[0-9a-fA-F]{2}',value):raise ValueError('Use six colon-separated hexadecimal MAC octets.')
        value=value.lower()
    if kind in ('email-src','email-dst') and not re.fullmatch(r'[^\s@<>]+@[^\s@<>]+\.[^\s@<>]+',value):raise ValueError('Enter a single email address.')
    if kind in ('regkey','regkey|value') and not re.match(r'^(?:HKLM|HKCU|HKCR|HKU|HKCC|HKEY_LOCAL_MACHINE|HKEY_CURRENT_USER|HKEY_CLASSES_ROOT|HKEY_USERS|HKEY_CURRENT_CONFIG)\\.+',value,re.I):raise ValueError('Enter an explicit Windows registry hive and key path.')
    return [value]


def analyze(row):
    if not any(cell.strip() for cell in row):return {'blank':True,'row':row}
    kind=canonical_type(row[0])
    if not kind:
        reason='Direction is ambiguous; choose ip-src or ip-dst.' if row[0].strip().casefold() in ('ip','ipv4','ipv6','ipv4-addr','ipv6-addr') else 'Unknown type; choose a supported canonical type.'
        return {'row':row,'error':reason}
    canonical=[kind,row[1],row[2]]
    try:
        values=components(kind,row[1])
        pattern='['+' AND '.join(path+' = '+literal(value) for path,value in zip(BY_NAME[kind]['paths'],values))+']'
        Pattern(pattern)
        return {'row':canonical,'pattern':pattern,'key':[kind,values],'normalized':row[0]!=kind}
    except Exception as error:
        return {'row':row,'error':str(error)}


def inspect_sections(sections):
    issues=[];normalized=0;count=0
    for section in sections:
        for index,row in enumerate(section['rows']):
            result=analyze(row)
            if result.get('blank'):continue
            count+=1;normalized+=bool(result.get('normalized'))
            if result.get('error'):issues.append({'section_id':section['id'],'section':section['title'],'row':index+1,'reason':result['error']})
    return {'available':not issues,'issues':issues,'normalized':normalized,'count':count}
