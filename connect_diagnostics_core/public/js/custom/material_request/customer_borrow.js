// Copyright (c) 2026, Siwat Sroisuwan and contributors
// For license information, please see license.txt

const customerBorrowType = "Customer Borrow";

frappe.ui.form.on("Material Request", {
	setup(frm) {
		frm.__customer_borrow_last_type = frm.doc.material_request_type;
		frm.set_query("borrow_employee", () => ({
			filters: { company: frm.doc.company || "", status: "Active" },
		}));
		frm.set_query("borrow_warehouse", () => ({
			filters: { company: frm.doc.company || "", is_group: 0, disabled: 0 },
		}));
	},

	refresh(frm) {
		frm.__customer_borrow_last_type = frm.doc.material_request_type;
		refresh_customer_borrow_ui(frm);
		if (is_customer_borrow(frm) && frm.doc.docstatus === 0) {
			sync_borrow_target(frm);
		}
		if (!is_customer_borrow(frm) || frm.doc.docstatus !== 1) return;
		if (frm.doc.borrow_fulfillment_status !== "Sent") {
			frm.add_custom_button(__("Send Borrowed Items"), () => open_customer_borrow_stock_entry(frm), __("Create"));
			frm.page.set_inner_btn_group_as_primary(__("Create"));
		}
		frm.add_custom_button(__("Borrow Tracking"), () => {
			frappe.set_route("query-report", "Customer Borrow Tracking", { material_request: frm.doc.name });
		}, __("View"));
	},

	async material_request_type(frm) {
		const wasBorrow = frm.__customer_borrow_last_type === customerBorrowType;
		frm.__customer_borrow_last_type = frm.doc.material_request_type;
		invalidate_borrow_resolution(frm);
		if (wasBorrow && !is_customer_borrow(frm) && frm.doc.docstatus === 0) {
			await clear_customer_borrow_fields(frm);
		}
		refresh_customer_borrow_ui(frm);
		if (is_customer_borrow(frm)) sync_borrow_target(frm);
	},

	async company(frm) {
		if (!is_customer_borrow(frm)) return;
		invalidate_borrow_resolution(frm);
		await frm.set_value("borrow_warehouse", "");
		await clear_borrow_target(frm);
		if (frm.doc.borrow_employee) await frm.set_value("borrow_employee", "");
	},

	async borrow_employee(frm) {
		if (!is_customer_borrow(frm)) return;
		const token = invalidate_borrow_resolution(frm);
		await frm.set_value("borrow_warehouse", "");
		await clear_borrow_target(frm);
		if (frm.doc.borrow_employee && frm.doc.company) await resolve_borrow_warehouse(frm, token);
	},

	set_from_warehouse(frm) {
		if (!is_customer_borrow(frm) || frm.doc.docstatus !== 0) return;
		for (const row of frm.doc.items || []) {
			if (row.from_warehouse !== frm.doc.set_from_warehouse) {
				frappe.model.set_value(row.doctype, row.name, "from_warehouse", frm.doc.set_from_warehouse || "");
			}
		}
	},

	set_warehouse(frm) {
		if (is_customer_borrow(frm) && frm.doc.set_warehouse !== (frm.doc.borrow_warehouse || "")) {
			frm.set_value("set_warehouse", frm.doc.borrow_warehouse || "");
		}
	},

	async validate(frm) {
		if (!is_customer_borrow(frm)) return;
		if (!frm.doc.borrow_warehouse) frappe.throw(__("Select an employee and resolve their Borrow Warehouse before saving."));
		await sync_borrow_target(frm);
	},
});

frappe.ui.form.on("Material Request Item", {
	items_add(frm, cdt, cdn) {
		if (!is_customer_borrow(frm)) return;
		const row = locals[cdt][cdn];
		if (frm.doc.set_from_warehouse) frappe.model.set_value(cdt, cdn, "from_warehouse", frm.doc.set_from_warehouse);
		if (frm.doc.borrow_warehouse) frappe.model.set_value(cdt, cdn, "warehouse", frm.doc.borrow_warehouse);
	},

	warehouse(frm, cdt, cdn) {
		if (!is_customer_borrow(frm) || frm.doc.docstatus !== 0) return;
		const warehouse = frm.doc.borrow_warehouse || "";
		if (locals[cdt][cdn].warehouse !== warehouse) frappe.model.set_value(cdt, cdn, "warehouse", warehouse);
	},
});

