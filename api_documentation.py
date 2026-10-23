"""OpenAPI contracts for public API handlers; routes/permissions come from Flask.

Keep CONTRACTS explicit: internal JSON UI routes are deliberately not APIs.
Tests compare the documented operations with every registered /api/v1 route.
"""
import copy
import re

from mip import CATEGORIES
from reporting import SECTIONS, TOKENS


def obj(properties=None, required=(), **kwargs):
    result = {'type': 'object', 'properties': properties or {}, **kwargs}
    if required:
        result['required'] = list(required)
    return result


def array(items, **kwargs):
    return {'type': 'array', 'items': items, **kwargs}


def ref(name):
    return {'$ref': '#/components/schemas/' + name}


TEXT = {'type': 'string'}
INT = {'type': 'integer'}
BOOL = {'type': 'boolean'}
BINARY = {'type': 'string', 'format': 'binary'}
NULL_TEXT = {**TEXT, 'nullable': True}
NULL_INT = {**INT, 'nullable': True}
DOCX = 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
CATEGORY = {**TEXT, 'enum': list(CATEGORIES)}
TITLE = {**TEXT, 'maxLength': 200}
MARKDOWN = {**TEXT, 'maxLength': 100000}
CELL = {**TEXT, 'maxLength': 4000}
SECTIONS_SCHEMA = obj({key: MARKDOWN for key in TOKENS}, additionalProperties=False)
MAPPINGS = obj({'attack': MARKDOWN, 'mbc': MARKDOWN}, additionalProperties=False)
ROWS = array(array(CELL), maxItems=10000)
CASE_FIELDS = {'name': {**TITLE, 'minLength': 1}, 'description': {**TEXT, 'maxLength': 20000},
               'owner_id': {**NULL_INT, 'description': 'Active user ID, or null to leave unassigned.'},
               'external_system': {**TEXT, 'enum': ['', 'Vortex', 'XSIAM', 'JIRA']}, 'external_number': {**TEXT, 'maxLength': 200}}
TASK_FIELDS = {'title': {**TITLE, 'minLength': 1}, 'body': {**TEXT, 'maxLength': 20000},
               'description': {**TEXT, 'description': 'Alias for body; body takes precedence.', 'maxLength': 20000},
               'priority': {**TEXT, 'enum': ['Low', 'Normal', 'High', 'Critical'], 'default': 'Normal'}}
NOTE_FIELDS = {'title': TITLE, 'body': MARKDOWN, 'include_export': BOOL}

