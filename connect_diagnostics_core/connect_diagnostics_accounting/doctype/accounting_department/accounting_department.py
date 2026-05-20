# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

from typing import cast

import frappe
from erpnext.accounts.utils import get_autoname_with_number, validate_field_number
from erpnext.setup.doctype.company.company import get_name_with_abbr
from frappe import _
from frappe.utils.nestedset import NestedSet


class AccountingDepartment(NestedSet):
    # begin: auto-generated types
    # This code is auto-generated. Do not modify anything in this block.

    from typing import TYPE_CHECKING

    if TYPE_CHECKING:
        from frappe.types import DF

        company: DF.Link
        department_name: DF.Data
        department_number: DF.Data | None
        disabled: DF.Check
        is_group: DF.Check
        lft: DF.Int
        old_parent: DF.Link | None
        parent_accounting_department: DF.Link
        rgt: DF.Int
    # end: auto-generated types

    nsm_parent_field = "parent_accounting_department"

    def autoname(self) -> None:
        self.name = get_autoname_with_number(self.department_number, self.department_name, self.company)

    def validate(self) -> None:
        self.validate_mandatory()
        self.validate_parent_accounting_department()

    def validate_mandatory(self) -> None:
        if self.department_name != self.company and not self.parent_accounting_department:
            frappe.throw(_("Please enter parent accounting department"))
        elif self.department_name == self.company and self.parent_accounting_department:
            frappe.throw(_("Root cannot have a parent accounting department"))

    def validate_parent_accounting_department(self) -> None:
        if self.parent_accounting_department:
            if not frappe.db.get_value(
                "Accounting Department", self.parent_accounting_department, "is_group"
            ):
                frappe.throw(
                    _(
                        "{0} is not a group node. Please select a group node as parent accounting department"
                    ).format(frappe.bold(self.parent_accounting_department))
                )

    @frappe.whitelist()
    def convert_group_to_ledger(self) -> int:
        if self.check_if_child_exists():
            frappe.throw(_("Cannot convert Accounting Department to ledger as it has child nodes"))
            raise frappe.ValidationError(
                _("Cannot convert Accounting Department to ledger as it has child nodes")
            )
        elif self.check_gle_exists():
            frappe.throw(_("Accounting Department with existing transactions can not be converted to ledger"))
            raise frappe.ValidationError(
                _("Accounting Department with existing transactions can not be converted to ledger")
            )
        else:
            self.is_group = 0
            self.save()
            return 1

    @frappe.whitelist()
    def convert_ledger_to_group(self) -> int:
        if self.check_gle_exists():
            frappe.throw(_("Accounting Department with existing transactions can not be converted to group"))
            raise frappe.ValidationError(
                _("Accounting Department with existing transactions can not be converted to group")
            )
        self.is_group = 1
        self.save()
        return 1

    def check_gle_exists(self) -> str | None:
        if not frappe.db.has_column("GL Entry", "accounting_department"):
            return None
        return cast(str, frappe.db.get_value("GL Entry", {"accounting_department": self.name}))

    def check_if_child_exists(self) -> list:
        return frappe.db.sql(
            """select name from `tabAccounting Department`
            where parent_accounting_department = %s and docstatus != 2""",
            [self.name],
        )

    # pyrefly: ignore [bad-override]
    def before_rename(self, olddn: str, newdn: str, merge: bool = False) -> str:
        new_department = get_name_with_abbr(newdn, self.company)

        super().before_rename(olddn, new_department, merge, "is_group")
        if not merge:
            new_department = get_name_with_number(new_department, self.department_number)

        return new_department

    def after_rename(self, olddn: str, newdn: str, merge: bool = False) -> None:
        super().after_rename(olddn, newdn, merge)

        if not merge:
            new_department = cast(
                AccountingDepartment,
                frappe.db.get_value(
                    "Accounting Department",
                    newdn,
                    ["department_name", "department_number"],
                    as_dict=1,
                ),
            )

            new_parts = newdn.split(" - ")[:-1]
            if new_parts[0][0].isdigit():
                if len(new_parts) == 1:
                    new_parts = newdn.split(" ")
                if new_department.department_number != new_parts[0]:
                    validate_field_number(
                        "Accounting Department",
                        self.name,
                        new_parts[0],
                        self.company,
                        "department_number",
                    )
                    self.department_number = new_parts[0]
                    self.db_set("department_number", new_parts[0])
                new_parts = new_parts[1:]

            department_name = " - ".join(new_parts)
            if new_department.department_name != department_name:
                self.department_name = department_name
                self.db_set("department_name", department_name)


def on_doctype_update() -> None:
    frappe.db.add_index("Accounting Department", ["lft", "rgt"])


def get_name_with_number(new_name: str, number_value: str | None) -> str:
    if number_value and not new_name[0].isdigit():
        new_name = number_value + " - " + new_name
    return new_name


@frappe.whitelist()
def add_node() -> str:
    from frappe.desk.treeview import make_tree_args

    args = cast(AccountingDepartment, make_tree_args(**frappe.local.form_dict))
    args.doctype = "Accounting Department"

    if args.parent_accounting_department == args.company:
        args.parent_accounting_department = "{} - {}".format(
            args.parent_accounting_department,
            cast(str, frappe.get_cached_value("Company", args.company, "abbr")),
        )

    dept = cast(AccountingDepartment, frappe.new_doc("Accounting Department"))
    dept.update(args)

    if not dept.parent_accounting_department:
        dept.parent_accounting_department = args.get("parent")

    if not dept.name:
        raise frappe.ValidationError(_("Accounting Department name is mandatory"))
        frappe.throw(_("Accounting Department name is mandatory"))

    dept.old_parent = ""
    dept.insert()
    return dept.name


@frappe.whitelist()
def update_accounting_department(
    docname: str,
    department_name: str,
    department_number: str,
    company: str,
    merge: bool = False,
) -> str | None:
    validate_field_number("Accounting Department", docname, department_number, company, "department_number")

    if department_number:
        frappe.db.set_value("Accounting Department", docname, "department_number", department_number)
    frappe.db.set_value("Accounting Department", docname, "department_name", department_name)

    new_name = get_autoname_with_number(department_number, department_name, company)
    if docname != new_name:
        frappe.rename_doc("Accounting Department", docname, new_name, force=True, merge=merge)
        return new_name
    return None
