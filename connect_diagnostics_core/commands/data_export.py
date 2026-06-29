# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

import click
import frappe
from frappe.commands import pass_context

from connect_diagnostics_core.data_export.drive import authorize, export_to_drive


@click.group("cd-data-export")
def cd_data_export() -> None:
    """Export ERPNext data to Google Sheets in Google Drive."""


@cd_data_export.command("login")
@click.option(
    "--client-secret",
    default=None,
    help="Path to the Google OAuth client secret JSON. "
    "Defaults to the site's private/files/client_secret.json.",
)
@click.option(
    "--folder",
    "folder_id",
    default=None,
    help="Google Drive folder ID to upload into. Saved for later runs.",
)
@click.option(
    "--token",
    "token_path",
    default=None,
    help="Where to save token.json. Defaults to the site's private files.",
)
@click.option(
    "--port",
    default=0,
    show_default=True,
    help="Local callback port for the OAuth redirect. 0 picks a free port.",
)
@pass_context
def login(context, client_secret: str, folder_id: str | None, token_path: str | None, port: int) -> None:
    """Authorize Google Drive on localhost and save token.json."""
    if not context.sites:
        raise frappe.SiteNotSpecifiedError

    site = context.sites[0]
    frappe.init(site=site)
    try:
        result = authorize(client_secret, folder_id, token_path, port)
        click.echo(f"{site}: {result['message']}")
    finally:
        frappe.destroy()


@cd_data_export.command("run")
@click.option(
    "--module",
    "modules",
    multiple=True,
    help="Limit export to this module. Repeatable. Default: all modules.",
)
@click.option(
    "--folder",
    "folder_id",
    default=None,
    help="Google Drive folder ID. Defaults to the one saved at login.",
)
@click.option(
    "--token",
    "token_path",
    default=None,
    help="Path to token.json. Defaults to the site's private files.",
)
@pass_context
def run(context, modules: tuple[str, ...], folder_id: str | None, token_path: str | None) -> None:
    """Export every DocType to Google Sheets, one spreadsheet per module."""
    if not context.sites:
        raise frappe.SiteNotSpecifiedError

    for site in context.sites:
        frappe.init(site=site)
        try:
            frappe.connect()
            summary = export_to_drive(modules, folder_id, token_path)
            for item in summary:
                click.echo(
                    f"{site}: {item['action']} '{item['module']}' "
                    f"({item['doctypes']} doctypes) -> {item['file_id']}"
                )
            click.echo(f"{site}: uploaded {len(summary)} module spreadsheet(s)")
        finally:
            frappe.destroy()
