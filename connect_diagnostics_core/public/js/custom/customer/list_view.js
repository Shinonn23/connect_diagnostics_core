// Copyright (c) 2026, Siwat Sroisuwan and contributors
// For license information, please see license.txt

/*
 * Customer list view
 * ==================
 *
 * Single "search everything" box, placed at the far LEFT of the filter bar.
 * The default ID filter is hidden (hide_name_filter) — the box covers it.
 * Typing in it searches ACROSS several fields at once — the same set the
 * Customer link search uses (see api/erpnext/customer.py):
 *     name (= Customer Code), customer_name, DKSH SAP customer code,
 *     and every Customer Alternative Name (child table).
 *
 * Implemented server-side by injecting `or_filters` into the list query via
 * get_args(), so paging/counting stay correct. `distinct` collapses the
 * duplicate parent rows the child-table join would otherwise produce.
 */

const SEARCH_TARGETS = [
	["Customer", "name"],
	["Customer", "customer_code"],
	["Customer", "customer_name"],
	["Customer", "dksh_sap_customer_code"],
	["Customer", "dksh_customer_code"],
	["Customer Alternative Name", "name_value"],
];

frappe.listview_settings["Customer"] = {
	add_fields: [
		"customer_name",
		"customer_group",
		"customer_channel",
		"customer_onboarding_state",
		"tax_invoice_readiness",
		"delivery_readiness",
	],

	hide_name_filter: true, // replaced by the single search box below

	onload(listview) {
		const apply_search = frappe.utils.debounce((value) => {
			listview._cd_search_text = (value || "").trim();
			listview.start = 0;
			listview.refresh();
		}, 300);

		const field = listview.page.add_field({
			fieldtype: "Data",
			fieldname: "cd_customer_search",
			label: __("Search"),
			placeholder: __("Customer Code, name, alt name, DKSH SAP code…"),
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
		// synthetic box into a query filter (cd_customer_search is not a real field).
		delete listview.page.fields_dict["cd_customer_search"];

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
