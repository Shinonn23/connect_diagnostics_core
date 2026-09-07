# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Request-only sidebar settings owned by the Shipment Box Label Print Format."""

from frappe import _

from connect_diagnostics_core.connect_diagnostics_print.print_format.settings import (
    GENERIC_COPIES,
    PrintDocument,
    SidebarExtension,
)

SIZE_OPTIONS = ("75 x 100 mm", "100 x 180 mm")


def shipment_label_sidebar_extension(_docname: str) -> SidebarExtension:
    """Return the selected paper-size control for Shipment Box Label."""
    return SidebarExtension(
        fields=(
            {
                "fieldname": "custom_shipment_label_size",
                "label": _("Shipment Label Size"),
                "fieldtype": "Select",
                "options": "\n".join(SIZE_OPTIONS),
            },
        ),
    )


PRINT_DOCUMENT = PrintDocument(
    key="shipment_box_label",
    label="Shipment Box Label",
    print_formats=("Shipment Box Label",),
    doctypes=("Shipment",),
    language_selectable=False,
    offers_batch_serial=False,
    copies=GENERIC_COPIES,
    defaults={"custom_shipment_label_size": SIZE_OPTIONS[0]},
    extra_fields=("custom_shipment_label_size",),
    include_standard_sidebar_fields=False,
    sidebar_extension=shipment_label_sidebar_extension,
    fallback_to_doctype=False,
)
