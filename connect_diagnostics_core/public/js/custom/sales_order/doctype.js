// Copyright (c) 2026, Siwat Sroisuwan and contributors
// For license information, please see license.txt

const DKSH_ITEM_MAPPING_QUERY =
	"connect_diagnostics_core.api.erpnext.sales_order.get_active_dksh_item_mapping";
const DKSH_ITEM_MAPPING_DETAILS =
	"connect_diagnostics_core.api.erpnext.sales_order.get_active_dksh_item_mapping_details";
const SALES_ORDER_ITEM_MODE = "connect_diagnostics_core.api.erpnext.sales_order.get_sales_order_item_mode";
const STANDARD_ITEM_QUERY = "connect_diagnostics_core.api.erpnext.item.get_item_with_stock";
const MARK_AS_KEYED_IN_SAP = "connect_diagnostics_core.api.erpnext.sales_order.mark_as_keyed_in_sap";
const CORRECT_SAP_ORDER_NO = "connect_diagnostics_core.api.erpnext.sales_order.correct_sap_order_no";

function getItemsGrid(frm) {
	return frm.fields_dict.items?.grid;
}

function hasSelectedItems(frm) {
	return (frm.doc.items || []).some((row) => row.item_code || row.dksh_item_mapping);
}

function configureItemQueries(frm) {
	frm.set_query("item_code", "items", function (doc, cdt, cdn) {
		const row = frappe.get_doc(cdt, cdn);
		return {
			query: STANDARD_ITEM_QUERY,
			filters: {
				warehouse: row.warehouse || "",
				company: doc.company || "",
			},
		};
	});

	frm.set_query("dksh_item_mapping", "items", function (doc) {
		return {
			query: DKSH_ITEM_MAPPING_QUERY,
			filters: { company: doc.company || "" },
		};
	});
}

function setGridColumnVisibility(grid, fieldname, show) {
	const docfield = grid.get_docfield(fieldname);
	if (!docfield) return;

	const visible = show ? 1 : 0;
	docfield.hidden = visible ? 0 : 1;
	docfield.in_list_view = visible;
}

function configureItemGridColumns(frm, isDkshCompany) {
	const grid = getItemsGrid(frm);
	if (!grid) return;

	setGridColumnVisibility(grid, "item_code", !isDkshCompany);
	setGridColumnVisibility(grid, "dksh_item_mapping", isDkshCompany);
	for (const fieldname of ["item_name", "qty", "uom", "rate", "amount"]) {
		setGridColumnVisibility(grid, fieldname, true);
	}
	setGridColumnVisibility(grid, "delivery_date", false);

	// Reset the editable grid after changing its document-specific metadata.
	// `set_column_disp` only updates controls that have already been rendered,
	// which can leave a hidden Item control without creating the DKSH one.
	grid.reset_grid();
}

async function applyDkshOrderDefaults(frm, itemMode) {
	const isDkshCompany = Boolean(itemMode?.is_dksh_company);
	const values = {};
	if (isDkshCompany) {
		if (frm.doc.selling_price_list !== itemMode.selling_price_list) {
			values.selling_price_list = itemMode.selling_price_list;
		}
		if (Number(frm.doc.skip_delivery_note) !== Number(itemMode.skip_delivery_note)) {
			values.skip_delivery_note = itemMode.skip_delivery_note;
		}
	}
	if (Object.keys(values).length) {
		await frm.set_value(values);
	}

	for (const fieldname of ["selling_price_list", "skip_delivery_note"]) {
		if (frm.fields_dict[fieldname]) {
			frm.set_df_property(fieldname, "read_only", isDkshCompany ? 1 : 0);
		}
	}
}

async function callSapKeyingAction(frm, method, args) {
	await frappe.call({
		method,
		args: { sales_order: frm.doc.name, ...args },
		freeze: true,
		freeze_message: __("Saving SAP order details..."),
	});
	await frm.reload_doc();
}

