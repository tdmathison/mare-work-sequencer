"""Shared directory metadata; rendering never loads dashboard datasets."""
from dataclasses import dataclass
from flask import g, render_template, request, url_for
from authorization import has_permission


@dataclass(frozen=True)
class Dashboard:
    identifier: str
    name: str
    description: str
    endpoint: str | None
    visibility: str
    availability: str
    permission: str | None
    order: int


DASHBOARDS = (
    Dashboard('metrics', 'Metrics', 'Case totals, lifecycle trends, workload, and completion metrics.', 'metrics', 'private', 'implemented', 'metrics:read', 10),
    Dashboard('cases', 'Cases', 'Completed work, ongoing investigations, and recent deliveries.', 'cases_dashboard', 'public', 'implemented', None, 20),
    Dashboard('families', 'Malware Families', 'Tracked families, research coverage, and investigations in progress.', 'family_dashboard', 'public', 'implemented', None, 30),
    Dashboard('actors', 'Threat Actors', 'Threat actor research and profile coverage.', None, 'public', 'coming later', None, 40),
)


def safe_dashboard_return(value):
    # An exact allowlist also rejects schemes, network paths, encoded redirects,
    # backslashes and unexpected query parameters. Expand with registered routes.
    return value if value in {url_for(item.endpoint) for item in DASHBOARDS
                             if item.endpoint and item.visibility == 'private'} else None


def register_dashboard_directory(app, db):
    @app.get('/dashboards')
    def dashboards_directory():
        return render_template('dashboard_directory.html')

    @app.context_processor
    def dashboard_navigation():
        entries = []
        menu = [dict(label='All dashboards', url=url_for('dashboards_directory'),
                     active=request.endpoint == 'dashboards_directory', divider_after=True)]
        for item in sorted(DASHBOARDS, key=lambda item: item.order):
            implemented = item.availability == 'implemented'
            allowed = not item.permission or has_permission(g.user, item.permission, db())
            destination = url_for(item.endpoint) if implemented else None
            restricted = bool(implemented and g.user and not allowed)
            if implemented and not allowed:
                destination = None if restricted else url_for('login', next=destination)
            entry = dict(identifier=item.identifier, name=item.name, description=item.description,
                         visibility=item.visibility, availability=item.availability, url=destination,
                         restricted=restricted, active=bool(item.endpoint and request.endpoint == item.endpoint))
            entries.append(entry)
            label = f'{item.name} — {item.visibility.title()}' if implemented else f'{item.name} — Coming later'
            if restricted:
                label += ' · Access restricted'
            menu.append(dict(label=label, url=destination, active=entry['active']))
        return dict(dashboard_entries=entries, dashboard_navigation=menu)
