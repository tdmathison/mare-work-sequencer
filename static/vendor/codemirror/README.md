# Locally bundled CodeMirror 6

Source: `frontend/markdown-editor.js`, `frontend/markdown-commands.js`,
`frontend/markdown-toolbar.js`, and `frontend/markdown-editor.css`.
Official upstream: https://codemirror.net/ and https://github.com/codemirror
Exact dependency versions and integrity hashes: `package-lock.json`.
Production dependency license texts: `THIRD_PARTY_LICENSES.txt`.

Rebuild from the repository root with `npm ci && npm run build:editors`.
Commit the compiled JS/CSS and notices together with source and lockfile updates.
Flask serves these files locally; production requires no Node runtime or CDN.
CodeMirror creates its own scoped theme CSS from the compiled JavaScript at runtime.
The companion CSS resets MARE's global form styles inside the editor/search panels.

After updates, run `npm run test:editors` and the Flask suite. See README.md for
browser installation, isolated test data, migration inventory, and theme guidance.
