frappe.listview_settings["Alias Name"] = {
	hide_name_column: true,
	add_fields: ["documents", "original_display_name"],
	formatters: {
		original_display_name(val) {
			return `<span style="display:inline-block;">${val || ""}</span>`;
		},
	},
	onload(listview) {
		listview.columns[0] = {
			type: "Subject",
			df: frappe.meta.get_docfield("Alias Name", "alias_name"),
		};

		const alias_col_idx = listview.columns.findIndex(
			(c) => c.type === "Field" && c.df?.fieldname === "alias_name",
		);
		if (alias_col_idx !== -1) {
			listview.columns.splice(alias_col_idx, 1);
		}

		listview.columns.splice(2, 0, {
			type: "Field",
			df: frappe.meta.get_docfield("Alias Name", "original_display_name"),
		});

		listview.columns.splice(3, 0, {
			type: "Field",
			df: frappe.meta.get_docfield("Alias Name", "documents"),
		});

		listview.render_header(true);
	},
};
