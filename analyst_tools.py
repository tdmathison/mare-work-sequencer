"""Case-independent analyst tools; vendor files are never public static assets."""
from dataclasses import dataclass
from pathlib import Path
import re
from flask import abort, g, make_response, render_template, send_from_directory, url_for
from authorization import has_permission


@dataclass(frozen=True)
class AnalystTool:
    identifier: str
    name: str
    description: str
    icon: str = '◇'
    endpoint: str = ''
    tool_type: str = 'embedded'
    enabled: bool = True
    permission: str | None = None


CYBERCHEF = AnalystTool('cyberchef', 'CyberChef', 'Local decoding, transformation, and analysis', '⚗', 'tools_cyberchef')


def register_tool(app, tool):
    """Register trusted application code, not user-supplied plugins."""
    if not re.fullmatch(r'[a-z][a-z0-9-]*', tool.identifier):
        raise ValueError('Tool identifiers must be lowercase URL-safe names')
    if tool.tool_type not in ('embedded', 'native') or not tool.endpoint:
        raise ValueError('Tools require a native/embedded type and Flask endpoint')
    registry = app.extensions['analyst_tools']
    if tool.identifier in registry:
        raise ValueError(f'Duplicate tool identifier: {tool.identifier}')
    registry[tool.identifier] = tool


def require_tool(app, db, identifier):
    """Call from each tool backend route, after MARE's session authentication."""
    tool = app.extensions['analyst_tools'].get(identifier)
    if not tool or not tool.enabled:
        abort(404)
    if not g.user or (tool.permission and not has_permission(g.user, tool.permission, db())):
        abort(403)
    return tool


def register_tools(app, db):
    app.extensions['analyst_tools'] = {}
    register_tool(app, CYBERCHEF)
    app.config.setdefault('CYBERCHEF_DIR', str(Path(app.root_path)/'vendor/cyberchef/dist'))

    def allowed(tool):
        return tool.enabled and (not tool.permission or has_permission(g.user, tool.permission, db()))

    @app.get('/tools')
    @app.get('/tools/<tool_id>')
    def tools_workspace(tool_id=None):
        available = [tool for tool in app.extensions['analyst_tools'].values() if allowed(tool)]
        selected = require_tool(app, db, tool_id) if tool_id else (available[0] if available else None)
        response = make_response(render_template('tools.html', tools=available, selected=selected))
        response.headers['Cache-Control'] = 'no-store'
        return response

    @app.get('/tools/cyberchef/app/')
    @app.get('/tools/cyberchef/app/<path:filename>')
    def tools_cyberchef(filename='index.html'):
        require_tool(app, db, 'cyberchef')
        root = Path(app.config['CYBERCHEF_DIR']).resolve()
        target = (root/filename).resolve()
        if not target.is_relative_to(root):
            abort(404)
        if not (root/'index.html').is_file():
            response = make_response(render_template('tool_setup.html'), 503)
        elif filename == 'index.html':
            html = target.read_text(encoding='utf-8')
            # Upstream theme selectors have high specificity. Our overrides load last.
            theme = url_for('tools_cyberchef', filename='mare-theme.css')
            html = re.sub(r'</head>', f'<link rel="stylesheet" href="{theme}"></head>', html, count=1, flags=re.I)
            response = make_response(html)
        elif filename == 'mare-palette.css':
            css = (Path(app.root_path)/'static/mare.css').read_text()
            palette = re.search(r':root\s*\{[^}]+\}', css).group(0)
            response = make_response(palette)
            response.mimetype = 'text/css'
        elif filename == 'mare-theme.css':
            response = send_from_directory(Path(app.root_path)/'resources', 'cyberchef-theme.css')
        else:
            response = send_from_directory(root, filename)
        response.headers.update({
            'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff',
            'Referrer-Policy': 'no-referrer', 'X-Frame-Options': 'SAMEORIGIN',
            'Content-Security-Policy': "default-src 'none'; script-src 'self' 'unsafe-inline' 'unsafe-eval' blob:; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; font-src 'self' data:; connect-src 'self' blob: data:; worker-src 'self' blob:; frame-src 'none'; object-src 'none'; base-uri 'self'; form-action 'none'; frame-ancestors 'self'",
        })
        return response
