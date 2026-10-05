from app import app

def test_ai_routes_and_dependencies_removed():
    endpoints={rule.rule for rule in app.url_map.iter_rules()}
    assert '/account/ai' not in endpoints
    assert '/cases/<int:cid>/report-assist' not in endpoints
    assert '/cases/<int:cid>/indicators/ingest' not in endpoints
    from pathlib import Path
    requirements=Path('requirements.txt').read_text().lower()
    assert 'openai' not in requirements and 'cryptography' not in requirements
