// Copyright (c) 2026, Siwat Sroisuwan and contributors
// For license information, please see license.txt

frappe.ui.form.on("Material Request", {
	refresh(frm) {
		frm.set_query("item_code", "items", function (doc, cdt, cdn) {
			const row = frappe.get_doc(cdt, cdn);
			return {
				query: "connect_diagnostics_core.api.erpnext.item.get_item_with_stock",
				filters: { warehouse: row.warehouse || "" },
			};
		});
	},
	validate(frm) {
		validate_schedule_date(frm);
	},
});

function validate_schedule_date(frm) {
	if (!frm.doc.schedule_date) return;

	const today = new Date();
	const scheduleDate = new Date(frm.doc.schedule_date);

	today.setHours(0, 0, 0, 0);
	scheduleDate.setHours(0, 0, 0, 0);

	const diffDays = (scheduleDate - today) / (1000 * 60 * 60 * 24);

	if (diffDays < 0) {
		frappe.throw(frappe._("Schedule date cannot be in the past."));
	}
	if (diffDays > 180) {
		frappe.throw(frappe._("Schedule date cannot be more than 6 months in the future."));
	}
}