SCHEMAS = {
    'Error': obj({'error': TEXT, 'required_permission': TEXT, 'blockers': array(TEXT), 'needs_choice': BOOL}, ('error',)),
    'User': obj({'id': INT, 'uuid': NULL_TEXT, 'username': TEXT, 'role': TEXT, 'active': BOOL, 'forced_password_change': BOOL}),
    'Token': obj({**dict.fromkeys(('name', 'token_prefix', 'created'), TEXT), 'id': INT,
                  **dict.fromkeys(('last_used', 'revoked', 'expires'), NULL_TEXT)}),
    'Role': obj({'name': TEXT, 'description': TEXT, 'builtin': BOOL, 'permissions': array(TEXT)}),
    'Case': obj({**CASE_FIELDS, 'id': INT, 'number': TEXT, 'stage': {**INT, 'minimum': 0, 'maximum': 3},
                 **dict.fromkeys(('stage_name', 'created', 'report_path'), TEXT),
                 **dict.fromkeys(('owner_name', 'creator_name'), NULL_TEXT), 'creator_id': NULL_INT, 'owner_active': BOOL}),
    'Task': obj({**{key: value for key, value in TASK_FIELDS.items() if key != 'description'}, 'id': INT,
                 'state': {**TEXT, 'enum': ['Not Started', 'In Progress', 'Completed']}, 'done': INT, 'created': TEXT}),
    'Note': obj({**NOTE_FIELDS, 'include_export': INT, 'id': INT, 'author': TEXT, 'created': TEXT}),
    'Draft': obj({'title': TITLE, 'body': MARKDOWN, 'updated': TEXT}, nullable=True),
    'Readiness': array(obj({'category': CATEGORY, 'label': TEXT, 'status': TEXT, 'reason': TEXT, 'count': INT})),
    'File': obj({'path': TEXT, 'size': INT, 'description': TEXT}),
    'IndicatorRowIdentity': obj({'id':TEXT,'created':TEXT,'modified':TEXT,'digest':TEXT,'original_type':{**TEXT,'maxLength':4000},'to_ids':{'type':'boolean','description':'Optional explicit detection intent; preserve when provided by import or API.'}}),
    'IndicatorSection': obj({'id': {**TEXT, 'pattern': '^[A-Za-z0-9_-]{1,64}$'}, 'title': {**TITLE, 'minLength': 1}, 'description': {**TEXT, 'maxLength': 4000}, 'rows': array(array(CELL, minItems=3, maxItems=3), maxItems=10000), 'row_meta':array({'allOf':[ref('IndicatorRowIdentity')], 'nullable':True}), 'stix_meta':ref('IndicatorRowIdentity')}, ('id', 'title', 'description', 'rows')),
    'Indicators': obj({'columns': array(TEXT), 'rows': ROWS, 'sections': array(ref('IndicatorSection')), 'revision': INT, 'stix':obj({'available':BOOL,'issues':array(obj({'section_id':TEXT,'section':TEXT,'row':INT,'reason':TEXT})),'notices':array(obj({'section_id':TEXT,'row':INT,'message':TEXT,'to_ids':BOOL}))}), 'types':array(obj())}),
    'References': obj({'columns': array(TEXT), 'rows': ROWS, 'revision': INT}),
    'Template': obj({'id': TEXT, 'name': TEXT, 'created': TEXT, 'selected': BOOL}),
    'Image': obj({'name': TEXT, 'section': TEXT, 'figure': INT, 'url': TEXT, 'markdown_url': TEXT}),
    'Job': obj({'id': TEXT, 'status': {**TEXT, 'enum': ['queued', 'running', 'completed', 'failed']},
                'messages': array(TEXT), 'updated': TEXT}, nullable=True),
    'SyncCase': obj({'title': TEXT, 'owner_warning': TEXT, 'summary': {'nullable': True}, 'suggestions': array(obj()), **dict.fromkeys(('classification', 'reason', 'case_uuid', 'incoming_number', 'destination_number',
                                     'incoming_revision', 'local_revision', 'fingerprint'), NULL_TEXT),
                     'destination_id': NULL_INT}, additionalProperties=True),
    'SyncOutcome': obj({'index': INT, 'case_uuid': NULL_TEXT, 'classification': TEXT, 'action': TEXT, 'reason': TEXT,
                        'decision': TEXT, 'ownership_decision': TEXT, 'recovery': NULL_TEXT,
                        'incoming_number': NULL_TEXT, 'destination_number': NULL_TEXT,
                        'previous_revision': NULL_TEXT, 'incoming_revision': NULL_TEXT}, additionalProperties=True),
    'SyncResult': obj({'operation': TEXT, 'status': {**TEXT, 'enum': ['preview', 'complete']},
                       'cases': array(ref('SyncCase')), 'outcomes': array(ref('SyncOutcome'))}),
}


def json_response(schema, description='Successful response.', example=None):
    content = {'schema': schema}
    if example is not None:
        content['example'] = example
    return {'description': description, 'content': {'application/json': content}}


def download(*types, inline=False):
    return {'description': ('Inline image response.' if inline else 'File attachment. The filename is supplied in Content-Disposition.'),
            'headers': {'Content-Disposition': {'schema': TEXT, 'description': 'Response filename/disposition.'}},
            'content': {kind: {'schema': BINARY} for kind in types}}


def field(name, schema, description='', **kwargs):
    return {'name': name, 'in': 'query', 'schema': schema, 'description': description, **kwargs}


