"""FIRST TLP 2.0 Case sharing designations; unrelated to severity or permissions."""
DEFAULT = 'TLP:AMBER'
METADATA = {
    'TLP:RED': {'color':'#FF2B2B', 'help':'For individual recipients only; do not share further.'},
    'TLP:AMBER+STRICT': {'color':'#FFC000', 'help':'Share only within your organization, on a need-to-know basis.'},
    'TLP:AMBER': {'color':'#FFC000', 'help':'Share within your organization and with its clients, on a need-to-know basis.'},
    'TLP:GREEN': {'color':'#33FF00', 'help':'Share within your community; do not publish on publicly accessible channels.'},
    'TLP:CLEAR': {'color':'#FFFFFF', 'help':'May be shared publicly, subject to copyright and other applicable rules.'},
}


def validate(value):
    if not isinstance(value, str) or value not in METADATA:
        raise ValueError('Choose a supported TLP designation: ' + ', '.join(METADATA) + '.')
    return value


def default(connection):
    row = connection.execute("SELECT value FROM site_settings WHERE name='default_case_tlp'").fetchone()
    return validate(row[0]) if row else DEFAULT


def archived(record):
    # Missing legacy fields differ from explicit null/blank/unsupported values.
    return validate(record['tlp']) if 'tlp' in record.keys() else DEFAULT


def snapshot_fields(record):
    value = archived(record)
    # Keep pre-TLP revision fingerprints valid; AMBER is the legacy assumption.
    return {'tlp': value} if value != DEFAULT else {}


def initialize(connection):
    columns = {r[1] for r in connection.execute('PRAGMA table_info(cases)')}
    if 'tlp' not in columns:
        connection.execute("ALTER TABLE cases ADD COLUMN tlp TEXT NOT NULL DEFAULT 'TLP:AMBER'")
    connection.execute("UPDATE cases SET tlp=? WHERE tlp IS NULL OR tlp=''", (DEFAULT,))
    for row in connection.execute('SELECT DISTINCT tlp FROM cases'):
        validate(row[0])
    allowed = ','.join("'"+value+"'" for value in METADATA)
    for operation in ('INSERT', 'UPDATE OF tlp'):
        name = 'insert' if operation == 'INSERT' else 'update'
        connection.execute(f"""CREATE TRIGGER IF NOT EXISTS valid_case_tlp_{name}
          BEFORE {operation} ON cases WHEN NEW.tlp IS NULL OR NEW.tlp NOT IN ({allowed})
          BEGIN SELECT RAISE(ABORT,'Invalid Case TLP designation'); END""")


def track_sync(connection):
    connection.execute('''CREATE TRIGGER IF NOT EXISTS sync_dirty_case_tlp_update
      AFTER UPDATE OF tlp ON cases WHEN NEW.tlp!=OLD.tlp
      BEGIN INSERT OR IGNORE INTO sync_dirty VALUES(NEW.id); END''')
