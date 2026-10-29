"""Optional real type checker check; source is analyzed, never imported/executed."""

import json
import os
from pathlib import Path
import subprocess
import pytest
import plugin_store as store
from test_plugin_workspace import metadata


@pytest.mark.skipif(
    not os.environ.get("MARE_TEST_LANGUAGE_SERVER"),
    reason="Requires an isolated basedpyright installation",
)
def test_all_wizard_templates_pass_real_type_and_import_checks(tmp_path):
    server = Path(os.environ["MARE_TEST_LANGUAGE_SERVER"]).resolve()
    environment = server.parent.parent
    include = []
    for template in store.TEMPLATES:
        folder = tmp_path / template
        folder.mkdir()
        for name, item in store.template_files(
            metadata("template_" + template), template
        ).items():
            path = folder / name
            if item["directory"]:
                path.mkdir(parents=True, exist_ok=True)
            else:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(item["body"])
        include.append(str(folder / "main.py"))
    configuration = tmp_path / "pyrightconfig.json"
    configuration.write_text(
        json.dumps(
            {
                "typeCheckingMode": "basic",
                "extraPaths": [str(Path(__file__).resolve().parents[1] / "sdk")],
                "include": include,
                "venvPath": str(environment.parent),
                "venv": environment.name,
            }
        )
    )
    result = subprocess.run(
        [
            str(server.with_name("basedpyright")),
            "--project",
            str(configuration),
            "--outputjson",
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=30,
    )
    report = json.loads(result.stdout)
    assert report["summary"]["errorCount"] == 0, report["generalDiagnostics"]
    assert result.returncode == 0, result.stderr