PAGING = [field('limit', {**INT, 'minimum': 1, 'maximum': 500, 'default': 100}, 'Clamped to 1–500.'),
          field('offset', {**INT, 'minimum': 0, 'default': 0}, 'Negative offsets are clamped to zero.')]
CONTRACTS = {}


def contract(endpoint, method, summary, response=None, *, body=None, required=True, media='application/json',
             status=200, description='', parameters=(), example=None, errors=()):
    operation = {'summary': summary, 'description': description,
                 'responses': {str(status): response or {'description': 'Successful response; no body.'}},
                 'parameters': list(parameters), 'x-errors': errors}
    if body is not None:
        payload = {'schema': body}
        if example is not None:
            payload['example'] = example
        operation['requestBody'] = {'required': required, 'content': {media: payload}}
    CONTRACTS[(endpoint, method)] = operation


def result(**properties):
    return json_response(obj(properties))


def paged(name, schema):
    return result(**{name: array(schema), 'limit': INT, 'offset': INT, 'total': INT})


contract('me', 'GET', 'Inspect the authenticated account and permissions', result(user=ref('User'), permissions=array(TEXT)))
contract('tokens', 'GET', 'List your token metadata (no secrets)', result(tokens=array(ref('Token'))))
contract('tokens', 'POST', 'Create a bearer token', result(id=INT, name=TEXT, token={**TEXT, 'description': 'Secret returned once. Store securely; never log it.'}, expires=NULL_TEXT),
         body=obj({'name': {**TEXT, 'minLength': 1, 'maxLength': 80}, 'expires_in_days': {**INT, 'minimum': 1, 'maximum': 3650}}, ('name',)), status=201)
contract('revoke_token', 'DELETE', 'Revoke a token', status=204, description='Own tokens only, unless users:manage is also held. Repeated revocation returns 204.')
contract('permissions', 'GET', 'List known permission names', result(permissions=array(obj({'name': TEXT, 'description': TEXT}))))
ROLE_FIELDS = {'name': {**TEXT, 'pattern': '^[a-z][a-z0-9_-]{2,31}$'}, 'description': {**TEXT, 'maxLength': 300},
               'permissions': array(TEXT, uniqueItems=True)}
contract('roles', 'GET', 'List roles and permissions', result(roles=array(ref('Role'))))
contract('roles', 'POST', 'Create a custom role', json_response(ref('Role')), body=obj(ROLE_FIELDS, ('name',)), status=201,
         description='Only known, unique permissions already held by the caller may be granted.', errors=(409,))
contract('role_item', 'PATCH', 'Update a custom role', json_response(ref('Role')), body=obj({k: v for k, v in ROLE_FIELDS.items() if k != 'name'}),
         description='Built-in roles are immutable. Cannot grant permissions the caller does not hold.', errors=(409,))
contract('role_item', 'DELETE', 'Delete an unused custom role', status=204, description='Built-in roles and roles assigned to users cannot be deleted.', errors=(409,))
contract('users', 'GET', 'List accounts', paged('users', ref('User')), parameters=PAGING)
contract('users', 'POST', 'Create an account', result(user=ref('User')), body=obj({'username': {**TEXT, 'pattern': '^[A-Za-z0-9_.-]{3,64}$'},
         'password': {**TEXT, 'minLength': 12, 'format': 'password', 'writeOnly': True}, 'role': {**TEXT, 'default': 'User'}}, ('username', 'password')), status=201,
         description='The role must exist. Without roles:manage, only roles whose permissions are a subset of the caller’s role may be assigned.', errors=(409,))
contract('user_item', 'PATCH', 'Change account role or active status', result(user=ref('User')), body=obj({'role': TEXT, 'active': BOOL}),
         description='Cannot disable/demote the last active Administrator. Role assignment uses the same permission constraints as account creation. Changes invalidate existing web sessions.', errors=(409,))
