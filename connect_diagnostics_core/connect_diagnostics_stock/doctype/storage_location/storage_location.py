# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from frappe.model.document import Document


class StorageLocation(Document):
    # begin: auto-generated types
    # This code is auto-generated. Do not modify anything in this block.

    from typing import TYPE_CHECKING

    if TYPE_CHECKING:
        from frappe.types import DF

        location_code: DF.Data
        location_name: DF.Data | None
        warehouse: DF.Link | None
        zone: DF.Data | None
    # end: auto-generated types
    pass
