// Copyright (c) 2026, Siwat Sroisuwan and contributors
// For license information, please see license.txt

frappe.ui.form.on("Sales Order", {
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
