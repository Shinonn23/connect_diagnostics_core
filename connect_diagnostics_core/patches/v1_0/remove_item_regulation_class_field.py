# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Remove the now-unused ``regulation_class`` Custom Field from Item.

No report, print format, or hook consumes it, and its only observed data (MEDICAL
DEVICE / CONSUMER HEALTH / GIMMICK) is a coarser duplicate of the Regulatory module's
own ``is_medical_device`` / ``medical_device_category`` / ``regulatory_registration_requirement``
fields. Must run before remove_regulation_class_doctype so the Link's target DocType is
only deleted once nothing on Item still points at it. Idempotent.
"""

from __future__ import annotations

import frappe

from connect_diagnostics_core.patches.v1_0.strip_custom_prefix_from_field_names import _drop_old


def execute() -> None:
    _drop_old("Item", "regulation_class")
    frappe.db.commit()
