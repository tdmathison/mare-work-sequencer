from app import app


def test_shared_tab_macro_supports_links_buttons_disabled_icons_and_counts():
    with app.test_request_context():
        html = app.jinja_env.from_string('''{% from 'components/tabs.html' import bar,item %}
{% call bar('Example') %}{{item('First','first',active=true,controls='first-panel',icon='◇',badge=4)}}{{item('Locked','locked',disabled=true,title='Permission required')}}{% endcall %}
{% call bar('Routes',links=true,attributes={'data-tabs-links':''}) %}{{item('Settings','settings',active=true,href='/settings/general')}}{{item('Unavailable','unavailable',href='/unavailable',disabled=true,title='Unavailable')}}{% endcall %}''').render()
    assert 'class="mws-tabs ' in html and 'class="mws-tab"' in html
    assert 'role="tablist"' in html and 'aria-controls="first-panel"' in html
    assert 'aria-selected="true" tabindex="0"' in html
    assert ' disabled title="Permission required"' in html
    assert 'mws-tab-icon' in html and 'mws-tab-count">4' in html
    assert 'href="/settings/general" aria-current="page"' in html
    assert 'aria-disabled="true" tabindex="-1"' in html
    assert 'data-tabs-links=' in html


def test_workspace_templates_use_the_shared_component():
    # Prevent separate visual implementations from returning as pages evolve.
    for filename in ('case.html','tools.html','settings_shell.html'):
        source = app.jinja_env.loader.get_source(app.jinja_env, filename)[0]
        assert "from 'components/tabs.html' import bar, item" in source
        assert 'call bar(' in source


def test_comparable_page_tabs_adopt_component_without_local_style_copies():
    from pathlib import Path
    import re
    root = Path(app.root_path)
    for filename in ('case.html', 'tools.html', 'settings_shell.html', 'backup_workspace.html', 'developer_plugins.html', 'malware_families.html'):
        source = (root / 'templates' / filename).read_text()
        assert "from 'components/tabs.html' import bar, item" in source
        assert 'call bar(' in source
        assert 'role="tablist"' not in source or filename == 'case.html'  # Archive-format selector is intentionally separate.
    aliases = r'\.(?:mws-tabs|mws-tab|case-tabs|tool-tabs|settings-categories|backup-tabs|plugin-detail-tabs|family-tabs)(?![\w-])'
    for path in (root / 'static').glob('*.css'):
        if path.name == 'mws-tabs.css':
            continue
        selectors = re.findall(r'([^{}]+)\{', path.read_text())
        assert not any(re.search(aliases, selector) for selector in selectors), f'Page-specific shared tab styling in {path.name}'


def test_new_raw_tablists_require_an_explicit_audit_decision():
    from pathlib import Path
    import re
    # These are nested editor/mode controls, not copies of workspace navigation.
    allowed = {
        'case.html': ['Archive type'],
        'developer_editor.html': ['Open files', 'Console tabs'],
        'indicators.html': ['Import format'],
        'report_workspace.html': ['Editor view'],
        'tasks.html': ['Task description view'],
        'snort_builder.html': ['Rule assistance'],
        'yara_editor.html': ['YARA assistance'],
        'data_explorer.html': ['Investigation inventory'],
    }
    found = {}
    for path in (Path(app.root_path) / 'templates').rglob('*.html'):
        if path.name == 'tabs.html' and path.parent.name == 'components':
            continue
        source = path.read_text()
        assert not re.search(r'<nav[^>]*class="[^"]*\b[\w-]*tabs\b', source), f'Use the shared routed tab bar in {path.name}'
        labels = re.findall(r'<[^>]*role="tablist"[^>]*aria-label="([^"]+)"', source)
        if labels:
            found[path.name] = labels
    assert found == allowed, 'Use components/tabs.html or document a new specialist control in the audit.'
