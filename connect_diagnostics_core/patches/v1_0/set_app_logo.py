from __future__ import annotations

import frappe

APP_LOGO_URL = "/assets/connect_diagnostics_core/images/cd_logo.jpg?v=2"


def execute() -> None:
    """Force the navbar/app logo to the Connect Diagnostics logo.

    The ``app_logo_url`` hook is unreliable when more than two apps are
    installed: ``get_app_logo`` only honours ``logos[1]`` when exactly two
    logos are registered, otherwise it falls back to ``logos[0]`` (Frappe's
    own logo). Setting ``Navbar Settings.app_logo`` takes priority over the
    hook, so the logo resolves correctly regardless of app count.
    """
    frappe.db.set_single_value("Navbar Settings", "app_logo", APP_LOGO_URL)
    frappe.clear_cache()
