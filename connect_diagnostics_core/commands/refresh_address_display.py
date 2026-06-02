from __future__ import annotations

import click
import frappe
from frappe.commands import pass_context
from frappe.utils.fixtures import sync_fixtures

from connect_diagnostics_core.utils.address import (
    refresh_address_display_values,
    validate_refresh_address_display_selectors,
)


@click.command("refresh-address-display")
@click.option("--doctype", "doctypes", multiple=True, help="Limit refresh to this DocType. Repeatable.")
@click.option("--name", "names", multiple=True, help="Limit refresh to this document name. Repeatable.")
@click.option("--address", "addresses", multiple=True, help="Limit refresh to this Address. Repeatable.")
@click.option("--all", "refresh_all", is_flag=True, help="Refresh address snapshots across all DocTypes.")
@click.option(
    "--include-party-primary", is_flag=True, help="Also refresh Customer and Supplier primary addresses."
)
@click.option(
    "--sync-fixtures", is_flag=True, help="Import app fixtures before refreshing. Requires --apply."
)
@click.option("--apply", is_flag=True, help="Write changes. Without this flag the command only previews.")
@pass_context
def refresh_address_display(
    context,
    doctypes: tuple[str, ...],
    names: tuple[str, ...],
    addresses: tuple[str, ...],
    refresh_all: bool,
    include_party_primary: bool,
    sync_fixtures: bool,
    apply: bool,
) -> None:
    """Refresh saved address display snapshots using the current Address Template."""

    if sync_fixtures and not apply:
        raise click.UsageError("--sync-fixtures requires --apply.")
    try:
        validate_refresh_address_display_selectors(
            all=refresh_all,
            doctypes=doctypes,
            names=names,
            addresses=addresses,
        )
    except ValueError as error:
        raise click.UsageError(str(error)) from error
    if not context.sites:
        raise frappe.SiteNotSpecifiedError

    for site in context.sites:
        frappe.init(site=site)
        try:
            frappe.connect()
            if sync_fixtures:
                sync_fixtures_for_app()

            result = refresh_address_display_values(
                all=refresh_all,
                doctypes=doctypes,
                names=names,
                addresses=addresses,
                include_party_primary=include_party_primary,
                apply=apply,
            )

            if apply:
                # This standalone bench command owns the transaction and commits once per successful site.
                frappe.db.commit()  # nosemgrep
            click.echo(
                f"{site}: {'applied' if apply else 'preview'} "
                f"changed={result.changed} unchanged={result.unchanged} dangling={result.dangling}"
            )
        except Exception:
            if frappe.db:
                frappe.db.rollback()
            raise
        finally:
            frappe.destroy()


def sync_fixtures_for_app() -> None:
    sync_fixtures("connect_diagnostics_core")
