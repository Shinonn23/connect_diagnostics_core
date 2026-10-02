# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

from frappe.model.document import Document


class AssetDisposalJournalEntry(Document):
    """Immutable evidence row owned by its Asset Disposal Request."""
