from frappe.utils.fixtures import sync_fixtures

from connect_diagnostics_core.utils.address import refresh_address_display_values


def execute():
    # Fixtures normally sync after patches. Import this app's updated Address Template
    # first so the refreshed snapshots use the new template during the same migration.
    sync_fixtures("connect_diagnostics_core")
    refresh_address_display_values(all=True, include_party_primary=True, apply=True)
