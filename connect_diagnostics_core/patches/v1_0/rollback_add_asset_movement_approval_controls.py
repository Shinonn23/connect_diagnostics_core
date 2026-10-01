# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Guarded rollback marker for the Asset Movement approval route."""

from __future__ import annotations

from connect_diagnostics_core.patches.v1_0.add_asset_movement_approval_controls import rollback

__all__ = ["rollback"]
