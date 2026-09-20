# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Rollback twin for ``drop_customer_print_configuration``.

The forward patch removes custom fields and DocTypes for a feature that was
deleted from the codebase. It is deliberately **not reversible**: the DocType
definitions and the per-Customer data are gone from the repository, so there is
nothing to restore them from. Recovering a site that ran the drop means checking
out the app at a revision before the removal and migrating there. This file
exists to satisfy the patch/rollback pairing rule and to state that plainly; it
performs no changes.
"""

from __future__ import annotations


def execute() -> None:
    return
