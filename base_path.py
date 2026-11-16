"""URL mount configuration; internal Flask routes always remain unprefixed."""
import ipaddress
import os
import re

from flask import current_app, has_request_context, request
from werkzeug.middleware.proxy_fix import ProxyFix


def normalize_base_path(value):
    if value in ('', '/'):
        return ''
    if not re.fullmatch(r'/[A-Za-z0-9_~.-]+(?:/[A-Za-z0-9_~.-]+)*/?', value):
        raise ValueError('MWS_BASE_PATH must be an absolute URL path without escapes, query or fragment')
    value = value.rstrip('/')
    if any(part in ('.', '..') for part in value.split('/')):
        raise ValueError('MWS_BASE_PATH cannot contain path traversal')
    return value


def app_url(value, *, internal=False):
    """Mount an internal URL once; leave external and relative references intact."""
    prefix = request.script_root if has_request_context() else current_app.config['APPLICATION_ROOT'].rstrip('/')
    if not isinstance(value, str) or not value.startswith('/') or value.startswith('//'):
        return value
    if not internal and prefix and (value == prefix or value.startswith(prefix + '/') or value.startswith(prefix + '?') or value.startswith(prefix + '#')):
        return value
    return prefix + value


class MountMiddleware:
    """Accept stripped paths. Only configured immediate proxies may set HTTPS/IP."""
    def __init__(self, app, prefix, trusted_proxies=()):
        self.app, self.prefix = app, prefix
        self.trusted = tuple(ipaddress.ip_network(ip) for ip in trusted_proxies)
        self.proxy_app = ProxyFix(app, x_for=1, x_proto=1, x_host=0, x_port=0, x_prefix=1)

    def __call__(self, environ, start_response):
        try:
            trusted = any(ipaddress.ip_address(environ.get('REMOTE_ADDR', '')) in network for network in self.trusted)
        except ValueError:
            trusted = False
        # The startup setting is authoritative, even for trusted proxies.
        environ['SCRIPT_NAME'] = self.prefix or environ.get('SCRIPT_NAME', '')
        if trusted:
            environ['HTTP_X_FORWARDED_PREFIX'] = environ['SCRIPT_NAME']
            return self.proxy_app(environ, start_response)
        for name in ('HTTP_X_FORWARDED_PREFIX', 'HTTP_X_FORWARDED_FOR', 'HTTP_X_FORWARDED_PROTO', 'HTTP_X_FORWARDED_HOST', 'HTTP_X_FORWARDED_PORT'):
            environ.pop(name, None)
        return self.app(environ, start_response)


def configure_base_path(app):
    prefix = normalize_base_path(os.environ.get('MWS_BASE_PATH', ''))
    trusted = [value.strip() for value in os.environ.get('MWS_TRUSTED_PROXIES', '').split(',') if value.strip()]
    app.config.update(APPLICATION_ROOT=prefix or '/', SESSION_COOKIE_PATH=prefix or '/', SESSION_COOKIE_NAME='mws_session')
    app.jinja_env.globals['app_url'] = app_url
    app.wsgi_app = MountMiddleware(app.wsgi_app, prefix, trusted)
