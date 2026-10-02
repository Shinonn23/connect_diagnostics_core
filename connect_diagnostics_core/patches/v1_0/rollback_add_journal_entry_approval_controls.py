# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Remove only additive Journal Entry approval fields."""

from __future__ import annotations


def execute() -> None:
    # Evidence fields are intentionally retained: rollback must not destroy snapshots,
    # proofs, or audit history on governed or submitted Journal Entries.
    return None