contract('user_item', 'DELETE', 'Delete an account', status=204, description='Cannot delete yourself or the last active Administrator. Case ownership/creator references are cleared.', errors=(409,))
SETTINGS = obj({'settings': obj({'sample_archive_password': obj({'configured': BOOL})})})
contract('settings', 'GET', 'Inspect configured settings (no secrets)', json_response(SETTINGS))
contract('settings', 'PATCH', 'Set the sample archive password', json_response(SETTINGS), body=obj({'sample_archive_password': {**TEXT, 'minLength': 1, 'maxLength': 256, 'format': 'password', 'writeOnly': True}}, ('sample_archive_password',), additionalProperties=False), description='NUL characters are rejected. Changes affect future sample archives; the password is never returned.')
contract('case_collection', 'GET', 'List cases newest first', paged('cases', ref('Case')), parameters=PAGING)
contract('case_collection', 'POST', 'Create a case', result(case=ref('Case')), body=obj(CASE_FIELDS, ('name',)), status=201,
         description='A date prefix is added to the title if absent; the resulting name must remain ≤200 characters. External system and number must be supplied together. Owner must be active.', example={'name': 'Example investigation'})
contract('case_item', 'GET', 'Read case details and workflow history', result(case={'allOf': [ref('Case'), obj({'readiness': ref('Readiness'), 'history': array(obj({'stage': INT, 'author': TEXT, 'created': TEXT, 'outcome': TEXT, 'reason': TEXT})), 'deferred': array(obj({'stage': INT, 'reason': TEXT, 'resolved': INT}))})]}))
contract('case_item', 'PATCH', 'Update case metadata or ownership', result(case=ref('Case')), body=obj(CASE_FIELDS), description='External system/number must be paired. Stage changes use the dedicated workflow endpoint.')
contract('case_item', 'DELETE', 'Permanently delete a case and its files', status=204, description='Real destructive operation. Active report generation blocks deletion; there is no additional API confirmation field.', errors=(409,))
contract('advance_case', 'POST', 'Advance one workflow stage', result(case=ref('Case')), body=obj({'expected': {**INT, 'minimum': 0, 'maximum': 3}, 'outcome': {**TEXT, 'enum': ['Done', 'No applicable work', 'Deferred'], 'default': 'Done'}, 'reason': TEXT}, ('expected',)),
         description='expected must equal the current stage. Active owner required to start; skipped/deferred outcomes require a reason. Completion checks readiness and review blockers. Stage 0 always records Started.', errors=(409,))
contract('reopen_case', 'POST', 'Reopen a completed case for analysis', result(case=ref('Case')), description='Completed cases only; active owner required when ownership is mandatory.', errors=(409,))
contract('case_readiness', 'GET', 'Read package readiness', result(readiness=ref('Readiness')))
contract('case_readiness', 'PUT', 'Set one category readiness', result(readiness=ref('Readiness')), body=obj({'category': CATEGORY, 'status': {**TEXT, 'enum': ['Pending', 'Populated', 'Not applicable']}, 'reason': TEXT}, ('category', 'status')),
         description='Not applicable requires a reason and is forbidden for reports. Populated requires an existing file.', errors=(409,))
