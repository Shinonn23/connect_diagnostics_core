// Copyright (c) 2026, Siwat Sroisuwan and contributors
// For license information, please see license.txt

frappe.ui.form.on("Purchase Order", {
	refresh(frm) {
		frm.set_query("item_code", "items", function (doc, cdt, cdn) {
			const row = frappe.get_doc(cdt, cdn);
			return {
				query: "connect_diagnostics_core.api.erpnext.item.get_item_with_stock",
				filters: { warehouse: row.warehouse || "" },
			};
		});
	},
});

frappe.ui.form.on("Purchase Order Item", {
	item_code(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		if (!row.item_code || frm.doc.supplier) return;

		// Auto-fill supplier from Item Supplier table (primary supplier for this item)
		frappe.db.get_value(
			"Item Supplier",
			{ parent: row.item_code },
			"supplier",
			(r) => {
				if (r && r.supplier) {
					frm.set_value("supplier", r.supplier);
				}
			},
		);
	},
});
