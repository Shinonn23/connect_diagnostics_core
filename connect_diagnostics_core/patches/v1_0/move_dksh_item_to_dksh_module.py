# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Move the DKSH Item DocType into the Connect Diagnostics DKSH module.

DKSH Item was created in ``Connect Diagnostics Core``. The DKSH domain now has its
own module — the single home for the DKSH reference masters and the deferred DKSH
sales import — so the DocType record is repointed and reloaded from its new module
folder. The records it names (250 on DEV) are untouched; only ``DocType.module``
moves.

Idempotent: repointing the module and reloading the DocType are both no-ops once
the record already sits in the target module.
"""

from __future__ import annotations

from typing import cast

import frappe
from frappe.utils.redis_wrapper import ClientCache, RedisWrapper

DKSH_MODULE = "Connect Diagnostics DKSH"


def execute() -> None:
    """Repoint DKSH Item at the DKSH module and reload it from the new folder."""
    _refresh_module_map()
    if frappe.db.exists("DocType", "DKSH Item"):
        frappe.db.set_value("DocType", "DKSH Item", "module", DKSH_MODULE)
    frappe.reload_doc(DKSH_MODULE, "doctype", "dksh_item", force=True)
    frappe.clear_cache()


def _refresh_module_map() -> None:
    """Rebuild the module map so ``Connect Diagnostics DKSH`` resolves during migration.

    ``frappe.local.module_app`` is built once at process init from the cached app
    module list, and ``frappe.clear_cache()`` does not rebuild it. A migration that
    runs right after the module was added to ``modules.txt`` therefore still sees
    the pre-checkout map, and ``reload_doc`` below fails with
    ``Module Connect Diagnostics DKSH not found``.
    """
    cast(RedisWrapper, frappe.cache).delete_value("app_modules")
    cast(ClientCache, frappe.client_cache).delete_value("installed_app_modules")
    frappe.setup_module_map()
