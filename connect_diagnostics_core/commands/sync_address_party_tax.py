from __future__ import annotations

import click
import frappe
from frappe.commands import pass_context

from connect_diagnostics_core.utils.address import (
    sync_address_party_tax_values,
    validate_sync_address_party_tax_selectors,
)


@click.command("sync-address-party-tax")
@click.option("--address", "addresses", multiple=True, help="Limit sync to this Address. Repeatable.")
@click.option(
    "--party-type",
    type=click.Choice(["Customer", "Supplier"], case_sensitive=True),
    help="Limit sync to linked Customer or Supplier.",
)
@click.option("--party", help="Limit sync to this party name. Requires --party-type.")
@click.option("--overwrite", is_flag=True, help="Overwrite existing Address tax fields.")
@click.option("--apply", is_flag=True, help="Write changes. Without this flag the command only previews.")
@pass_context
def sync_address_party_tax(
    context,
    addresses: tuple[str, ...],
    party_type: str | None,
    party: str | None,
    overwrite: bool,
    apply: bool,
) -> None:
    """Sync Address tax fields from linked Customer/Supplier."""

    try:
        validate_sync_address_party_tax_selectors(addresses=addresses, party_type=party_type, party=party)
    except ValueError as error:
        raise click.UsageError(str(error)) from error
    if not context.sites:
        raise frappe.SiteNotSpecifiedError

    for site in context.sites:
        frappe.init(site=site)
        try:
            frappe.connect()
            result = sync_address_party_tax_values(
                addresses=addresses,
                party_type=party_type,
                party=party,
                overwrite=overwrite,
                apply=apply,
            )

            if apply:
                # This standalone bench command owns the transaction and commits once per successful site.
                frappe.db.commit()  # nosemgrep
            click.echo(
                f"{site}: {'applied' if apply else 'preview'} "
                f"changed={result.changed} unchanged={result.unchanged} "
                f"skipped={result.skipped} conflict={result.conflict}"
            )
        except Exception:
            if frappe.db:
                frappe.db.rollback()
            raise
        finally:
            frappe.destroy()
