import frappe
from frappe.contacts.doctype.address.address import get_default_address, render_address
from frappe.utils.fixtures import sync_fixtures

ADDRESS_DISPLAY_FIELDS = {
    "address": "address_display",
    "billing_address": "billing_address_display",
    "company_address": "company_address_display",
    "customer_address": "address_display",
    "dispatch_address": "dispatch_address_display",
    "dispatch_address_name": "dispatch_address",
    "shipping_address": "shipping_address_display",
    "shipping_address_name": "shipping_address",
    "source_warehouse_address": "source_address_display",
    "supplier_address": "address_display",
    "target_warehouse_address": "target_address_display",
}


def execute():
    # Fixtures normally sync after patches. Import this app's updated Address Template
    # first so the refreshed snapshots use the new template during the same migration.
    sync_fixtures("connect_diagnostics_core")
    refresh_address_display_values()


def refresh_address_display_values():
    rendered_addresses = {
        address: render_address(address, check_permissions=False)
        for address in frappe.get_all("Address", pluck="name")
    }

    _refresh_party_primary_addresses(rendered_addresses)

    for doctype in frappe.get_all(
        "DocType",
        filters={"issingle": 0, "istable": 0},
        pluck="name",
        order_by=None,
    ):
        meta = frappe.get_meta(doctype)
        # pyrefly: ignore [missing-attribute]
        if meta.is_virtual:
            continue

        for address_field in meta.get_link_fields():
            if address_field.options != "Address":
                continue

            display_field = _get_display_field(meta, address_field.fieldname)
            if display_field:
                _refresh_linked_address_display(
                    doctype,
                    address_field.fieldname,
                    display_field,
                    rendered_addresses,
                )


def _refresh_party_primary_addresses(rendered_addresses):
    for doctype in ("Customer", "Supplier"):
        for party in frappe.get_all(doctype, pluck="name", order_by=None):
            address = get_default_address(doctype, party)
            frappe.db.set_value(
                doctype,
                party,
                "primary_address",
                rendered_addresses.get(address),
                update_modified=False,
            )


def _get_display_field(meta, address_field):
    candidates = [ADDRESS_DISPLAY_FIELDS.get(address_field)]

    if address_field.endswith("_name"):
        candidates.append(address_field.removesuffix("_name"))
        candidates.append(f"{address_field.removesuffix('_name')}_display")

    candidates.append(f"{address_field}_display")

    for candidate in candidates:
        if candidate and meta.get_field(candidate):
            return candidate


def _refresh_linked_address_display(doctype, address_field, display_field, rendered_addresses):
    used_addresses = frappe.get_all(
        doctype,
        filters={address_field: ("is", "set")},
        pluck=address_field,
        distinct=True,
        order_by=None,
    )

    for address in used_addresses:
        if address in rendered_addresses:
            frappe.db.set_value(
                doctype,
                {address_field: address},
                display_field,
                rendered_addresses[address],
                update_modified=False,
            )
