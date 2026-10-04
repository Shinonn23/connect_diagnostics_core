# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from frappe.model.document import Document


class MaterialRequestAssetTransferItem(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		asset: DF.Link
		asset_name: DF.Data | None
		asset_transfer_snapshot_captured: DF.Check
		current_location: DF.Link | None
		department: DF.Link | None
		from_employee: DF.Link | None
		item_code: DF.Link | None
		parent: DF.Data
		parentfield: DF.Data
		parenttype: DF.Data
		target_location: DF.Link | None
		territory: DF.Link | None
		to_employee: DF.Link | None
	# end: auto-generated types

	pass
