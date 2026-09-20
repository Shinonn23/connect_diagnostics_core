# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Retired: Print Formats may be either standard or editable.

The patch name remains in ``patches.txt`` so existing site patch history stays valid,
but current policy deliberately does not normalize the ``standard`` flag.
"""

from __future__ import annotations


def execute() -> None:
    """Preserve each Print Format's configured ownership mode."""
