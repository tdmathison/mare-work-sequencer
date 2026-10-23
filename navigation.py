"""Application navigation identifiers derived from Flask's matched routes."""

from flask import request
from dashboard_directory import DASHBOARDS


SECTION_ENDPOINTS = {
    "board": {"dashboard", "create_case_page", "new_case", "save_board_sort"},
    "search": {"mip_search", "mip_search_results", "mip_search_finding"},
    "dashboards": {"dashboards_directory"} | {item.endpoint for item in DASHBOARDS if item.endpoint},
    "families": {"families_workspace", "families_edit", "families_delete", "families_osint_edit", "families_osint_delete", "families_reports_upload", "families_reports_download", "families_reports_edit", "families_reports_delete"},
    "tags": {"tags_manager", "tag_detail", "tags_search", "tags_create", "tag_manage"},
    "tools": {
        "tools_workspace",
        "tools_cyberchef",
        "tools_text_manipulation",
        "tools_text_process",
        "tools_yara", "yara_state", "yara_jobs", "yara_job", "yara_cancel", "yara_draft", "yara_download",
        "tools_snort", "snort_state", "snort_jobs", "snort_job", "snort_cancel", "snort_draft", "snort_download",
    },
    "users": {"users", "user_action"},
    "audit": {"audit_view", "audit_export_csv", "audit_export_all_zip"},
    "settings": {
        "account",
        "save_autosave_settings",
        "save_board_view",
        "save_sample_archive_password",
        "upload_template",
        "download_template",
        "delete_template",
        "database_backup",
    },
    "api": {"api_page", "create_account_api_token", "revoke_account_api_token"},
    "import_export": {"backup_workspace_page", "backup_jobs_create", "backup_jobs_status", "backup_jobs_download", "backup_jobs_preview", "backup_jobs_apply", "import_export_page", "backup_export", "backup_import", "sync_import_review", "sync_import_apply", "sync_api_review", "sync_api_apply"},
}
SETTINGS_CATEGORY_ENDPOINTS = {
    'general': set(SECTION_ENDPOINTS['settings']) | {'settings_home'},
    'users': set(SECTION_ENDPOINTS['users']),
    'audit': set(SECTION_ENDPOINTS['audit']),
    'import-export': set(SECTION_ENDPOINTS['import_export']),
}
for category in ('users','audit','import_export'):
    SECTION_ENDPOINTS['settings'].update(SECTION_ENDPOINTS.pop(category))
SECTION_ENDPOINTS['settings'].add('settings_home')
ENDPOINT_SECTION = {
    endpoint: section
    for section, endpoints in SECTION_ENDPOINTS.items()
    for endpoint in endpoints
}


def navigation_section(endpoint, view_args=None):
    # Case workspace utilities share this route parameter, including tag actions.
    if endpoint and "cid" in (view_args or {}):
        return "board"
    return ENDPOINT_SECTION.get(endpoint)


def register_navigation(app):
    @app.context_processor
    def application_navigation():
        return {
            "active_navigation": navigation_section(request.endpoint, request.view_args)
        }
