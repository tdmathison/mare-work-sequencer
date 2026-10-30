"""Bounded Unix-socket RPC to the separately deployed rootless worker supervisor."""

import http.client
import json
import os
import socket


class Unavailable(RuntimeError):
    pass


class UnixHTTP(http.client.HTTPConnection):
    def __init__(self, path):
        super().__init__("localhost", timeout=30)
        self.path = path

    def connect(self):
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.settimeout(self.timeout)
        self.sock.connect(self.path)


def call(method, path, value=None):
    location = os.environ.get("MARE_PLUGIN_WORKER_SOCKET")
    if not location:
        raise Unavailable("Isolated plugin runtime is not configured.")
    connection = UnixHTTP(location)
    try:
        body = json.dumps(value).encode() if value is not None else None
        connection.request(method, path, body, {"Content-Type": "application/json"})
        response = connection.getresponse()
        raw = response.read(2 * 1024 * 1024 + 1)
        if len(raw) > 2 * 1024 * 1024:
            raise Unavailable("Worker response exceeded output limits.")
        result = json.loads(raw)
        if response.status >= 400:
            raise Unavailable(result.get("error", "Worker rejected request."))
        return result
    except (OSError, ValueError, http.client.HTTPException) as error:
        raise Unavailable("Isolated worker is unavailable.") from error
    finally:
        connection.close()
