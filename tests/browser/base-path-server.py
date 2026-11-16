"""Local stripped-prefix proxy simulator; does not replace target nginx -t."""
import os
import runpy
from pathlib import Path
from werkzeug.serving import run_simple
from werkzeug.wrappers import Response

fixture = runpy.run_path(str(Path(__file__).with_name('server.py')))
app = fixture['app']
prefix = os.environ.get('MWS_BASE_PATH', '').rstrip('/')


def proxy(environ, start_response):
    path = environ['PATH_INFO']
    if prefix:
        if path == prefix:
            query = environ.get('QUERY_STRING', '')
            return Response(status=308, headers={'Location': prefix + '/' + ('?' + query if query else '')})(environ, start_response)
        if not path.startswith(prefix + '/'):
            return Response('Unexpected request outside mount', status=404)(environ, start_response)
        environ['PATH_INFO'] = path[len(prefix):]
    return app(environ, start_response)


run_simple('127.0.0.1', int(os.environ['MARE_EDITOR_TEST_PORT']), proxy, use_reloader=False)
