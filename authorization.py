PERMISSIONS={
    'cases:read':'Read case records and workspaces',
    'cases:create':'Create cases',
    'cases:update':'Edit case details and workflow data',
    'cases:delete':'Delete cases',
    'cases:workflow':'Advance and reopen case stages',
    'cases:assets':'List, download, upload, and delete case assets',
    'cases:export':'Export MIP archives',
    'samples:export':'Include password-protected malware sample archives in exports',
    'indicators:read':'Read case indicators',
    'indicators:write':'Edit case indicators',
    'references:read':'Read case references',
    'references:write':'Edit case references',
    'reports:read':'Read report data and jobs',
    'reports:write':'Edit report sections and mappings',
    'reports:generate':'Generate and upload reports',
    'settings:read':'Read non-secret site settings',
    'settings:write':'Change site settings',
    'users:manage':'Create, update, and delete user accounts',
    'roles:manage':'Create roles and manage role permissions',
    'tokens:manage':'Create and revoke personal bearer tokens',
    'metrics:read':'Read workload metrics',
    'templates:manage':'Manage your own Word report templates',
    'audit:read':'Read audit events',
    'backups:manage':'Create or restore site backups',
}

USER_PERMISSIONS={
    'cases:read','cases:create','cases:update','cases:delete','cases:workflow',
    'cases:assets','cases:export','indicators:read','indicators:write',
    'references:read','references:write','reports:read','reports:write',
    'reports:generate','tokens:manage','metrics:read','templates:manage',
}

def initialize_roles(connection):
    connection.executescript('''
    CREATE TABLE IF NOT EXISTS roles(
        name TEXT PRIMARY KEY,
        description TEXT NOT NULL DEFAULT '',
        builtin INTEGER NOT NULL DEFAULT 0
    );
    CREATE TABLE IF NOT EXISTS role_permissions(
        role_name TEXT NOT NULL REFERENCES roles(name) ON DELETE CASCADE,
        permission TEXT NOT NULL,
        PRIMARY KEY(role_name,permission)
    );
    ''')
    connection.execute('INSERT OR IGNORE INTO roles(name,description,builtin) VALUES(?,?,1)',('Administrator','Full access',))
    connection.execute('INSERT OR IGNORE INTO roles(name,description,builtin) VALUES(?,?,1)',('User','Standard case access',))
    for permission in PERMISSIONS:
        connection.execute('INSERT OR IGNORE INTO role_permissions VALUES(?,?)',('Administrator',permission))
    for permission in USER_PERMISSIONS:
        connection.execute('INSERT OR IGNORE INTO role_permissions VALUES(?,?)',('User',permission))
    connection.commit()

def has_permission(user,permission,connection):
    if not user:return False
    if user['role']=='Administrator':return True
    return connection.execute('SELECT 1 FROM role_permissions WHERE role_name=? AND permission=?',(user['role'],permission)).fetchone() is not None

def role_records(connection):
    roles=connection.execute('SELECT name,description,builtin FROM roles ORDER BY builtin DESC,name').fetchall()
    return [dict(name=row['name'],description=row['description'],builtin=bool(row['builtin']),permissions=[item['permission'] for item in connection.execute('SELECT permission FROM role_permissions WHERE role_name=? ORDER BY permission',(row['name'],))]) for row in roles]