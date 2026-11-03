"""Authenticated browser sessions for shared web UI tests."""

import uuid
from app import app
from test_api import make_user


def browser(role="Administrator"):
    uid, _ = make_user("web-" + uuid.uuid4().hex[:8], role=role)
    client = app.test_client()
    with client.session_transaction() as session:
        session.update(uid=uid, version=1, csrf="web-csrf")
    return client, uid
