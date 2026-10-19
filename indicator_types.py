"""Supported scalar indicator ↔ STIX 2.1 mappings (no fuzzy inference)."""
import json
from pathlib import Path
import ipaddress
import re
from urllib.parse import urlsplit,urlunsplit
from reporting import refang, defang
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
LEGACY_DETECTION_TYPES={item['name'] for item in CATALOG}
entry('software','Software name','Software',['software:name'],['application','software-name'])
entry('mobile-application-id','Mobile application identifier','Software',['software:name'],['Android','package','package-name','application-id','bundle identifier','android-app','android-package','Android application/package identifier'])
# Additional official native hash mappings; source values remain unchanged.
EXTRA_HASHES={'sha224':('SHA-224',56),'sha384':('SHA-384',96),
              'sha512/224':('SHA-512/224',56),'sha512/256':('SHA-512/256',64),
              'sha3-224':('SHA3-224',56),'sha3-256':('SHA3-256',64),
              'sha3-384':('SHA3-384',96),'sha3-512':('SHA3-512',128)}
for name,(algorithm,length) in EXTRA_HASHES.items():
    entry(name,algorithm,'Files',[f"file:hashes.'{algorithm}'"])
    entry('filename|'+name,'Filename + '+algorithm,'Files',['file:name',f"file:hashes.'{algorithm}'"])
entry('x509-fingerprint-md5','Certificate MD5','Certificates',["x509-certificate:hashes.'MD5'"])
BINARY_TYPES=frozenset(('attachment','malware-sample'))
# Complete official storage catalog; native pattern support is a separate capability.
MISP_SOURCE=json.loads((Path(__file__).parent/'vendor/misp/describeTypes.json').read_text())['result']
PATTERN_TYPES={item['name'] for item in CATALOG}
CONVERSION_PROFILE=json.loads((Path(__file__).parent/'vendor/misp/stix21-capabilities.json').read_text())
OFFICIAL_NATIVE=CONVERSION_PROFILE['native_detection_patterns']
NATIVE_SDO=CONVERSION_PROFILE['native_descriptive_objects']
CONTEXT_TYPES=frozenset(set(MISP_SOURCE['types'])-PATTERN_TYPES-set(OFFICIAL_NATIVE)-set(NATIVE_SDO)-BINARY_TYPES|{'mobile-application-id'})
for name in MISP_SOURCE['types']:
    if name not in PATTERN_TYPES:
        entry(name,name,'Context' if name in CONTEXT_TYPES else MISP_SOURCE['sane_defaults'][name]['default_category'],[],
              {'text':['free text'], 'other':['miscellaneous','catch all']}.get(name,[]))
for item in CATALOG:
    name=item['name']
    item['search_aliases']=['unknown'] if name=='text' else []
    mode='unsupported' if name in BINARY_TYPES else 'contextual' if name in CONTEXT_TYPES else 'native'
    item['import_paths']=OFFICIAL_NATIVE.get(name,item['paths'])
    item['native_sdo']=NATIVE_SDO.get(name)
    item['export']=mode
    item['default_to_ids']=name in LEGACY_DETECTION_TYPES or name=='software'
    item['help']=('MISP-compatible representation — official converter contextual attribute; no fabricated detection pattern.' if mode=='contextual' else
                  'Native STIX mapping when detection-enabled; MISP-compatible representation for non-detection content.' if mode=='native' else
                  'Requires correction/additional data.')
    if name in NATIVE_SDO:item['help']='MISP-compatible representation by default to preserve non-detection intent. Native STIX mapping is available with explicit detection intent; the pinned importer marks native descriptive objects detection-enabled.'
    if name in ('attachment','malware-sample'):
        item['help']=('Requires correction/additional data: STIX export requires attachment bytes; the three-column editor stores only text. Supply the evidence separately or explicitly use text/other for a contextual filename.' if name=='attachment' else 'Requires correction/additional data: STIX export requires sample/archive bytes and associated sample metadata; a filename/hash string is insufficient. Supply the evidence separately or explicitly use text/other for context.')
# Exact canonical official names take precedence over compatibility aliases (e.g. uri).
BY_NAME={item['name']:item for item in CATALOG}
ALIASES={alias.casefold():item['name'] for item in CATALOG for alias in [item['name'],item['label'],*item['aliases']]}
ALIASES.update({name.casefold():name for name in MISP_SOURCE['types']})
HASH_LENGTH={'md5':32,'sha1':40,'sha256':64,'sha512':128,**{name:info[1] for name,info in EXTRA_HASHES.items()}}
NETWORK_TYPES=frozenset(('domain','hostname','url','ip-src','ip-dst','email-src','email-dst'))


def canonical_type(value):
    return ALIASES.get(value.strip().casefold())


