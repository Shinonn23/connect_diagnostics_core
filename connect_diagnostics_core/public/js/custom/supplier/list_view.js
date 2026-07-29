// Copyright (c) 2026, Siwat Sroisuwan and contributors
// For license information, please see license.txt

/*
 * Supplier list view
 * ==================
 *
 * Single "search everything" box, placed at the far LEFT of the filter bar.
 * The default ID filter is hidden (hide_name_filter) — the box covers it.
 * Typing in it searches ACROSS several fields at once — the same set the
 * Supplier link search uses (see api/erpnext/supplier.py):
 *     name (= Supplier ID), supplier_name, and every Supplier Alternative Name
 *     (child table).
 *
 * Implemented server-side by injecting `or_filters` into the list query via
 * get_args(), so paging/counting stay correct. `distinct` collapses the
 * duplicate parent rows the child-table join would otherwise produce.
 */

const SEARCH_TARGETS = [
	["Supplier", "name"],
	["Supplier", "supplier_name"],
	["Supplier Alternative Name", "name_value"],
];

frappe.listview_settings["Supplier"] = {
	add_fields: ["supplier_name", "supplier_group"],

	hide_name_filter: true, // replaced by the single search box below

	onload(listview) {
		const apply_search = frappe.utils.debounce((value) => {
			listview._cd_search_text = (value || "").trim();
			listview.start = 0;
			listview.refresh();
		}, 300);

		const field = listview.page.add_field({
			fieldtype: "Data",
			fieldname: "cd_supplier_search",
			label: __("Search"),
			placeholder: __("Supplier ID, name, alternative name…"),
			onchange() {
				apply_search(this.get_value());
			},
		});
		// Live search while typing, not only on commit/blur.
		field.$input.on("input", () => apply_search(field.get_value()));

		// add_field() appends after the filter/tag section (far right); move the box
		// to the far left of the bar, ahead of the remaining standard filters.
		$(field.wrapper).prependTo(listview.page.page_form.find(".standard-filter-section"));

		// Unregister from page.fields_dict so get_standard_filters() doesn't turn this
		// synthetic box into a query filter (cd_supplier_search is not a real field).
		delete listview.page.fields_dict["cd_supplier_search"];

		const get_args = listview.get_args.bind(listview);
		listview.get_args = function () {
			const args = get_args();
			const txt = listview._cd_search_text;
			if (txt) {
				const like = `%${txt}%`;
				args.or_filters = SEARCH_TARGETS.map(([dt, fn]) => [dt, fn, "like", like]);
				args.distinct = 1;
			}
			return args;
		};
	},
};
