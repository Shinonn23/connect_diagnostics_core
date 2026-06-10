# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from frappe.model.document import Document


class DepartmentUserPermissionUser(Document):
    # begin: auto-generated types
    # This code is auto-generated. Do not modify anything in this block.

    from typing import TYPE_CHECKING

    if TYPE_CHECKING:
        from frappe.types import DF

        apply: DF.Check
        employee: DF.Link | None
        employee_name: DF.Data | None
        parent: DF.Data
        parentfield: DF.Data
        parenttype: DF.Data
        user: DF.Link | None
    # end: auto-generated types
    pass
