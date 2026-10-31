from pathlib import Path
from app import app


def test_intelligence_pages_share_structure_and_workspace_geometry():
    root=Path(app.root_path)
    for name in ('malware_families.html','tags.html'):
        source=(root/'templates'/name).read_text()
        assert "import 'components/intelligence_workspace.html' as workspace" in source
        for component in ('assets','heading','toolbar','directory','choice','detail_header','tabs','empty','footer','history_heading','history_table'):
            assert f'workspace.{component}(' in source
        assert 'data-intelligence-workspace' in source
        assert 'class="family-profile-header"' not in source
    # Geometry has one owner; domain styles cannot redefine pane widths or tab insets.
    for name in ('malware-families.css','tag-workspace.css'):
        source=(root/'static'/name).read_text()
        for selector in ('.family-layout','.family-selector','.family-choice','.family-workspace','.family-profile-header','.tag-layout','.tag-tabs-container'):
            assert selector not in source
    css=(root/'static/intelligence-workspace.css').read_text()
    assert '--workspace-directory-width:300px' in css
    assert 'data-mobile-detail=true' in css and 'data-mobile-detail=false' in css
