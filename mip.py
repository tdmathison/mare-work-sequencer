from pathlib import Path
import re
CATEGORIES={'reports':'Reports','iocs':'IOCs','signatures':'Signatures','scripts':'Scripts','mappings':'MITRE tables','supporting':'Supporting evidence','samples':'Samples'}
REPORT_TEMPLATE='''# Malware Analysis Report

## Executive Summary
[Add the key findings and stakeholder impact.]

## Sample Identification
[Record hashes and identifying details.]

## Findings
[Summarize the analyst findings and supporting evidence.]

## Indicators and Detection
[Reference IOC lists and signatures, or explain why none apply.]

## Recommendations
[Add recommended actions and limitations.]
'''
GUIDANCE=[
'Case created. Update its details, then start analysis to unlock the workspace.',
'Collect analysis findings, notes, scripts, indicators, and supporting evidence. Draft or generate reports as you work.',
'Review the completion checklist, build the MIP ZIP, and deliver it. Resolve outstanding actions before marking the case complete.',
'The case is complete. View or regenerate the MIP ZIP at any time. Reopen the case to edit its content.'
]
OPTIONAL_TEMPLATES={'reports/executive-summary.md':'# Executive Summary\n\n[Add the stakeholder summary.]\n','mappings/mitre-attack.md':'# MITRE ATT&CK\n\n| Technique ID | Technique | Evidence |\n|---|---|---|\n','mappings/mitre-mbc.md':'# Malware Behavior Catalog\n\n| Behavior ID | Behavior | Evidence |\n|---|---|---|\n'}

def slugify(value):
    value=re.sub(r'\s+','_',value.strip());return re.sub(r'[^A-Za-z0-9._-]+','-',value).strip('-_') or 'mip'
def create_mip(root:Path,name:str,package_type='SAFE',force=False):
    p=root/slugify(name);p.mkdir(parents=True,exist_ok=True)
    for folder in CATEGORIES: (p/folder).mkdir(exist_ok=True)
    files={'reports/malware-analysis-report.md':REPORT_TEMPLATE,'reports/executive-summary.md':OPTIONAL_TEMPLATES['reports/executive-summary.md']}
    for rel,text in files.items():
        if not (p/rel).exists(): (p/rel).write_text(text)
    clean_mapping_placeholders(p)
    return p

def clean_mapping_placeholders(root):
    """Retain analyst content; remove only exact old scaffolding files."""
    for rel,text in OPTIONAL_TEMPLATES.items():
        path=root/rel
        if rel.startswith('mappings/') and path.is_file() and not path.is_symlink() and path.read_bytes()==text.encode():path.unlink()
