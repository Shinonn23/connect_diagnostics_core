# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Authorize Google Drive and upload module exports to Google Drive.

``authorize`` runs the localhost OAuth flow once and saves the token to a
``token.json`` file (refreshed automatically on later runs). ``export_to_drive``
then builds each module workbook in memory and uploads it as either a native
Google Sheet or an Excel file, replacing the file of the same name in the folder
when one already exists.
"""

from __future__ import annotations

import os
from io import BytesIO
from typing import Any, TypedDict, cast

import frappe
from frappe import _

from connect_diagnostics_core.data_export.exporter import (
    FrappeClient,
    build_module_workbook,
    list_target_doctypes,
)

# drive.file lets the app upload and later replace only the files it creates.
SCOPES = ["https://www.googleapis.com/auth/drive.file"]

XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
GOOGLE_SHEET_MIME = "application/vnd.google-apps.spreadsheet"

DEFAULT_TOKEN_FILENAME = "cd_data_export_token.json"
DEFAULT_CLIENT_SECRET_FILENAME = "client_secret.json"
CONFIG_FOLDER = "cd_data_export_drive_folder_id"


class DriveExportSummary(TypedDict):
    module: str
    file_id: str
    action: str
    doctypes: int


def _token_path(token_path: str | None = None) -> str:
    """Return the token.json path, defaulting to the site's private files."""
    return token_path or frappe.get_site_path("private", "files", DEFAULT_TOKEN_FILENAME)


def _client_secret_path(client_secret_path: str | None = None) -> str:
    """Return the client_secret path, defaulting to the site's private files."""
    return client_secret_path or frappe.get_site_path("private", "files", DEFAULT_CLIENT_SECRET_FILENAME)


def get_drive_credentials(
    client_secret_path: str | None = None,
    token_path: str | None = None,
    port: int = 0,
    allow_login: bool = False,
) -> Any:
    """Return valid Drive credentials, logging in via browser when allowed.

    Loads ``token.json`` when present and refreshes it when expired. When no
    usable token exists and ``allow_login`` is set, runs the localhost consent
    flow using the OAuth client secret and writes the new ``token.json``. With
    ``allow_login`` off (the export path) a missing token raises instead.
    """
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow

    path = _token_path(token_path)
    credentials = None
    if os.path.exists(path):
        credentials = Credentials.from_authorized_user_file(path, SCOPES)

    if credentials and credentials.valid:
        return credentials

    if credentials and credentials.expired and credentials.refresh_token:
        credentials.refresh(Request())
    elif allow_login:
        secret = _client_secret_path(client_secret_path)
        if not os.path.exists(secret):
            frappe.throw(
                _(
                    "OAuth client secret not found at {0}. Download it from Google Cloud "
                    "Console and place it there, or pass --client-secret <path>."
                ).format(secret)
            )
        flow = InstalledAppFlow.from_client_secrets_file(secret, SCOPES)
        # open_browser=False: headless/WSL has no browser; just print the consent URL.
        credentials = flow.run_local_server(port=port, open_browser=False)
    else:
        frappe.throw(_("Google Drive is not authorized. Run 'cd-data-export login' first."))

    assert credentials is not None  # every branch above either set it or raised
    with open(path, "w") as token_file:  # nosemgrep: frappe-security-file-traversal
        token_file.write(credentials.to_json())
    return credentials


def authorize(
    client_secret_path: str | None = None,
    folder_id: str | None = None,
    token_path: str | None = None,
    port: int = 0,
) -> dict[str, object]:
    """Run the localhost login and save the token (and optional folder id).

    ``client_secret_path`` defaults to ``private/files/client_secret.json``.
    """
    from frappe.installer import update_site_config

    get_drive_credentials(
        client_secret_path=client_secret_path, token_path=token_path, port=port, allow_login=True
    )
    if folder_id:
        update_site_config(CONFIG_FOLDER, folder_id)

    path = _token_path(token_path)
    return {
        "data": {"token_path": path, "folder_id": folder_id or frappe.conf.get(CONFIG_FOLDER)},
        "message": f"Google Drive authorized; token saved to {path}.",
    }


def _drive_service(token_path: str | None = None) -> Any:
    """Return an authorized Google Drive v3 service."""
    from googleapiclient.discovery import build

    credentials = get_drive_credentials(token_path=token_path)
    return build("drive", "v3", credentials=credentials, cache_discovery=False)


