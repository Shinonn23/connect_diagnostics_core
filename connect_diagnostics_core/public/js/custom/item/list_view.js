// Copyright (c) 2026, Siwat Sroisuwan and contributors
// For license information, please see license.txt

/*
 * Item list view
 * ==============
 *
 * 1. COLUMN ORDER (left → right): Item Code, Item Group, Product Group, Brand.
 *    Item Code uses the document ID (`name`), which equals item_code for Items.
 *    We rebuild listview.columns in onload so the order is exactly as above and
 *    independent of which fields happen to have `in_list_view` ticked.
 *
 * 2. SINGLE SEARCH BOX:
 *    The default per-field standard filters are hidden (hide_name_filter) and a
 *    single "Search" box is added instead, placed at the far LEFT of the filter
 *    bar. Typing in it searches ACROSS several fields at once — the same set the
 *    item Link search uses:
 *        item_code (= name), item_name, DKSH item code, model,
 *        and every Item Alternative Name (child table).
 *    This is done server-side by injecting `or_filters` into the list query via
 *    get_args(), so paging/counting stay correct. `distinct` collapses the
 *    duplicate parent rows that the child-table join would otherwise produce.
 *
 * 3. "HAS DKSH ITEM CODE" FILTER:
 *    A checkbox in the filter bar — when ticked, only items with a DKSH item
 *    code are listed (dksh_item_code custom field, setup/item.py).
 */

const SEARCH_TARGETS = [
	// [doctype, fieldname] — Item Alternative Name is the child table (alternative_names)
	["Item", "name"],
	["Item", "item_name"],
	["Item", "dksh_item_code"],
	["Item", "model"],
	["Item Alternative Name", "name_value"],
];

frappe.listview_settings["Item"] = {
	add_fields: ["item_group", "product_group", "brand"],

	hide_name_column: true, // we own columns[] entirely (see onload)
	hide_name_filter: true, // replaced by the single search box below

	onload(listview) {
		// --- 1. Column order ---------------------------------------------------
		const get_df = (fieldname) =>
			frappe.meta.get_docfield("Item", fieldname) || {
				label: fieldname,
				fieldname,
			};

		listview.columns = [
			{
				type: "Subject",
				df: { label: __("Item Code"), fieldname: "name" },
			},
			{ type: "Tag" },
			{ type: "Field", df: get_df("item_group") },
			{ type: "Field", df: get_df("product_group") },
			{ type: "Field", df: get_df("brand") },
		];
		listview.render_header(true);

		// Drop standard filters we don't want in the bar. has_variants/variant_of
		// come from `in_standard_filter`; item_name is rendered because it is the
		// doctype's title_field (frappe always adds a filter box for the title
		// field) — the single Search box already covers it. make_standard_filters()
		// has already rendered them by the time onload runs, so remove them from
		// the page form.
		["item_name", "has_variants", "variant_of"].forEach((fieldname) => {
			const f = listview.page.fields_dict[fieldname];
			if (f) {
				$(f.wrapper).remove();
				delete listview.page.fields_dict[fieldname];
			}
		});

		// Add a Product Group filter box next to Item Group. Unlike the synthetic
		// boxes below, this stays registered in fields_dict so get_standard_filters()
		// turns it into a real `=` filter (product_group is a custom Link field,
		// setup/item.py).
		listview.page.add_field(
			{
				fieldtype: "Link",
				fieldname: "product_group",
				label: __("Product Group"),
				options: "Product Group",
				condition: "=",
				onchange: () => listview.filter_area.debounced_refresh_list_view(),
			},
			listview.page.page_form.find(".standard-filter-section"),
		);

		// --- 2. Single "search everything" box ---------------------------------
		const apply_search = frappe.utils.debounce((value) => {
			listview._cd_search_text = (value || "").trim();
			listview.start = 0;
			listview.refresh();
		}, 300);

		const field = listview.page.add_field({
			fieldtype: "Data",
			fieldname: "cd_item_search",
			label: __("Search"),
			placeholder: __("Item code, name, alt name, DKSH code…"),
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
		// synthetic box into a query filter (cd_item_search is not a real Item field).
		// The control keeps working via the `field` reference above.
		delete listview.page.fields_dict["cd_item_search"];

		// --- 3. "Has DKSH Item Code" filter -------------------------------------
		const dksh_field = listview.page.add_field({
			fieldtype: "Check",
			fieldname: "has_dksh_item_code",
			label: __("Has DKSH Item Code"),
			onchange() {
				listview._cd_has_dksh_item_code = this.get_value();
				listview.start = 0;
				listview.refresh();
			},
		});
		$(dksh_field.wrapper).appendTo(listview.page.page_form.find(".standard-filter-section"));
		// Synthetic like the search box — has_dksh_item_code is not a real Item field;
		// the actual condition is injected in get_args() below.
		delete listview.page.fields_dict["has_dksh_item_code"];

		// Inject the cross-field OR search into the list query on every refresh.
		const get_args = listview.get_args.bind(listview);
		listview.get_args = function () {
			const args = get_args();
			const txt = listview._cd_search_text;
			if (txt) {
				const like = `%${txt}%`;
				args.or_filters = SEARCH_TARGETS.map(([dt, fn]) => [dt, fn, "like", like]);
				args.distinct = 1;
			}
			if (listview._cd_has_dksh_item_code) {
				args.filters = args.filters || [];
				args.filters.push(["Item", "dksh_item_code", "is", "set"]);
			}
			return args;
		};
	},
};
