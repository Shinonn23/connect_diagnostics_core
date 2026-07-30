// Copyright (c) 2026, Siwat Sroisuwan and contributors
// For license information, please see license.txt

const QUOTATION_FORM_PRESETS = {
	"Form 01": {
		show_quotation_date: 1,
		quotation_signatory_type: "Sales Representative",
		quotation_validity_mode: "Valid Till",
	},
	"Form 02": {
		show_quotation_date: 0,
		quotation_signatory_type: "Sales Representative",
		quotation_validity_mode: "Valid Till",
	},
	"Form 03": {
		show_quotation_date: 1,
		quotation_signatory_type: "Managing Director",
		quotation_validity_mode: "Valid Till",
	},
	"Form 04": {
		show_quotation_date: 1,
		quotation_signatory_type: "Managing Director",
		quotation_validity_mode: "Custom Text",
	},
};

const DEFAULT_QUOTATION_PRINT_CONFIGURATION = {
	quotation_form_preset: "Form 01",
	...QUOTATION_FORM_PRESETS["Form 01"],
	quotation_language: "Thai",
	quotation_original_count: 1,
	quotation_copy_count: 0,
};

async function apply_quotation_print_configuration(frm, values) {
	frm.__cd_applying_quotation_print_configuration = true;
	try {
		await frm.set_value(values);
	} finally {
		frm.__cd_applying_quotation_print_configuration = false;
	}
}

async function load_customer_quotation_print_configuration(frm, customer) {
	if (frm.doc.docstatus !== 0 || frm.doc.quotation_to !== "Customer" || frm.doc.party_name !== customer) {
		return;
	}

	const sales_person = frm.doc.sales_team?.[0]?.sales_person || "";
	const response = await frappe.call({
		method: "connect_diagnostics_core.api.erpnext.quotation.get_print_configuration_defaults",
		args: { customer, sales_person },
	});

	if (frm.doc.party_name === customer && response.message?.data) {
		await apply_quotation_print_configuration(frm, response.message.data);
	}
}

async function mark_quotation_preset_custom(frm) {
	if (
		!frm.__cd_applying_quotation_print_configuration &&
		frm.doc.quotation_form_preset &&
		frm.doc.quotation_form_preset !== "Custom"
	) {
		await frm.set_value("quotation_form_preset", "Custom");
	}
}

frappe.ui.form.on("Quotation", {
	async refresh(frm) {
		frm.set_query("item_code", "items", function (doc, cdt, cdn) {
			const row = frappe.get_doc(cdt, cdn);
			return {
				query: "connect_diagnostics_core.api.erpnext.item.get_item_with_stock",
				filters: { warehouse: row.warehouse || "" },
			};
		});

		if (frm.is_new() && !frm.doc.quotation_form_preset) {
			await apply_quotation_print_configuration(frm, DEFAULT_QUOTATION_PRINT_CONFIGURATION);
		}
	},

	party_name(frm) {
		const customer = frm.doc.party_name;
		if (customer && frm.doc.quotation_to === "Customer" && frm.doc.docstatus === 0) {
			return frappe.after_ajax(() => load_customer_quotation_print_configuration(frm, customer));
		}
	},

	async quotation_form_preset(frm) {
		if (frm.__cd_applying_quotation_print_configuration) {
			return;
		}
		const values = QUOTATION_FORM_PRESETS[frm.doc.quotation_form_preset];
		if (values) {
			await apply_quotation_print_configuration(frm, values);
		}
	},

	show_quotation_date: mark_quotation_preset_custom,
	quotation_signatory_type: mark_quotation_preset_custom,
	quotation_sales_representative: mark_quotation_preset_custom,
	quotation_validity_mode: mark_quotation_preset_custom,
	quotation_custom_validity_text: mark_quotation_preset_custom,
	quotation_delivery_terms: mark_quotation_preset_custom,
	quotation_language: mark_quotation_preset_custom,
	quotation_original_count: mark_quotation_preset_custom,
	quotation_copy_count: mark_quotation_preset_custom,
});