contract('case_tasks', 'GET', 'List case tasks', paged('tasks', ref('Task')), parameters=PAGING)
contract('case_tasks', 'POST', 'Create a task', result(task=ref('Task')), body=obj(TASK_FIELDS, ('title',)), status=201)
contract('case_task', 'PATCH', 'Update a task', result(task=ref('Task')), body=obj({**TASK_FIELDS, 'state': SCHEMAS['Task']['properties']['state']}))
contract('case_task', 'DELETE', 'Delete a task', status=204)
contract('case_notes', 'GET', 'List case notes', paged('notes', ref('Note')), parameters=PAGING)
contract('case_notes', 'POST', 'Create a note', result(note=ref('Note')), body=obj({**NOTE_FIELDS, 'body': {**MARKDOWN, 'minLength': 1}}, ('body',)), status=201)
contract('case_note', 'PATCH', 'Update a note', result(note=ref('Note')), body=obj(NOTE_FIELDS), description='The resulting body must contain non-whitespace text.')
contract('case_note', 'DELETE', 'Delete a note', status=204)
contract('case_draft', 'GET', 'Read your case note draft', result(draft=ref('Draft')))
contract('case_draft', 'PUT', 'Replace your case note draft', result(draft=ref('Draft')), body=obj({'title': TITLE, 'body': MARKDOWN}))
contract('case_draft', 'DELETE', 'Delete your case note draft', status=204)
contract('case_assets', 'GET', 'List package files', result(files=array(ref('File'))), parameters=[field('category', CATEGORY, 'Optional package category. Backup folders and symlinks are excluded.')])
contract('case_assets', 'POST', 'Upload a package artifact', result(file=ref('File')), body=obj({'category': CATEGORY, 'description': TEXT, 'file': BINARY}, ('category', 'file')), media='multipart/form-data', status=201,
         description='Maximum 100 MiB per file. Sanitized duplicate filenames are rejected. Samples are wrapped in password-protected AES ZIP files using the configured sample password.', errors=(409, 413))
contract('case_assets', 'DELETE', 'Delete a package artifact', status=204, body=obj({'path': TEXT}, ('path',)))
contract('download_case_asset', 'GET', 'Download a package artifact', download('application/octet-stream'), description='relative_path may include slashes, e.g. scripts/example.txt; it must remain within the case directory. Content-Type is inferred from the filename. Generated indicators.stix.json returns 409 if it does not match the current saved table.', errors=(409,))
for endpoint, name in [('case_indicators', 'Indicators'), ('case_references', 'References')]:
    contract(endpoint, 'GET', f'Read {name.lower()} and revision', json_response(ref(name)))
