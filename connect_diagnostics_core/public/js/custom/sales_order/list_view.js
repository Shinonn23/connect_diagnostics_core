/*
 * DRAFT REFERENCE — Frappe List View: columns, types, formatters, styling
 * =========================================================================
 *
 * HOW columns[] WORKS
 * -------------------
 * Frappe builds `listview.columns` in setup_columns() before onload fires.
 * Each entry is a plain object: { type, df }
 *
 *   col.type  — one of "Subject" | "Field" | "Status" | "Tag"
 *   col.df    — docfield descriptor (see below)
 *
 *
 * COLUMN TYPES
 * ------------
 *
 *   "Subject"
 *     • Always columns[0]. The leftmost clickable link column.
 *     • Renders checkbox + document link.
 *     • df.fieldname drives what value is shown as the link text.
 *     • formatter for df.fieldname IS applied here (via get_subject_text).
 *     • CSS: "list-row-col list-subject level ellipsis"
 *       → always visible, never hidden-xs, takes up remaining flex space.
 *
 *   "Field"
 *     • Any regular data column.
 *     • CSS: "list-row-col hidden-xs ellipsis"
 *       → hidden on xs/mobile. No fixed width — flex layout shares remaining space.
 *     • formatter for df.fieldname IS applied (col.type !== "Subject" check passes).
 *     • Adds "text-right" class automatically for numeric fieldtypes.
 *
 *   "Status"
 *     • The coloured status pill. Uses frappe.get_indicator(doc, doctype).
 *     • No df needed. Auto-added when frappe.has_indicator(doctype) returns true.
 *
 *   "Tag"
 *     • User tag pills. Always at columns[1].
 *     • Hidden by default; shown when user toggles tag display in list view.
 *
 *
 * THE df OBJECT
 * -------------
 * For real doctype fields: frappe.meta.get_docfield(doctype, fieldname)
 * For synthetic columns you only need the minimum:
 *
 *   { label: "My Label", fieldname: "my_field" }
 *
 * Extra df properties that affect rendering:
 *   fieldtype  — auto-formats value (Currency, Date, Percent progress bar,
 *                Rating stars, Image thumbnail, Select pill, Link anchor, etc.)
 *   options    — for Link: target doctype; for Select: choices string
 *   is_virtual — true → column excluded automatically by Frappe
 *   in_list_view — true → Frappe auto-includes the field as a Field column
 *
 *
 * COLUMN WIDTH
 * ------------
 * Frappe list view uses CSS flex; individual Field columns have NO explicit width.
 * Subject gets all remaining space; Field columns share the remainder equally.
 *
 * To constrain width, return a styled span from the formatter:
 *
 *   formatters: {
 *     my_field(val) {
 *       return `<span style="min-width:120px; display:inline-block;">${val}</span>`;
 *     }
 *   }
 *
 * Maximum visible Field columns (auto-sliced by Frappe):
 *   ≤1366px → 4  |  default → 6  |  ≥1920px → 10
 * Override via List View Settings doctype (total_fields field).
 *
 *
 * TEXT FORMATTING IN formatters
 * ------------------------------
 * formatters return raw HTML strings. Frappe wraps the return value in a cell div.
 *
 *   Bold:          `<strong>${val}</strong>`
 *   Light/thin:    `<span style="font-weight:300;">${val}</span>`
 *   Italic:        `<em>${val}</em>`
 *   Underline:     `<span style="text-decoration:underline;">${val}</span>`
 *   Strikethrough: `<s>${val}</s>`
 *   Colour:        `<span style="color:#e74c3c;">${val}</span>`
 *   Pill/badge:    `<span class="indicator-pill green ellipsis">${val}</span>`
 *                  Frappe colour classes: gray red green orange blue purple pink yellow cyan
 *
 * Caveat — Subject columns: formatter runs through get_subject_text() which calls
 * html2text() when df.fieldtype is an HTML type, stripping your markup. For
 * Data/Link/name fields (no fieldtype, or fieldtype:"Data") HTML renders fine.
 *
 * Caveat — Field columns: formatter completely replaces the default field_html()
 * render. You own the full inner HTML. Frappe still wraps it in the cell div.
 *
 *
 * FORMATTER SIGNATURE
 * -------------------
 *   formatters: {
 *     fieldname(value, df, doc) {
 *       // value — raw value from doc (may be "" not null when missing)
 *       // df    — docfield descriptor object
 *       // doc   — full row document (access other fields via doc.other_field)
 *       return "<html string>";
 *     }
 *   }
 *
 *
 * COLUMN ORDER MANIPULATION (onload pattern used in this file)
 * ------------------------------------------------------------
 *   onload(listview) {
 *     // listview.columns is already built; onload fires before the first refresh().
 *     listview.columns.splice(insertAt, 0, newCol); // insert
 *     listview.columns.splice(removeAt, 1);          // remove
 *     listview.columns[0] = newSubjectCol;            // replace Subject
 *     listview.render_header(true);                   // force header re-render
 *     // After onload, Frappe calls refresh() → rows render with updated columns.
 *   }
 *
 *
 * OTHER USEFUL listview_settings KEYS
 * ------------------------------------
 *   add_fields: ["fieldname", ...]
 *     Extra fields fetched from server. Required when a formatter references
 *     doc.fieldname for a field that is not in_list_view.
 *
 *   hide_name_column: true
 *     Suppress Frappe's default behaviour of appending `name` as the last Field.
 *
 *   get_indicator(doc)
 *     Return [label, colour_class, filter_string] to override Status pill.
 *     Example: if (doc.status === "Overdue") return ["Overdue", "red", "status,=,Overdue"];
 *
 *   button: { show(doc), get_label(doc), get_description(doc), action(doc) }
 *     Adds a per-row action button (shown in the right meta area).
 *
 *   before_render()
 *     Called before every data refresh cycle.
 */

frappe.listview_settings["Sales Order"] = {
	add_fields: ["name", "customer_name", "status", "sap_order_no", "sap_order_status"],

	hide_name_column: true,

	onload(listview) {
		// Move name (Sales Order ID) to the leftmost Subject column position.
		// Sales Order's title_field is customer_name, which Frappe places at columns[0].
		// We swap it: name becomes Subject (columns[0], the clickable link), customer_name
		// becomes a Field inserted after the Tag column (index 2).
		const customerNameCol = { ...listview.columns[0], type: "Field" };
		listview.columns[0] = {
			type: "Subject",
			df: { label: __("ID"), fieldname: "name" },
		};
		listview.columns.splice(2, 0, customerNameCol);
		listview.render_header(true);
	},
};
