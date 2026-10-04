// Copyright (c) 2026, Siwat Sroisuwan and contributors
// For license information, please see license.txt

frappe.ui.form.on("Asset Movement", {
	setup(frm) {
		set_reference_doctype_query(frm);
	},

	refresh(frm) {
		set_reference_doctype_query(frm);
		set_reference_doctype_read_only(frm);
		frm.set_query("reference_name", (doc) => {
			const filters = {
				company: doc.company,
				docstatus: 1,
			};

			if (doc.reference_doctype === "Material Request") {
				filters.material_request_type = ["in", ["Asset Transfer", "Customer Demo"]];
			}

			return { filters };
		});
	},

	async onload_post_render(frm) {
		set_reference_doctype_query(frm);
		await ensure_asset_transfer_reference(frm);
		set_reference_doctype_read_only(frm);
	},

	reference_doctype(frm) {
		set_reference_doctype_read_only(frm);
	},

	reference_name(frm) {
		set_reference_doctype_read_only(frm);
	},
});

function set_reference_doctype_query(frm) {
	const field = frm.fields_dict.reference_doctype;
	if (!field) return;

	const query = () => ({
		filters: {
			name: ["in", ["Purchase Receipt", "Purchase Invoice", "Material Request"]],
		},
	});
	frm.set_query("reference_doctype", query);
	field.get_query = query;
	if (field.$input) field.$input.cache = {};
}

async function ensure_asset_transfer_reference(frm) {
	if (!frm.is_new() || !frm.doc.reference_name) return;
	if (frm.doc.reference_doctype && frm.doc.reference_doctype !== "Material Request") return;

	const local_request = locals["Material Request"]?.[frm.doc.reference_name];
	let material_request_type = local_request?.material_request_type;
	if (!material_request_type) {
		const response = await frappe.db.get_value(
			"Material Request",
			frm.doc.reference_name,
			"material_request_type",
		);
		material_request_type = response.message?.material_request_type;
	}

	if (["Asset Transfer", "Customer Demo"].includes(material_request_type)) {
		await frm.set_value("reference_doctype", "Material Request");
		frm.refresh_field("reference_doctype");
	}
}

function set_reference_doctype_read_only(frm) {
	const is_linked_to_mr = frm.doc.reference_doctype === "Material Request" && frm.doc.reference_name;
	frm.set_df_property("reference_doctype", "read_only", Boolean(is_linked_to_mr));
}
