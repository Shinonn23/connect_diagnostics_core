// Copyright (c) 2026, Siwat Sroisuwan and contributors
// For license information, please see license.txt

/*
 * Item list view
 * ==============
 *
 * 1. COLUMN ORDER (left → right): Item Code, Item Name, Item Group, Brand.
 *    Item Code uses the document ID (`name`), which equals item_code for Items.
 *    We rebuild listview.columns in onload so the order is exactly as above and
 *    independent of which fields happen to have `in_list_view` ticked.
 *
 * 2. SINGLE SEARCH BOX:
 *    The default per-field standard filters are hidden (hide_name_filter) and a
 *    single "Search" box is added instead. Typing in it searches ACROSS several
 *    fields at once — the same set the item Link search uses:
 *        item_code (= name), item_name, DKSH item code, model,
 *        and every Item Alternative Name (child table).
 *    This is done server-side by injecting `or_filters` into the list query via
 *    get_args(), so paging/counting stay correct. `distinct` collapses the
 *    duplicate parent rows that the child-table join would otherwise produce.
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
	add_fields: ["item_name", "item_group", "brand"],

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
			{ type: "Field", df: get_df("item_name") },
			{ type: "Field", df: get_df("item_group") },
			{ type: "Field", df: get_df("brand") },
		];
		listview.render_header(true);

		// Drop standard filters we don't want in the bar. These come from the Item
		// doctype's `in_standard_filter` fields; make_standard_filters() has already
		// rendered them by the time onload runs, so remove them from the page form.
		["has_variants", "variant_of"].forEach((fieldname) => {
			const f = listview.page.fields_dict[fieldname];
			if (f) {
				$(f.wrapper).remove();
				delete listview.page.fields_dict[fieldname];
			}
		});

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

		// Unregister from page.fields_dict so get_standard_filters() doesn't turn this
		// synthetic box into a query filter (cd_item_search is not a real Item field).
		// The control keeps working via the `field` reference above.
		delete listview.page.fields_dict["cd_item_search"];

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
			return args;
		};
	},

	formatters: {
		item_group(val) {
			return val || "-";
		},
		brand(val) {
			return val || "-";
		},
	},
};
