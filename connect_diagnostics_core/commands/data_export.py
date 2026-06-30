# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

from pathlib import Path

import click
import frappe
from frappe.commands import pass_context

from connect_diagnostics_core.data_export.drive import authorize, export_to_drive
from connect_diagnostics_core.data_export.exporter import (
    FrappeClient,
    build_module_workbook,
    list_target_doctypes,
    load_catalog,
)


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
@click.option("--excel", is_flag=True, help="Upload Excel .xlsx files instead of native Google Sheets.")
@click.option("--url", "remote_url", default=None, help="Remote Frappe site URL (export via HTTP API).")
@click.option("--api-key", "api_key", default=None, help="Frappe API key for the remote site.")
@click.option("--api-secret", "api_secret", default=None, help="Frappe API secret for the remote site.")
@click.option(
    "--local", "save_local", is_flag=True, help="Save .xlsx files locally instead of uploading to Drive."
)
@click.option(
    "--output-dir",
    default=".",
    show_default=True,
    help="Directory to write files when --local is used.",
)
@click.option(
    "--catalog",
    "catalog_path",
    default=None,
    help="Path to DocType_Categorized.xlsx. When provided, DocTypes are filtered and categorized via the catalog.",
)
@pass_context
def run(
    context,
    modules: tuple[str, ...],
    folder_id: str | None,
    token_path: str | None,
    excel: bool,
    remote_url: str | None,
    api_key: str | None,
    api_secret: str | None,
    save_local: bool,
    output_dir: str,
    catalog_path: str | None,
) -> None:
    """Export every DocType to Google Drive, one file per module."""
    if not context.sites:
        raise frappe.SiteNotSpecifiedError

    if remote_url:
        if not api_key or not api_secret:
            raise click.UsageError("--api-key and --api-secret are required when --url is set.")
        client: FrappeClient | None = FrappeClient(remote_url, api_key, api_secret)
    else:
        client = None

    catalog = load_catalog(Path(catalog_path)) if catalog_path else None

    for site in context.sites:
        frappe.init(site=site)
        try:
            if client is None:
                frappe.connect()

            if save_local:
                dest = Path(output_dir)
                dest.mkdir(parents=True, exist_ok=True)
                grouped = list_target_doctypes(modules, client=client, catalog=catalog)
                saved = 0
                for module, module_doctypes in grouped.items():
                    content = build_module_workbook(module_doctypes, client=client)
                    filepath = dest / f"{module}.xlsx"
                    filepath.write_bytes(content)
                    click.echo(f"{site}: saved '{module}' ({len(module_doctypes)} doctypes) -> {filepath}")
                    saved += 1
                click.echo(f"{site}: saved {saved} workbook(s) to {dest.resolve()}")
            else:
                summary = export_to_drive(
                    modules, folder_id, token_path, excel=excel, client=client, catalog=catalog
                )
                for item in summary:
                    click.echo(
                        f"{site}: {item['action']} '{item['module']}' "
                        f"({item['doctypes']} doctypes) -> {item['file_id']}"
                    )
                kind = "Excel file" if excel else "module spreadsheet"
                click.echo(f"{site}: uploaded {len(summary)} {kind}(s)")
        finally:
            frappe.destroy()
