# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Compatibility shim for the generated setup package initializer.

Item Custom Fields and Property Setters are managed only by
``connect_diagnostics_core/custom/item.json``.
"""

CUSTOM_FIELDS: dict[str, list[dict[str, object]]] = {}
PROPERTY_SETTERS: dict[str, list[tuple[str, str, str, str]]] = {}


def ensure_configuration() -> None:
    """Keep the legacy setup hook inert; Item layout is exported in custom/item.json."""
