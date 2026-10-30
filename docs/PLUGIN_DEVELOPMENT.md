# External Python plugin development

Developer provides **API → SDK → Plugins**. Author and test Python code in VS Code
or another external environment. MWS has no embedded source editor, file API,
scaffolding, autocomplete server, debugger or development-run service.

From a checkout, create a Python 3 environment and install the actual SDK:

```sh
python3 -m venv .venv-plugin
.venv-plugin/bin/python -m pip install -e ./sdk
.venv-plugin/bin/python -m pip install pytest
```

Select `.venv-plugin/bin/python` in VS Code. Python/Pylance can use the SDK's
shipped types. Set `MWS_BASE_URL` to your HTTPS MWS origin and `MWS_API_KEY` to a
short-lived token with only the permissions you need. Use a shell or secret
manager; never put tokens in packages, manifests or committed VS Code settings.
Run a standalone SDK script with `.venv-plugin/bin/python your_script.py`:

```python
from mws_sdk import MWSClient

with MWSClient() as client:
    print(client.plugins.capabilities())
```

The existing package format is unchanged. Start from `examples/hello_world_plugin`:

```text
hello_world_plugin/
  plugin.json
  main.py
```

`plugin.json` declares `schema: mws-plugin/1`, identifier, version, author,
`entrypoint: main.py:run`, `plugin_api: 1`, API/SDK versions, dependencies and
permissions. `main.py` exports `run(context)`. The context satisfies
`mws_sdk.plugin.PluginContext`; use `context.client`, `context.configuration` and
`context.log`. Unit-test locally with a fixture implementing this protocol and
mock the APIs the plugin uses. A local SDK script is executed by your Python
interpreter; it is not submitted to MWS as arbitrary development code.

An operator installs the complete directory into `MARE_PLUGINS_DIR` (default:
`<checkout>/plugins/`), then refreshes Developer → Plugins. Discovery validates
packages without importing their Python. Registration requires `plugins:install`;
configuration, version management/enablement, deletion and execution retain their
separate permissions and owner checks. Configuration secrets are encrypted and
are not returned to the browser. Protected plugins cannot be deleted.

Configure required values and Enable the plugin. Operational runs use the
installed immutable version and the [isolated runtime](PLUGIN_RUNTIME.md).
No browser action can create, import, edit or publish source. To update a package,
increment its manifest version, replace its directory atomically and rescan.
Changing files under an existing version is rejected. Existing runs retain their
snapshots, and configuration and enablement survive a rescan. Rollback selects an
existing immutable installed version. Deletion moves the installed directory into
the plugin root's `.mws-deleted` area for administrator recovery; history remains.

The SDK's `plugins.capabilities()` reports authorized tools and registered plugins.
API documentation, SDK documentation, folder discovery and configuration work
without an execution service. Other tools and report/Markdown/Text editors keep
their existing CodeMirror integrations.

## Upgrade and recovery

`retire-developer-editor-v1` is a forward migration. The old editable file table is
converted into immutable `plugin_packages` ZIP snapshots and removed. Existing
plugin registrations, configuration, secrets, installed versions and execution/
audit records are retained; obsolete editor session tokens are revoked and active
editor sessions are canceled. Historical migration markers are preserved. Normal
registry/version/execution/grant tables retain their historical `developer_`
prefix because they are still operational plugin data, not editor session models.

Complete backups validate their original hashes and row counts before applying
this migration. Legacy workspace source is retained as package archives, not
recreated as web-editable workspaces. If an old registration has no disk package,
its source remains in `plugin_packages.archive`; an administrator can recover
that ZIP to a reviewed directory and install it using the same package format.
Back up operator-managed external plugin directories separately as well as the
MWS data backup. Never overwrite an existing package during recovery.
