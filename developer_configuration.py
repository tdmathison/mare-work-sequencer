"""Typed plugin configuration; AES-encrypted secrets use the site's existing key."""

import hashlib
import io
import json
import math
import pyzipper
from flask import abort, g, request
from authorization import has_permission
import plugin_store as store


def secret_password(site_key):
    return hashlib.pbkdf2_hmac(
        "sha256", str(site_key).encode(), b"mws-plugin-configuration-v1", 200000
    )


def seal(values, site_key):
    target = io.BytesIO()
    with pyzipper.AESZipFile(
        target, "w", compression=pyzipper.ZIP_DEFLATED, encryption=pyzipper.WZ_AES
    ) as archive:
        archive.setpassword(secret_password(site_key))
        archive.setencryption(pyzipper.WZ_AES, nbits=256)
        archive.writestr("configuration.json", store.dumps(values))
    return target.getvalue()


def unseal(raw, site_key):
    if not raw:
        return {}
    with pyzipper.AESZipFile(io.BytesIO(raw)) as archive:
        archive.setpassword(secret_password(site_key))
        return json.loads(archive.read("configuration.json"))


def validate_value(field, value):
    kind = field["type"]
    valid = (
        (isinstance(value, str) and len(value) <= 8000)
        if kind == "string"
        else (
            (type(value) in (int, float) and math.isfinite(value))
            if kind == "number"
            else type(value) is bool
        )
    )
    if not valid or ("enum" in field and value not in field["enum"]):
        raise ValueError(
            "Configuration value does not match its declared type/options."
        )
    return value


def resolved(row, value, site_key, require=False):
    fields = value.get("configuration", {})
    plain = json.loads(row["configuration"])
    secret = unseal(row["secret_box"], site_key)
    public = {}
    private = {}
    for key, field in fields.items():
        values = secret if field.get("secret") else plain
        if key in values:
            result = validate_value(field, values[key])
        elif "default" in field:
            result = validate_value(field, field["default"])
        elif require and field.get("required"):
            raise ValueError("Required configuration field is missing: " + key)
        else:
            continue
        (private if field.get("secret") else public)[key] = result
    return public, private


def register_configuration(app, db, audit):
    @app.route(
        "/plugins/registry/<pid>/configuration", methods=["GET", "POST"]
    )
    def developer_configuration(pid):
        if not has_permission(g.user, "plugins:read", db()) or not has_permission(
            g.user, "plugins:configure", db()
        ):
            abort(403)
        row = (
            db()
            .execute(
                "SELECT * FROM developer_plugins WHERE id=? AND owner_uuid=? AND deleted=0",
                (pid, g.user["user_uuid"]),
            )
            .fetchone()
        )
        if not row:
            abort(404)
        checked = store.static_validation(store.files(db(), pid))
        if not checked["valid"]:
            abort(409, description="Correct the plugin manifest before configuring it.")
        value = checked["manifest"]
        fields = value.get("configuration", {})
        try:
            public, private = resolved(row, value, app.config["SECRET_KEY"])
            if request.method == "POST":
                data = json.loads(request.form.get("payload", "{}"))
                if not isinstance(data, dict) or set(data) - {
                    "values",
                    "secrets",
                    "clear_secrets",
                }:
                    raise ValueError("Invalid configuration payload.")
                for name, collection in (("values", public), ("secrets", private)):
                    supplied = data.get(name, {})
                    if not isinstance(supplied, dict):
                        raise ValueError("Configuration values must be an object.")
                    for key, item in supplied.items():
                        if key not in fields or bool(fields[key].get("secret")) != (
                            name == "secrets"
                        ):
                            raise ValueError(
                                "Unknown configuration field or wrong secret classification."
                            )
                        collection[key] = validate_value(fields[key], item)
                clear = data.get("clear_secrets", [])
                if not isinstance(clear, list) or any(
                    not isinstance(k, str)
                    or k not in fields
                    or not fields[k].get("secret")
                    for k in clear
                ):
                    raise ValueError("Invalid secret removals.")
                for key in clear:
                    private.pop(key, None)
                encrypted = seal(private, app.config["SECRET_KEY"])
                with db():
                    db().execute(
                        "UPDATE developer_plugins SET configuration=?,secret_box=? WHERE id=?",
                        (store.dumps(public), encrypted, pid),
                    )
                audit(
                    "Updated plugin configuration " + pid
                )  # Values deliberately excluded.
        except (ValueError, TypeError, KeyError, RuntimeError) as error:
            abort(400, description=str(error))
        return {
            "schema": fields,
            "values": public,
            "configured_secrets": sorted(private),
        }