def literal(value):
    return "'"+value.replace('\\','\\\\').replace("'","\\'")+"'"


def network_value(value):
    # Decode colon brackets before recognizing the defanged scheme. Applying the
    # established refanger twice also supports its existing combined forms.
    value=refang(refang(value)).strip()
    return re.sub(r'(?i)^hxxps?://',lambda match:'https://' if match.group().lower().startswith('hxxps') else 'http://',value)


def components(kind,value):
    if kind in NETWORK_TYPES:value=network_value(value)
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
        try:address=ipaddress.ip_network(value,strict=False) if '/' in value else ipaddress.ip_address(value)
        except ValueError:raise ValueError('Enter one valid IPv4/IPv6 address or CIDR network, without a port or arbitrary range.')
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
            try:
                address=ipaddress.ip_address(hostname)
                host='['+str(address)+']' if address.version==6 else str(address)
            except ValueError:host=components('hostname',hostname)[0]
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


def analyze(row, *, to_ids=None):
    if not any(cell.strip() for cell in row):return {'blank':True,'row':row}
    kind=canonical_type(row[0])
    if not kind:
        reason='Direction is ambiguous; choose ip-src or ip-dst.' if row[0].strip().casefold() in ('ip','ipv4','ipv6','ipv4-addr','ipv6-addr') else 'Unknown type; choose a supported canonical type.'
        return {'row':row,'error':reason}
    canonical=[kind,row[1],row[2]]
    if kind=='software' and to_ids is False:return {'row':canonical,'error':'The MARE software-name extension has no verified non-detection MISP attribute representation. Use an appropriate MISP type such as text or mobile-application-id.'}
    capability=BY_NAME[kind]['export']
    if capability!='native' or not BY_NAME[kind]['paths']:
        if capability=='unsupported':return {'row':canonical,'storage_valid':True,'error':BY_NAME[kind]['help'],'normalized':row[0]!=kind}
        # Arbitrary analyst content remains byte-for-byte literal, including whitespace.
        if row[1]=='':return {'row':canonical,'error':'Enter a value (whitespace and line breaks are preserved).'}
        try:
            value=machine_value(kind,row[1])
            if kind not in ('text','comment','other'):
                from pymisp.tools.attributevalidationtool import AttributeValidationTool
                valid=AttributeValidationTool.validate(kind,AttributeValidationTool.modifyBeforeValidation(kind,value))
                if valid is not True and kind not in ('edge-extension-id','filename|impfuzzy','mac-eui-64'):raise ValueError(str(valid))
        except ValueError as error:return {'row':canonical,'error':str(error)}
        result={'row':canonical,'key':[kind,[value]],'export':'native' if capability=='native' and to_ids else 'contextual','to_ids':bool(to_ids),'normalized':row[0]!=kind}
        if result['export']=='native' and kind not in NATIVE_SDO:
            values=['github',value] if kind=='github-username' else value.split('|') if '|' in kind else [value]
            paths=BY_NAME[kind]['import_paths']
            if len(paths)!=len(values):return {'row':canonical,'error':'Native pattern components require review; no row was omitted.'}
            result['components']=values
        return result
    try:
        values=components(kind,row[1])
        pattern='['+' AND '.join(path+' = '+literal(value) for path,value in zip(BY_NAME[kind]['paths'],values))+']'
        Pattern(pattern)
        return {'row':canonical,'pattern':pattern,'key':[kind,values],'normalized':row[0]!=kind,'to_ids':BY_NAME[kind]['default_to_ids'] if to_ids is None else to_ids,'export':'native' if (BY_NAME[kind]['default_to_ids'] if to_ids is None else to_ids) else 'contextual'}
    except Exception as error:
        return {'row':row,'error':str(error)}


def duplicate_key(row, *, result=None):
    """Same canonical type/value identity for import checks and saved feedback."""
    result = analyze(row) if result is None else result
    return json.dumps(result['key']) if result.get('key') else None


def inspect_sections(sections):
    issues=[];notices=[];duplicates=[];normalized=0;count=0
    for section in sections:
        groups={}
        for index,row in enumerate(section['rows']):
            metadata=section.get('row_meta',[])
            result=analyze(row,to_ids=(metadata[index] or {}).get('to_ids') if index<len(metadata) else None)
            if result.get('blank'):continue
            count+=1;normalized+=bool(result.get('normalized'))
            key=duplicate_key(row, result=result)
            if key is not None:groups.setdefault(key,[]).append(index+1)
            if not result.get('error') and result.get('export')=='contextual':
                message='MISP-compatible representation'
                if row[1]!=row[1].strip():message+=' — MISP import trims boundary whitespace; STIX retains it.'
                elif result['row'][0]=='datetime':message+=' — MISP may normalize the timezone spelling.'
                notices.append({'section_id':section['id'],'row':index+1,'message':message,'to_ids':result.get('to_ids',False)})
            if result.get('error'):issues.append({'section_id':section['id'],'section':section['title'],'row':index+1,'reason':result['error'],'storage_valid':result.get('storage_valid',False)})
        for rows in groups.values():
            if len(rows)>1:duplicates.extend({'section_id':section['id'],'row':row} for row in rows)
    return {'available':not issues,'issues':issues,'normalized':normalized,'count':count,'notices':notices,'duplicates':duplicates}