def _find_existing_sheet(service: Any, folder_id: str, name: str) -> str | None:
    """Return the id of a Google Sheet named ``name`` in ``folder_id``, if any."""
    return _find_existing_file(service, folder_id, name, GOOGLE_SHEET_MIME)


def _find_existing_file(service: Any, folder_id: str, name: str, mime_type: str) -> str | None:
    """Return the id of a Drive file named ``name`` in ``folder_id``, if any."""
    escaped = name.replace("\\", "\\\\").replace("'", "\\'")
    query = (
        f"name = '{escaped}' and '{folder_id}' in parents and mimeType = '{mime_type}' and trashed = false"
    )
    response = service.files().list(q=query, spaces="drive", fields="files(id, name)", pageSize=1).execute()
    files = response.get("files", [])
    return files[0]["id"] if files else None


def upload_module_as_sheet(service: Any, folder_id: str, name: str, xlsx_bytes: bytes) -> tuple[str, str]:
    """Upload ``xlsx_bytes`` as a Google Sheet, replacing one of the same name.

    Returns ``(file_id, action)`` where ``action`` is ``"created"`` or
    ``"updated"``. Uploading xlsx with the Google Sheet target mime type makes
    Drive convert the workbook into a native spreadsheet (one tab per sheet).
    """
    from googleapiclient.http import MediaIoBaseUpload

    media = MediaIoBaseUpload(BytesIO(xlsx_bytes), mimetype=XLSX_MIME, resumable=True)
    existing_id = _find_existing_sheet(service, folder_id, name)
    if existing_id:
        service.files().update(fileId=existing_id, media_body=media).execute()
        return existing_id, "updated"

    metadata = {"name": name, "mimeType": GOOGLE_SHEET_MIME, "parents": [folder_id]}
    created = service.files().create(body=metadata, media_body=media, fields="id").execute()
    return created["id"], "created"


def upload_module_as_excel(service: Any, folder_id: str, name: str, xlsx_bytes: bytes) -> tuple[str, str]:
    """Upload ``xlsx_bytes`` as an Excel file, replacing one of the same name."""
    from googleapiclient.http import MediaIoBaseUpload

    filename = f"{name}.xlsx"
    media = MediaIoBaseUpload(BytesIO(xlsx_bytes), mimetype=XLSX_MIME, resumable=True)
    existing_id = _find_existing_file(service, folder_id, filename, XLSX_MIME)
    if existing_id:
        service.files().update(fileId=existing_id, media_body=media).execute()
        return existing_id, "updated"

    metadata = {"name": filename, "mimeType": XLSX_MIME, "parents": [folder_id]}
    created = service.files().create(body=metadata, media_body=media, fields="id").execute()
    return created["id"], "created"


def export_to_drive(
    modules: tuple[str, ...] = (),
    folder_id: str | None = None,
    token_path: str | None = None,
    *,
    excel: bool = False,
    client: FrappeClient | None = None,
    catalog: dict[str, str] | None = None,
) -> list[DriveExportSummary]:
    """Export every DocType to Google Drive, one file per module.

    Each module is uploaded into the Drive folder (``folder_id`` or the one saved
    in site config), replacing the file of the same name when it exists.
    Pass ``client`` to fetch data from a remote Frappe site via HTTP instead of
    the local database. Pass ``catalog`` (loaded via ``load_catalog()``) to filter
    and categorize DocTypes using a ``DocType_Categorized.xlsx`` catalog file.
    """
    folder = cast(str | None, folder_id or frappe.conf.get(CONFIG_FOLDER))
    if not folder:
        frappe.throw(_("No Google Drive folder configured. Pass --folder or run login with --folder first."))
    folder = cast(str, folder)

    grouped = list_target_doctypes(modules, client=client, catalog=catalog)
    service = _drive_service(token_path)

    summary: list[DriveExportSummary] = []
    for module, module_doctypes in grouped.items():
        content = build_module_workbook(module_doctypes, client=client)
        if excel:
            file_id, action = upload_module_as_excel(service, folder, module, content)
            target = "Excel file"
        else:
            file_id, action = upload_module_as_sheet(service, folder, module, content)
            target = "Google Sheet"
        summary.append(
            {
                "module": module,
                "file_id": file_id,
                "action": action,
                "doctypes": len(module_doctypes),
            }
        )
        frappe.logger(__name__).info(f"Data export {action} {target} for module {module!r} ({file_id})")

    return summary
