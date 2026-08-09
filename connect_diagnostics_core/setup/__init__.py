"""Programmatic custom field / property setter setup (erpnext_thailand style).

Replaces the old custom/*.json export-customization fixtures. Applied on both
after_install and after_migrate (both are idempotent).
"""

from frappe.custom.doctype.custom_field.custom_field import create_custom_fields
from frappe.custom.doctype.property_setter.property_setter import make_property_setter

from connect_diagnostics_core.setup import (
    account,
    contact,
    currency_exchange,
    customer,
    customer_onboarding,
    delivery_note,
    employee,
    item,
    item_barcode,
    item_default,
    item_group,
    journal_entry_account,
    packed_item,
    payment_approval,
    payroll,
    procure_to_pay,
    purchase_invoice,
    purchase_invoice_item,
    purchase_taxes_and_charges,
    quotation,
    regulatory,
    regulatory_transactions,
    sales_invoice,
    sales_invoice_item,
    sales_order_item,
    sales_requirements,
    sales_taxes_and_charges,
    supplier,
    uom,
    workspace,
)
from connect_diagnostics_core.setup.print_format import remove_non_app_print_formats

_MODULES = (
    account,
    contact,
    currency_exchange,
    customer,
    customer_onboarding,
    delivery_note,
    employee,
    item,
    item_barcode,
    item_default,
    item_group,
    journal_entry_account,
    packed_item,
    payment_approval,
    procure_to_pay,
    regulatory,
    regulatory_transactions,
    purchase_invoice,
    purchase_invoice_item,
    purchase_taxes_and_charges,
    quotation,
    sales_invoice,
    sales_invoice_item,
    sales_order_item,
    sales_requirements,
    sales_taxes_and_charges,
    supplier,
    uom,
)


def apply_all() -> None:
    for module in _MODULES:
        custom_fields = getattr(module, "CUSTOM_FIELDS", None)
        if custom_fields:
            create_custom_fields(custom_fields, ignore_validate=True)
    for module in _MODULES:
        for doctype, setters in getattr(module, "PROPERTY_SETTERS", {}).items():
            for fieldname, prop, value, property_type in setters:
                make_property_setter(
                    doctype,
                    fieldname,
                    prop,
                    value,
                    property_type,
                    for_doctype=fieldname is None,
                    validate_fields_for_doctype=False,
                )
    procure_to_pay.ensure_configuration()
    payment_approval.ensure_configuration()
    payroll.ensure_configuration()
    customer_onboarding.ensure_configuration()
    sales_requirements.ensure_configuration()
    regulatory.ensure_configuration()
    workspace.ensure_workspace_navigation()


def after_install() -> None:
    apply_all()
    _ensure_default_print_configuration_template()


def after_sync() -> None:
    remove_non_app_print_formats()


def after_migrate() -> None:
    apply_all()
    _ensure_default_print_configuration_template()
    remove_non_app_print_formats()


def _ensure_default_print_configuration_template() -> None:
    """Create the reusable Templates after the standard DocType has synchronized."""
    from connect_diagnostics_core.setup.print_configuration_template import (
        ensure_default_template,
        ensure_policy_templates,
    )

    ensure_default_template()
    ensure_policy_templates()
