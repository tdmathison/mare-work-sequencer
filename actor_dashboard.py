"""Anonymous actor library projection; private research stays server-side."""
from flask import abort, jsonify, render_template, request
from profile_types import ACTOR
from public_profile_dashboard import FIELDS, INVESTIGATION_SIZE, LIBRARY_SIZE
from public_profile_dashboard import snapshot as profile_snapshot


def snapshot(connection, page=0, library_page=0, current=None, timezone_name="UTC"):
    return profile_snapshot(connection, page, library_page, current, timezone_name, spec=ACTOR)


def register_actor_dashboard(app, db):
    @app.get('/dashboards/threat-actors')
    def actor_dashboard():
        return render_template('family_dashboard.html', wall_kind='actor')

    @app.get('/dashboards/threat-actors/data')
    def actor_dashboard_data():
        try:
            page = int(request.args.get('page', '0'))
            library_page = int(request.args.get('library_page', '0'))
            if not 0 <= page <= 1000000 or not 0 <= library_page <= 1000000:
                raise ValueError()
        except ValueError:
            abort(400)
        response = jsonify(snapshot(db(), page, library_page,
                                   timezone_name=app.config['DISPLAY_TIMEZONE']))
        # Match the other public walls: fresh bounded snapshots, no stale HTTP
        # cache after edits/deletions/restores, no persistent derived cache.
        response.headers['Cache-Control'] = 'no-store'
        return response
