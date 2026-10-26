"""Anonymous Malware Families wall, sharing the bounded public projection."""
from flask import abort, jsonify, render_template, request
from profile_types import FAMILY
from public_profile_dashboard import FIELDS, INVESTIGATION_SIZE, LIBRARY_SIZE, projection_cte
from public_profile_dashboard import public_profile as public_family
from public_profile_dashboard import snapshot

CTE = projection_cte(FAMILY)


def register_family_dashboard(app, db):
    @app.get("/dashboards/malware-families")
    def family_dashboard():
        return render_template("family_dashboard.html", wall_kind="family")

    @app.get("/dashboards/malware-families/data")
    def family_dashboard_data():
        try:
            page = int(request.args.get("page", "0"))
            library_page = int(request.args.get("library_page", "0"))
            if not 0 <= page <= 1000000 or not 0 <= library_page <= 1000000:
                raise ValueError()
        except ValueError:
            abort(400)
        response = jsonify(
            snapshot(
                db(), page, library_page, timezone_name=app.config["DISPLAY_TIMEZONE"]
            )
        )
        response.headers["Cache-Control"] = "no-store"
        return response
