# Knowledge: Frappe List View (JS)

_Last updated: 2026-05-07_

## Key Files

- `apps/frappe/frappe/public/js/frappe/list/list_view.js` — main implementation (2269 lines)
- `apps/frappe/frappe/public/js/frappe/list/base_list.js` — base class (934 lines)
- `apps/frappe/frappe/public/js/frappe/list/list_view_select.js` — column selection UI (347 lines)

## Entry Points

| Symbol                         | Location                 | Notes                                                            |
| ------------------------------ | ------------------------ | ---------------------------------------------------------------- |
| `setup_columns()`              | `list_view.js:375–459`   | Builds `this.columns`; called before `onload` fires              |
| `render_header(refresh=false)` | `list_view.js:600–608`   | Pass `true` to force re-render after column mutation             |
| `get_subject_text()`           | `list_view.js:1085–1103` | Applies formatters; strips HTML for HTML fieldtypes              |
| `before_render` hook           | `list_view.js:618`       | `listview_settings.before_render()` — fires before every refresh |
| `onload` hook                  | `list_view.js:333`       | Fires after `setup_columns()` and initial `render_header()`      |

## Column Types (verified string values)

- `"Subject"` — always `columns[0]`; checkbox + link; formatter applied via `get_subject_text()`; CSS: `list-row-col list-subject level ellipsis`; always visible
- `"Tag"` — always `columns[1]`; user tag pills; hidden by default
- `"Status"` — coloured status pill; auto-added when `frappe.has_indicator(doctype)` is true
- `"Field"` — regular data column; CSS: `list-row-col hidden-xs ellipsis`; hidden on mobile; numeric fieldtypes get `text-right` class automatically

Each column entry: `{ type: "Subject"|"Field"|"Status"|"Tag", df: <docfield object> }`

## `listview_settings` Keys (all source-verified)

| Key                | Source Line        | Description                                                                                           |
| ------------------ | ------------------ | ----------------------------------------------------------------------------------------------------- |
| `add_fields`       | 219                | Extra fields fetched from server — required when formatter uses `doc.fieldname` not in `in_list_view` |
| `hide_name_column` | 447                | Suppress Frappe's auto-appended `name` (ID) column                                                    |
| `formatters`       | 907–911, 1088–1090 | `{ fieldname(value, df, doc) → HTML string }`                                                         |
| `before_render`    | 618                | `() → void`; called before every data refresh                                                         |
| `button`           | 950, 1369          | `{ show(doc), get_label(doc), get_description(doc), action(doc) }` — per-row action button            |
| `get_indicator`    | —                  | Override via `frappe.get_indicator()` at line 1106; return `[label, colour, filter]`                  |
| `onload`           | 333                | `(listview) → void`; safe place to mutate `listview.columns`                                          |

## Column Count Limits by Screen Width (`list_view.js:436–442`)

```js
let total_fields = 6;
if (window.innerWidth <= 1366) total_fields = 4;
else if (window.innerWidth >= 1920) total_fields = 10;
```

Override: List View Settings doctype `total_fields` field.

## Formatter Notes

- Return raw HTML string; Frappe wraps it in the cell div
- **Subject column:** formatter runs through `get_subject_text()` — HTML is stripped for HTML fieldtypes via `html2text()`; safe for `Data` / `Link` / `name` fieldtypes
- **Field column:** formatter fully replaces `field_html()` — you own the full inner HTML
- **Width control:** `<span style="min-width:120px; display:inline-block;">${val}</span>`
- **Pill/badge:** `<span class="indicator-pill green ellipsis">${val}</span>` — colours: gray red green orange blue purple pink yellow cyan

## `onload` Column Manipulation Pattern

```js
onload(listview) {
  // listview.columns already built; onload fires before first refresh()
  listview.columns.splice(insertAt, 0, newCol);  // insert
  listview.columns.splice(removeAt, 1);           // remove
  listview.columns[0] = newSubjectCol;            // replace Subject
  listview.render_header(true);                   // force header re-render
  // Frappe calls refresh() after onload → rows render with updated columns
}
```

Synthetic column (minimum df): `{ type: "Field", df: { label: "My Label", fieldname: "my_field" } }`

## Constraints

- `is_virtual: true` on a df → Frappe auto-excludes the column
- `in_list_view: true` on a df → Frappe auto-includes as a Field column (no need to add manually)
- Subject formatters that return HTML will have markup stripped if df.fieldtype is an HTML type — use Data/Link fieldtype or no fieldtype to preserve HTML
- Column mutations in `onload` must be followed by `render_header(true)` to take effect in the header; row data picks up changes automatically on the first `refresh()`

## Dead Ends

- `get_indicator` is NOT a direct `listview_settings` key in the current source — the internal call is `frappe.get_indicator()` at `list_view.js:1106`; user-space override goes through `frappe.listview_settings[doctype].get_indicator`