contract('case_indicators', 'PUT', 'Replace indicators with revision validation', json_response(ref('Indicators')), body=obj({'revision': INT, 'columns': {**array(TEXT), 'description': 'Fixed columns: type, value, description.'}, 'rows': ROWS, 'sections': array(ref('IndicatorSection'))}, ('revision',)), description='Send all sections to preserve grouping, or rows when exactly one section exists. Each row has three text cells (≤4,000 characters), 1–100 sections with unique IDs (1–64 alphanumeric/underscore/hyphen), a nonempty title ≤200 characters and description ≤4,000 characters. The default section must remain; ≤10,000 rows total. revision must equal the current revision. The bundled official MISP attribute catalog is selectable/storable; export capability/help is supplied per type. Known compatibility aliases normalize on save; exact MISP canonical names take precedence. text/comment/other retain literal Unicode/whitespace and export as non-detection x-misp-attribute objects; Valid scalar attributes without native mappings use the official MISP-compatible contextual representation, with informational stix.notices. Missing attachment/sample bytes and invalid values retain saved drafts with explicit stix.issues. Legacy android-package aliases normalize to mobile-application-id while retaining identity and original_type provenance. Unknown/ambiguous types and invalid values remain saved as drafts with stix.issues; CSV is refreshed and stale STIX removed. Fully exportable tables generate iocs/indicators.stix.json with refanged native patterns and faithful contextual objects; any unsupported row withholds the entire STIX output. Preserve optional row_meta (including explicit boolean to_ids detection intent) and stix_meta when editing to retain IDs/timestamps/intent; do not generate them yourself. Unchanged saves do not advance revision. The authenticated web Indicators workspace provides CSV/STIX import previews and a read-only download; these internal UI routes are not public REST endpoints.', errors=(409,))
contract('case_references', 'PUT', 'Replace references with revision validation', json_response(ref('References')), body=obj({'revision': INT, 'rows': array(array(CELL, minItems=2, maxItems=2), maxItems=10000)}, ('revision', 'rows')), description='Fixed columns Link, Description. revision must equal the current revision.', errors=(409,))
contract('case_report', 'GET', 'Read report sections and mappings', result(sections=SECTIONS_SCHEMA, mappings=MAPPINGS, report_path=TEXT, report_exists=BOOL))
contract('case_report', 'PUT', 'Save manual report sections', result(sections=SECTIONS_SCHEMA), body=obj({'sections': SECTIONS_SCHEMA}, ('sections',)), description='Only manual sections are written; generated sections are accepted but not persisted. Omitted manual sections retain their current values.')
contract('case_report_mappings', 'GET', 'Read MITRE mappings', result(mappings=MAPPINGS))
contract('case_report_mappings', 'PUT', 'Save MITRE mapping Markdown', result(mappings=MAPPINGS), body=obj({'mappings': MAPPINGS}, ('mappings',)), description='Blank text removes that mapping. Active report generation blocks saving.', errors=(409,))
contract('export_case', 'POST', 'Download a Standard or RAW MIP ZIP', download('application/zip'), body=obj({'archive_type': {**TEXT, 'enum': ['standard', 'raw'], 'default': 'standard'}, 'include_samples': {**BOOL, 'default': False}, 'acknowledge': {**BOOL, 'default': False}}), description='Packaging & Delivery or Completed only; active owner required when mandatory. Standard requires a completed Word report. Outstanding review blockers require acknowledge=true. Including samples additionally requires samples:export. Malware sample archives are dangerous; handle only in an isolated analysis environment.', errors=(409,))
contract('case_report_job', 'GET', 'Read the latest report generation job', result(job=ref('Job')))
contract('generate_case_report', 'POST', 'Start local Word report generation', result(job_id=TEXT), body=obj({'generation_mode': {**TEXT, 'enum': ['manual'], 'default': 'manual'}, 'previous': {**TEXT, 'enum': ['backup', 'overwrite']}, 'generate_pdf': {'oneOf': [{**TEXT, 'enum': ['0', '1']}, BOOL], 'description': '0 or false skips PDF conversion; default is enabled.'}, 'sections': SECTIONS_SCHEMA, **{key: MARKDOWN for key in SECTIONS}}), status=202, description='Select an available template first. Generation saves supplied manual sections; omitted manual fields become empty. Read and submit existing sections to retain them. Existing reports require an explicit previous=backup or overwrite choice (409 needs_choice otherwise). Poll report/job; PDF generation requires LibreOffice. Accepts JSON or form fields.', errors=(409,))
contract('upload_final_report', 'POST', 'Upload an edited DOCX report', result(saved=BOOL, report_exists=BOOL, report_path=TEXT, report_files=array(ref('File'))), body=obj({'report': BINARY, 'backup': {**TEXT, 'enum': ['0', '1']}, 'generate_pdf': {**TEXT, 'enum': ['0', '1'], 'default': '1'}}, ('report',)), media='multipart/form-data', description='Valid DOCX ≤20 MiB required. backup=1 saves the previous report. generate_pdf=0 skips PDF conversion; otherwise LibreOffice is required. Active report jobs block replacement.', errors=(409,))
contract('download_report', 'GET', 'Download the current report', download(DOCX, 'application/pdf'), parameters=[field('format', {**TEXT, 'enum': ['docx', 'pdf'], 'default': 'docx'})], description='404 if the requested output has not been generated.')
contract('report_images', 'GET', 'List report image metadata', result(images=array(ref('Image'))))
contract('report_images', 'POST', 'Upload a report or task image', json_response(ref('Image')), body=obj({'image': BINARY, 'section': {**TEXT, 'description': 'A manual report section key, task-draft, or task-<task_id>.', 'example': 'key_findings'}}, ('image', 'section')), media='multipart/form-data', status=201, description='Readable image ≤10 MiB and ≤20 megapixels; normalized to PNG. Active report jobs block changes.', errors=(409,))
contract('report_image', 'GET', 'Download a report image', download('image/png', inline=True))
contract('report_image', 'DELETE', 'Delete a report image', status=204, errors=(409,))
contract('templates', 'GET', 'List your Word templates', result(templates=array(ref('Template'))))
contract('templates', 'POST', 'Upload and select a Word template', result(message=TEXT, templates=array(ref('Template'))), body=obj({'template': BINARY}, ('template',)), media='multipart/form-data', status=201, description='DOCX ≤10 MiB, containing every report section heading or placeholder. Templates belong to the requesting user.')
contract('select_template', 'PUT', 'Select your Word template', result(templates=array(ref('Template'))), body=obj({'template_id': {**TEXT, 'description': 'Own template ID; empty string clears the selection.'}}))
contract('template_item', 'GET', 'Download your Word template', download(DOCX))
contract('template_item', 'DELETE', 'Delete your Word template', status=204)
contract('case_backup', 'POST', 'Download a case RAW backup ZIP', download('application/zip'), description='Includes case metadata and email-safe Python filenames. Malware samples excluded.', errors=(400, 409))
contract('export_all_cases', 'POST', 'Download a full case backup ZIP', download('application/zip'), description='Includes nested case RAW ZIPs and metadata; excludes malware samples.', errors=(400, 409))
contract('api_database_backup', 'POST', 'Retired plaintext installation backup', json_response(obj({'error': TEXT, 'workspace': TEXT})), status=410, description='Complete archives require an authenticated encrypted export from /backup-restore with a user-supplied passphrase. Selective backup APIs remain supported.')
contract('api_import_backup', 'POST', 'Stage a backup or RAW ZIP for synchronization review', result(operation=TEXT, cases=array(ref('SyncCase')), apply_url=TEXT), body=obj({'backup': BINARY}, ('backup',)), media='multipart/form-data', status=202, description='Validates archive paths, resource limits, checksums and case metadata. Does not immediately apply changes. Review with backups/review/{operation}, then explicitly apply. Review is bound to the importing account and expires after one hour. import and import-raw are aliases.')
contract('sync_api_review', 'GET', 'Review a staged synchronization or its outcomes', json_response(ref('SyncResult')), description='Only the account that staged the archive may access it. Expired preview returns 410.', errors=(410,))
contract('sync_api_apply', 'POST', 'Apply validated per-case synchronization decisions', json_response(ref('SyncResult')), body=obj(additionalProperties=obj({'decision': {**TEXT, 'enum': ['keep', 'replace', 'new', 'link']}, 'owner': {**TEXT, 'enum': ['local', 'incoming'], 'default': 'local'}, 'target': TEXT})), required=False, description='Object keyed by the zero-based review case index (string). Omitted decisions apply safe automatic new/update/unchanged/older actions; unresolved/invalid cases are skipped. Conflicts need explicit keep or replace. Legacy review also supports new or link (target is a local numeric case ID). Revision validation, ownership checks and recovery snapshots remain enforced; inspect each actual outcome for failure/rollback. Only the staging account may apply; preview expires after one hour.', errors=(410,))
contract('metrics', 'GET', 'Read all-time metrics', result(users=array(obj({'id': INT, 'username': TEXT, 'active': INT, **dict.fromkeys(('created_count', 'assigned_count', 'progress_count', 'completed_count'), INT)})), stages=array(obj({'label': TEXT, 'value': INT})), completed=array(obj({'label': TEXT, 'value': INT}))), description='Legacy all-time API metrics; independent of dashboard period filters.')