function is_customer_borrow(frm) {
	return frm.doc.material_request_type === customerBorrowType;
}

function invalidate_borrow_resolution(frm) {
	frm.__borrow_resolution_token = (frm.__borrow_resolution_token || 0) + 1;
	return frm.__borrow_resolution_token;
}

async function clear_customer_borrow_fields(frm) {
	const warehouse = frm.doc.borrow_warehouse;
	if (warehouse && frm.doc.set_warehouse === warehouse) await frm.set_value("set_warehouse", "");
	for (const row of frm.doc.items || []) {
		if (warehouse && row.warehouse === warehouse) await frappe.model.set_value(row.doctype, row.name, "warehouse", "");
	}
	for (const field of ["borrow_customer", "borrow_employee", "borrow_warehouse", "borrow_expected_return_date", "borrow_fulfillment_status"]) {
		if (frm.doc[field]) await frm.set_value(field, "");
	}
}

function refresh_customer_borrow_ui(frm) {
	const borrow = is_customer_borrow(frm);
	if (borrow) frm.set_df_property("set_warehouse", "label", __("Set Target Warehouse"));
	frm.set_df_property("set_warehouse", "read_only", borrow ? 1 : 0);
	if (borrow) frm.fields_dict.items?.grid.update_docfield_property("warehouse", "label", __("Target Warehouse"));
	frm.fields_dict.items?.grid.update_docfield_property("warehouse", "read_only", borrow ? 1 : 0);
	if (!borrow || frm.doc.docstatus !== 0 || !frm.doc.borrow_employee || frm.doc.borrow_warehouse) return;
	frm.add_custom_button(__("Resolve Borrow Warehouse"), () => resolve_borrow_warehouse(frm, invalidate_borrow_resolution(frm)));
}

async function clear_borrow_target(frm) {
	if (frm.doc.docstatus !== 0) return;
	if (frm.doc.set_warehouse) await frm.set_value("set_warehouse", "");
	for (const row of frm.doc.items || []) {
		if (row.warehouse) await frappe.model.set_value(row.doctype, row.name, "warehouse", "");
	}
}

async function sync_borrow_target(frm) {
	if (frm.doc.docstatus !== 0) return;
	const warehouse = frm.doc.borrow_warehouse || "";
	if (frm.doc.set_warehouse !== warehouse) await frm.set_value("set_warehouse", warehouse);
	for (const row of frm.doc.items || []) {
		if (row.warehouse !== warehouse) await frappe.model.set_value(row.doctype, row.name, "warehouse", warehouse);
	}
}

async function resolve_borrow_warehouse(frm, token) {
	const employee = frm.doc.borrow_employee;
	const company = frm.doc.company;
	const requestName = frm.doc.name;
	if (!employee || !company) return;
	const { message } = await frappe.call({
		method: "connect_diagnostics_core.api.erpnext.customer_borrow.ensure_employee_borrow_warehouse",
		type: "POST",
		args: { employee, company, material_request: frm.is_new() ? null : frm.doc.name },
	});
	if (token !== frm.__borrow_resolution_token || !is_customer_borrow(frm) || frm.doc.name !== requestName || frm.doc.borrow_employee !== employee || frm.doc.company !== company) return;
	const warehouse = message?.data?.warehouse;
	if (!warehouse) frappe.throw(message?.message || __("Employee Borrow Warehouse could not be resolved."));
	await frm.set_value("borrow_warehouse", warehouse);
	await sync_borrow_target(frm);
}

async function open_customer_borrow_stock_entry(frm) {
	const { message } = await frappe.call({
		method: "connect_diagnostics_core.api.erpnext.customer_borrow.get_customer_borrow_stock_entry_draft",
		type: "POST",
		args: { material_request: frm.doc.name },
	});
	const draft = message?.data;
	if (!draft) {
		frappe.msgprint(message?.message || __("There are no items left to send."));
		return;
	}
	frappe.model.sync(draft);
	await frappe.set_route("Form", "Stock Entry", draft.name);
	frappe.show_alert({ message: __("Complete the Stock Entry approval workflow to send these items.") });
}
