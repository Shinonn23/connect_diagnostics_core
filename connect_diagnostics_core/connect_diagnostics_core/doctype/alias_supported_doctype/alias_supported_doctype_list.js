frappe.listview_settings["Alias Supported DocType"] = {
	hide_name_column: true,
	add_fields: ["reference_doctype", "alias_field", "is_enabled"],
	formatters: {
		is_enabled(val) {
			const label = val ? __("Enabled") : __("Disabled");
			const color = val ? "green" : "gray";

			return `<span class="indicator-pill ${color} ellipsis">${label}</span>`;
		},
	},
	onload(listview) {
		listview.columns[0] = {
			type: "Subject",
			df: frappe.meta.get_docfield(
				"Alias Supported DocType",
				"reference_doctype"
			),
		};
		listview.columns.push({
			type: "Field",
			df: frappe.meta.get_docfield(
				"Alias Supported DocType",
				"alias_field"
			),
		});
		listview.columns.push({
			type: "Field",
			df: frappe.meta.get_docfield(
				"Alias Supported DocType",
				"is_enabled"
			),
		});
		listview.render_header(true);
	},
};
