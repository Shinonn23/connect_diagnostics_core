// Copyright (c) 2026, Siwat Sroisuwan and contributors
// For license information, please see license.txt

const CD_PAYMENT_ENTRY_REFERENCE_DOCTYPES = ["Purchase Invoice", "Sales Invoice"];

frappe.ui.form.on("Payment Entry", {
	refresh(frm) {
		update_dimension_lock(frm);
	},
	references_add(frm) {
		update_dimension_lock(frm);
	},
});

frappe.ui.form.on("Payment Entry Reference", {
	reference_name(frm, cdt, cdn) {
		sync_dimensions_from_references(frm, cdt, cdn);
	},
	allocated_amount(frm) {
		update_dimension_lock(frm);
	},
	references_remove(frm) {
		update_dimension_lock(frm);
	},
});

async function get_dimension_fields(frm) {
	if (frm.cd_dimension_fields) return frm.cd_dimension_fields;

	const response = await frappe.call({
		method: "erpnext.accounts.doctype.accounting_dimension.accounting_dimension.get_dimensions",
		args: { with_cost_center_and_project: true },
	});
	const dimensions = response.message?.[0] || [];

	frm.cd_dimension_fields = dimensions
		.map((dimension) => dimension.fieldname)
		.filter((fieldname, index, fieldnames) => {
			return fieldnames.indexOf(fieldname) === index && frappe.meta.has_field(frm.doctype, fieldname);
		});

	return frm.cd_dimension_fields;
}

async function sync_dimensions_from_references(frm, cdt, cdn) {
	const row = locals[cdt][cdn];
	if (!is_invoice_reference(row)) return;

	const dimensions = await get_dimension_fields(frm);
	const reference_values = await get_reference_dimensions(
		row.reference_doctype,
		row.reference_name,
		dimensions,
	);
	if (!reference_values) return;

	const conflicts = [];
	for (const fieldname of Object.keys(reference_values)) {
		const reference_value = reference_values[fieldname];
		const current_value = frm.doc[fieldname];
		if (!current_value && reference_value) {
			await frm.set_value(fieldname, reference_value);
		} else if (current_value !== reference_value) {
			conflicts.push(fieldname);
		}
	}

	if (conflicts.length) {
		frappe.msgprint({
			title: __("Accounting Dimension Mismatch"),
			indicator: "orange",
			message: __(
				"Selected invoice has different accounting dimensions. Please create a separate Payment Entry for this reference.",
			),
		});
	}

	update_dimension_lock(frm);
}

async function update_dimension_lock(frm) {
	const dimensions = await get_dimension_fields(frm);
	const should_lock = has_allocated_invoice_references(frm);

	for (const fieldname of dimensions) {
		frm.set_df_property(fieldname, "read_only", should_lock ? 1 : 0);
	}
}

function has_allocated_invoice_references(frm) {
	return (frm.doc.references || []).some((row) => {
		return is_invoice_reference(row) && flt(row.allocated_amount) !== 0;
	});
}

function is_invoice_reference(row) {
	return (
		row.reference_doctype &&
		row.reference_name &&
		CD_PAYMENT_ENTRY_REFERENCE_DOCTYPES.includes(row.reference_doctype)
	);
}

async function get_reference_dimensions(reference_doctype, reference_name, dimensions) {
	const fields = dimensions.filter((fieldname) => {
		return frappe.meta.has_field(reference_doctype, fieldname);
	});
	if (!fields.length) return null;

	const response = await frappe.db.get_value(reference_doctype, reference_name, fields);
	return response.message || null;
}