function addSapKeyingActions(frm) {
	if (!frm.__dksh_item_mode || frm.doc.docstatus !== 1 || !frm.has_perm("write")) return;

	const statuses = frm.__dksh_sap_order_statuses || {};
	if (frm.doc.sap_order_status === statuses.pending) {
		frm.add_custom_button(__("Mark as Keyed in SAP"), () => {
			frappe.prompt(
				[
					{
						fieldname: "sap_order_no",
						fieldtype: "Data",
						label: __("SAP Order No."),
						reqd: 1,
					},
				],
				(values) => callSapKeyingAction(frm, MARK_AS_KEYED_IN_SAP, values),
				__("Mark as Keyed in SAP"),
				__("Save"),
			);
		});
	}

	if (frm.doc.sap_order_status === statuses.keyed) {
		frm.add_custom_button(__("Correct SAP Order No."), () => {
			frappe.prompt(
				[
					{
						fieldname: "sap_order_no",
						fieldtype: "Data",
						label: __("SAP Order No."),
						default: frm.doc.sap_order_no,
						reqd: 1,
					},
					{
						fieldname: "correction_reason",
						fieldtype: "Small Text",
						label: __("Correction Reason"),
						reqd: 1,
					},
				],
				(values) => callSapKeyingAction(frm, CORRECT_SAP_ORDER_NO, values),
				__("Correct SAP Order No."),
				__("Save"),
			);
		});
	}
}

async function refreshItemMode(frm) {
	const company = frm.doc.company || "";
	const response = await frappe.call({
		method: SALES_ORDER_ITEM_MODE,
		args: { company },
	});
	if (company !== (frm.doc.company || "")) return;

	const itemMode = response.message?.data || {};
	frm.__dksh_item_mode = Boolean(itemMode.is_dksh_company);
	frm.__dksh_sap_order_statuses = itemMode.sap_order_statuses || {};
	await applyDkshOrderDefaults(frm, itemMode);
	configureItemGridColumns(frm, frm.__dksh_item_mode);
	addSapKeyingActions(frm);
}

function restoreCompanyAfterItemWarning(frm, company) {
	frm.__restoring_company = true;
	frm.set_value("company", company).finally(() => {
		frm.__restoring_company = false;
	});
}

frappe.ui.form.on("Sales Order", {
	setup(frm) {
		frm.__last_item_company = frm.doc.company || "";
		configureItemQueries(frm);
	},
	async refresh(frm) {
		frm.__last_item_company = frm.doc.company || frm.__last_item_company || "";
		configureItemQueries(frm);
		await refreshItemMode(frm);
	},
	async company(frm) {
		if (frm.__restoring_company) return;

		const previousCompany = frm.__last_item_company || "";
		const currentCompany = frm.doc.company || "";
		if (previousCompany && currentCompany !== previousCompany && hasSelectedItems(frm)) {
			frappe.msgprint(__("Delete all Items before changing Company."));
			restoreCompanyAfterItemWarning(frm, previousCompany);
			return;
		}

		frm.__last_item_company = currentCompany;
		await refreshItemMode(frm);
	},
});

frappe.ui.form.on("Sales Order Item", {
	dksh_item_mapping(frm, cdt, cdn) {
		if (!frm.__dksh_item_mode) return;

		const row = locals[cdt][cdn];
		const mapping = row.dksh_item_mapping;
		if (!mapping) {
			frappe.model.set_value(cdt, cdn, "item_code", "");
			return;
		}

		frappe
			.call({
				method: DKSH_ITEM_MAPPING_DETAILS,
				args: { mapping, company: frm.doc.company || "" },
			})
			.then((response) => {
				if (locals[cdt][cdn].dksh_item_mapping !== mapping) return;
				const itemCode = response.message?.data?.item_code;
				if (itemCode) {
					frappe.model.set_value(cdt, cdn, "item_code", itemCode);
				}
			});
	},
});
