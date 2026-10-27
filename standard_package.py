"""Shared Standard/RAW file selection. Planning never scaffolds or writes files."""
from pathlib import Path
from mip import CATEGORIES, OPTIONAL_TEMPLATES
from reporting import current_report, is_backup


def raw_file(rel, include_samples=False):
    return (rel.split('/')[0] in CATEGORIES and not is_backup(rel)
            and (not rel.startswith('samples/') or (include_samples and Path(rel).suffix.lower()=='.zip')))


def standard_file(record, root, rel):
    if not raw_file(rel) or rel.startswith('samples/'):
        return False
    if rel.startswith('reports/') and (rel.startswith('reports/sections/')
            or Path(rel).suffix.lower()=='.md' or rel==current_report(record, root)):
        return False
    if rel in OPTIONAL_TEMPLATES and (root/rel).read_text(errors='replace').strip()==OPTIONAL_TEMPLATES[rel].strip():
        return False
    return True


def selected_files(record, root, *, raw=False, include_samples=False):
    result={}
    if not root.is_dir() or any(p.is_symlink() for p in (root,*root.parents)):
        return result
    for path in sorted(root.rglob('*')):
        rel=path.relative_to(root).as_posix()
        if not path.is_file() or any(p.is_symlink() for p in (path,*path.parents)):
            continue
        if (raw_file(rel, include_samples) if raw else standard_file(record,root,rel)
                or (include_samples and rel.startswith('samples/') and path.suffix.lower()=='.zip' and not is_backup(rel))):
            result[rel]=path
    return result


def planned_standard(connection, record, root, *, indicator_table=None):
    """Predict the export's derived STIX refresh without writing or building a ZIP."""
    from indicators import load_table
    from indicator_stix import build_bundle
    files=selected_files(record,root)
    bundle,_=build_bundle((indicator_table if indicator_table is not None else load_table(lambda:connection,record['id']))['sections'])
    files.pop('iocs/indicators.stix.json',None)
    if bundle is not None:
        files['iocs/indicators.stix.json']=bundle.encode()
    return files
