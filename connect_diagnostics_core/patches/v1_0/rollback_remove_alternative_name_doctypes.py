# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Rollback for remove_alternative_name_doctypes.

Each child DocType has a real controller module file on disk
(``customer_alternative_name.py`` etc.), so recreating only the DocType
metadata row here would leave a DocType whose controller module cannot be
imported. A correct rollback must restore the source files, not just DB rows.
To restore:

1. Restore the three doctype folders from git history (before the commit that
   removed them) under
   ``connect_diagnostics_core/doctype/{customer_alternative_name,
   item_alternative_name,supplier_alternative_name}``.
2. Restore the ``alternative_names`` field entries in ``setup/customer.py``,
   ``setup/item.py``, and ``setup/supplier.py``.
3. Restore the ``or_filters``/search-target references in
   ``api/erpnext/customer.py``, ``api/erpnext/supplier.py``, and the two
   ``public/js/custom/{customer,supplier}/list_view.js`` files.
4. Run ``bench migrate`` — ``after_migrate`` recreates the Custom Fields from
   ``setup/*.py`` and Frappe reimports the child DocTypes from source.

Row data dropped by the removal patch (the actual Thai/alias name values) is
not recoverable by any of the above — this only restores the feature, not the
data that used to be stored in it.

Not registered in patches.txt (manual rollback utility only), matching the
existing rollback_remove_customer_name_th_field.py convention.
"""

import frappe
from frappe import _


def execute():
    frappe.throw(
        _(
            "Restoring the Alternative Names feature requires restoring the three doctype "
            "folders, the setup/*.py field definitions, and the search-logic call sites from "
            "git history, then re-running `bench migrate` — see this file's module docstring. "
            "There is nothing this script can do purely against the database."
        )
    )
