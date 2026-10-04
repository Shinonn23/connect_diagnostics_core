// Copyright (c) 2026, Siwat Sroisuwan and contributors
// For license information, please see license.txt

frappe.ui.form.on("Stock Entry", {
	async refresh(frm) {
		const borrow = Boolean(frm.doc.borrow_material_request);
		if (frm.__borrow_reference !== frm.doc.borrow_material_request) {
			frm.__borrow_target_warehouse = null;
			frm.__borrow_reference = frm.doc.borrow_material_request;
			if (frm.__customer_borrow_intro) frm.set_intro("");
			frm.__customer_borrow_intro = false;
		}
		frm.set_df_property("to_warehouse", "read_only", borrow ? 1 : 0);
		frm.fields_dict.items?.grid.update_docfield_property("t_warehouse", "read_only", borrow ? 1 : 0);
		if (!borrow) {
			if (frm.__customer_borrow_intro) frm.set_intro("");
			frm.__customer_borrow_intro = false;
			return;
		}
		if (frm.doc.docstatus === 0) sync_customer_borrow_stock_entry_target(frm);
		const request = frm.doc.borrow_material_request;
		const stockEntry = frm.doc.name;
		try {
			const { message } = await frappe.db.get_value(
				"Material Request",
				request,
				["borrow_customer", "borrow_employee", "borrow_warehouse"],
			);
			if (frm.doc.name === stockEntry && frm.doc.borrow_material_request === request && message) {
				frm.__borrow_target_warehouse = message.borrow_warehouse || null;
				if (frm.doc.docstatus === 0) sync_customer_borrow_stock_entry_target(frm);
				const customer = frappe.utils.escape_html(message.borrow_customer || "");
				const employee = frappe.utils.escape_html(message.borrow_employee || "");
				frm.set_intro(__("Customer Borrow: Customer {0}; responsible employee {1}.", [customer, employee]));
				frm.__customer_borrow_intro = true;
			}
		} catch {
			if (frm.doc.name === stockEntry && frm.doc.borrow_material_request === request) {
				frm.set_intro(__("Customer Borrow request details are unavailable."));
				frm.__customer_borrow_intro = true;
			}
		}
	},

	to_warehouse(frm) {
		if (frm.doc.borrow_material_request && frm.doc.docstatus === 0) sync_customer_borrow_stock_entry_target(frm);
	},

	validate(frm) {
		if (frm.doc.borrow_material_request) sync_customer_borrow_stock_entry_target(frm);
	},
});

frappe.ui.form.on("Stock Entry Detail", {
	items_add(frm, cdt, cdn) {
		if (!frm.doc.borrow_material_request || !frm.doc.to_warehouse) return;
		frappe.model.set_value(cdt, cdn, "t_warehouse", frm.doc.to_warehouse);
	},

	t_warehouse(frm, cdt, cdn) {
		if (!frm.doc.borrow_material_request || frm.doc.docstatus !== 0) return;
		if (locals[cdt][cdn].t_warehouse !== frm.doc.to_warehouse) {
			frappe.model.set_value(cdt, cdn, "t_warehouse", frm.doc.to_warehouse || "");
		}
	},
});

function sync_customer_borrow_stock_entry_target(frm) {
	const warehouse = frm.__borrow_target_warehouse || frm.doc.to_warehouse || "";
	if (frm.doc.to_warehouse !== warehouse) frm.set_value("to_warehouse", warehouse);
	for (const row of frm.doc.items || []) {
		if (row.t_warehouse !== warehouse) frappe.model.set_value(row.doctype, row.name, "t_warehouse", warehouse);
	}
}