_generate = CONTRACTS[('generate_case_report', 'POST')]['requestBody']['content']
_generate['application/x-www-form-urlencoded'] = {'schema': obj({
    'generation_mode': {**TEXT, 'enum': ['manual']},
    'previous': {**TEXT, 'enum': ['backup', 'overwrite']},
    'generate_pdf': {**TEXT, 'enum': ['0', '1'], 'default': '1'},
    **{key: MARKDOWN for key in SECTIONS},
})}

CONTENT_EDITORS = {'case_readiness', 'case_tasks', 'case_task', 'case_notes', 'case_note', 'case_draft', 'case_assets',
                   'case_indicators', 'case_references', 'case_report', 'case_report_mappings',
                   'generate_case_report', 'upload_final_report', 'report_images', 'report_image'}


def build_spec(app, script_root=''):
    """Resolve exact registered paths and permission metadata without API calls."""
    paths = {}
    for rule in sorted(app.url_map.iter_rules(), key=lambda item: item.rule):
        if not rule.rule.startswith('/api/v1/'):
            continue
        endpoint = rule.endpoint.removeprefix('api.')
        path = re.sub(r'<(?:[^:>]+:)?([^>]+)>', r'{\1}', rule.rule[len('/api/v1'):])
        permission = getattr(app.view_functions[rule.endpoint], 'permission', None)
        for method in sorted(rule.methods - {'OPTIONS', 'HEAD'}):
            operation = copy.deepcopy(CONTRACTS[(endpoint, method)])
            needed = permission.get(method) if isinstance(permission, dict) else permission
            if endpoint.startswith('sync_api_'):
                needed = 'backups:manage'
            operation['operationId'] = endpoint + '_' + method.lower() + ('_raw' if path.endswith('import-raw') else '')
            tag = path.strip('/').split('/')[0].title()
            if '/report' in path:
                tag = 'Reports'
            operation['tags'] = [tag]
            operation['x-required-permission'] = needed
            operation['description'] += '\n\nRequired role permission: ' + (needed or 'any authenticated API user') + '.'
            errors = {401, 403, 429, 500, *operation.pop('x-errors')}
            if rule.arguments:
                errors.add(404)
            if operation['parameters'] or operation.get('requestBody'):
                errors.add(400)
            if 'requestBody' in operation:
                errors.add(413)
            if endpoint in CONTENT_EDITORS and method != 'GET':
                errors.add(409)
                operation['description'] += '\n\nContent edits require Malware Analysis or Packaging & Delivery stage and an active owner when ownership is mandatory.'
            if method != 'GET':
                operation['description'] += '\n\nExecute affects real application data. Nothing executes automatically.'
            for name in sorted(rule.arguments):
                converter = rule._converters[name]
                schema = INT if converter.__class__.__name__ == 'IntegerConverter' else TEXT
                operation['parameters'].append({'name': name, 'in': 'path', 'required': True, 'schema': schema})
            for status in sorted(errors):
                operation['responses'].setdefault(str(status), json_response(ref('Error'), {
                    400: 'Invalid input or failed validation.', 401: 'Missing, expired, revoked or invalid bearer token.',
                    403: 'Missing role permission or required password change.', 404: 'Resource not found or not owned by caller.',
                    409: 'Conflict with current state, revision, or active job.', 410: 'Staged import expired.',
                    413: 'Upload exceeds the configured request/file limit.', 429: 'Per-token request limit exceeded (default 600/minute).',
                    500: 'Unexpected server error.'}[status], {'error': 'Illustrative error; consult the actual response.'}))
            paths.setdefault(path, {})[method.lower()] = operation
    return {'openapi': '3.0.3', 'info': {'title': 'MARE Work Sequencer API', 'version': '1',
            'description': 'Existing public REST API. The default total request limit is 100 MiB (including multipart overhead); backup imports allow 1 GiB. Proxy limits also apply. Authorize with a bearer token created in the API tab; enter only the secret, without the Bearer prefix. Tokens use the account’s current role permissions, not the web session. Administrator has all permissions; custom roles may differ. Disabled accounts, forced password changes, revoked/expired tokens and rate limits remain enforced. State-changing operations affect real data. No requests run automatically.'},
            'servers': [{'url': (script_root.rstrip('/') + '/api/v1'), 'description': 'This MARE deployment (same origin)'}],
            'security': [{'bearerAuth': []}], 'paths': paths,
            'components': {'securitySchemes': {'bearerAuth': {'type': 'http', 'scheme': 'bearer', 'description': 'Authorization: Bearer <token>. Enter the secret only. Not saved in browser storage.'}}, 'schemas': SCHEMAS}}