# CSV-only component mappings do not imply verified STIX export support.
CSV_NETWORK_ALIASES={
    'uri':'url','link':'url','onion-address':'hostname',
    'email':'email-src','email-reply-to':'email-src','target-email':'email-src',
    'whois-registrant-email':'email-src','dns-soa-email':'email-src',
}
CSV_NETWORK_COMPOSITES={
    'domain|ip':('domain','ip-src'),
    'ip-src|port':('ip-src',None),'ip-dst|port':('ip-dst',None),'hostname|port':('hostname',None),
}


def csv_row(row):
    """Defang only recognized network components; never mutate stored cells."""
    result=list(row)
    kind=canonical_type(row[0])
    def network(kind,value):
        try:return defang(components(kind,value)[-1])
        except ValueError:return defang(value)  # keep known network drafts safe for delivery
    if kind in CSV_NETWORK_COMPOSITES and row[1].count('|')==1:
        result[1]='|'.join(network(component,value) if component else value
                           for component,value in zip(CSV_NETWORK_COMPOSITES[kind],row[1].split('|')))
    else:
        network_kind=CSV_NETWORK_ALIASES.get(kind,kind)
        if network_kind in NETWORK_TYPES:result[1]=network(network_kind,row[1])
        elif row[0].strip().casefold() in ('ip','ipv4','ipv6','ipv4-addr','ipv6-addr','email-addr'):
            result[1]=network('email-src' if row[0].strip().casefold().startswith('email') else 'ip-src',row[1])
    return result


def machine_value(kind,value):
    """Validate known typed values; refang only explicit network components."""
    if kind in ('text','comment','other','mobile-application-id','chrome-extension-id','edge-extension-id'):return value
    from pymisp.tools.attributevalidationtool import HASH_HEX_LENGTH
    if kind in HASH_HEX_LENGTH:return value.strip().lower()
    if kind.startswith('filename|') and kind[9:] in HASH_HEX_LENGTH and value.count('|')==1:
        name,checksum=value.split('|');return name+'|'+checksum.strip().lower()
    if kind=='mac-eui-64' and not re.fullmatch(r'(?:[0-9a-fA-F]{2}:){7}[0-9a-fA-F]{2}',value):raise ValueError('MAC EUI-64 requires eight colon-separated hexadecimal octets.')
    if kind=='filename|impfuzzy':
        if value.count('|')!=1:raise ValueError('filename|impfuzzy requires one filename|hash separator.')
        from pymisp.tools.attributevalidationtool import AttributeValidationTool
        filename,fuzzy=value.split('|')
        if not filename.strip() or any(ord(char)<32 for char in filename):raise ValueError('filename|impfuzzy requires a nonblank filename without control characters.')
        checked=AttributeValidationTool.validate('impfuzzy',fuzzy)
        if checked is not True:raise ValueError(str(checked))
    if kind in ('port','counter','size-in-bytes','integer'):
        if not re.fullmatch(r'[+-]?[0-9]+',value.strip()):raise ValueError(f'{kind} requires an integer value.')
        number=int(value)
        if kind=='port' and not 0<=number<=65535:raise ValueError('Port must be between 0 and 65535.')
        if kind in ('counter','size-in-bytes') and number<0:raise ValueError(f'{kind} cannot be negative.')
    if kind=='float':
        import math
        try:number=float(value)
        except ValueError:raise ValueError('float requires a finite numeric value.')
        if not math.isfinite(number):raise ValueError('float requires a finite numeric value.')
    if kind=='boolean' and value.strip().lower() not in ('true','false','0','1'):raise ValueError('boolean requires true, false, 0 or 1.')
    if kind=='uuid':
        import uuid
        try:uuid.UUID(value)
        except ValueError:raise ValueError('uuid requires a valid UUID.')
    if kind in CSV_NETWORK_COMPOSITES:
        if value.count('|')!=1:raise ValueError('Network composites require exactly one | separator.')
        left,right=value.split('|');first,second=CSV_NETWORK_COMPOSITES[kind]
        left=components(first,left)[-1]
        if second:right=components(second,right)[-1]
        else:machine_value('port',right)
        return left+'|'+right
    network_kind=CSV_NETWORK_ALIASES.get(kind,kind)
    if network_kind in NETWORK_TYPES:return components(network_kind,value)[-1]
    return value
