// Copyright (c) 2026, Siwat Sroisuwan and contributors
// For license information, please see license.txt

const ALIAS_FIELD_TYPES = ["Data", "Small Text", "Text", "Long Text", "Link"];

frappe.ui.form.on("Alias Supported DocType", {
	refresh(frm) {
		if (frm.doc.reference_doctype) {
			frm.trigger("reference_doctype");
		}
	},

	reference_doctype(frm) {
		if (!frm.doc.reference_doctype) {
			frm.set_df_property("alias_field", "options", [""]);
			frm.set_value("alias_field", "");
			frm.refresh_field("alias_field");
			return;
		}

		frappe.model.with_doctype(frm.doc.reference_doctype, function () {
			const meta = frappe.get_meta(frm.doc.reference_doctype);
			const fields = meta.fields
				.filter(
					(f) =>
						ALIAS_FIELD_TYPES.includes(f.fieldtype) &&
						!f.hidden &&
						f.label
				)
				.map((f) => f.fieldname);

			frm.set_df_property("alias_field", "options", ["", ...fields]);
			frm.refresh_field("alias_field");
		});
	},
});
