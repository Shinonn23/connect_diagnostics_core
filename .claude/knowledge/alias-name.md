# Knowledge: Alias Name Feature

_Last updated: 2026-05-07_

## Key Files

- `connect_diagnostics_core/connect_diagnostics_core/doctype/alias_supported_doctype/alias_supported_doctype.json` — configures which doctypes support aliasing (`reference_doctype`, `alias_field`, `is_enabled`)
- `connect_diagnostics_core/connect_diagnostics_core/doctype/alias_supported_doctype/alias_supported_doctype.js` — JS form script: populates `alias_field` options from `reference_doctype` meta on change/refresh
- `connect_diagnostics_core/connect_diagnostics_core/doctype/alias_name/alias_name.json` — stores per-record alias mappings; fields: `documents`, `primary_name`, `alias_name`, `original_display_name` (read-only)
- `connect_diagnostics_core/connect_diagnostics_core/doctype/alias_name/alias_name.js` — JS form script: `set_query` on `documents`, auto-populate `original_display_name` on `primary_name` change
- `connect_diagnostics_core/api/connect_diagnostics_core/alias_name.py` — 3 whitelisted functions: `get_supported_doctypes`, `get_original_display_name`, `get_alias_map`
- `connect_diagnostics_core/api/connect_diagnostics_core/test_alias_name.py` — 12 unit tests (8 for `get_alias_map`, 4 for `get_original_display_name`)

## Entry Points

- Whitelisted search: `@frappe.whitelist()` + `@frappe.validate_and_sanitize_search_inputs` `get_supported_doctypes` at `api/connect_diagnostics_core/alias_name.py:11`
- Whitelisted API: `@frappe.whitelist()` `get_original_display_name` at `api/connect_diagnostics_core/alias_name.py:47`
- Whitelisted API: `@frappe.whitelist()` `get_alias_map` at `api/connect_diagnostics_core/alias_name.py:73`
- No `hooks.py` entries — whitelisted methods are self-registering via Frappe's router

## Patterns & Business Rules

- **Use case**: Government documents require specific item names; alias avoids renaming items permanently in the system
- **`get_alias_map` return shape**: `{"data": {name: display_name, ...}}` — follows project API response convention
- **Fallback chain**: explicit `alias_name` → `alias_field` value on the source record → `""`
- **Enabled guard**: `Alias Supported DocType` must have `is_enabled=1` — disabled configs silently return `{"data": {}}`
- **Meta validation**: `alias_field` is validated via `frappe.get_meta(reference_doctype).has_field(alias_field)` before using in a query — guards against stale Select options
- **Two-query pattern**: one `frappe.get_all()` for source records + one for `Alias Name` rows; O(1) dict lookup in comprehension — no N+1
- **Report usage**: call `get_alias_map("Item")`, then `alias_map.get(row["item_code"], row["item_name"])` per row to get `display_name` column
- **`get_original_display_name` flow**: 2 chained `frappe.db.get_value` calls — first gets `alias_field` from `Alias Supported DocType`, second gets that field's value from the actual record; returns `{"data": value_or_empty_string}`
- **JS dependent field pattern**: when parent Link (`documents`) changes → clear child DynamicLink (`primary_name`) and read-only display field (`original_display_name`); when DynamicLink (`primary_name`) changes → call Python API and set display field
- **JS refresh trigger**: `frm.trigger("primary_name")` in `refresh` event repopulates `original_display_name` when opening existing records (field is read-only so not saved; must re-fetch on every load)

## Constraints

- `Alias Supported DocType.alias_field` — options are populated dynamically from `reference_doctype` meta via JS (`alias_supported_doctype.js`); filter: `Data`, `Small Text`, `Text`, `Long Text`, `Link` types only; stored value is the raw `fieldname` (must match exactly what Python API uses for querying)
- `Alias Supported DocType` has no unique constraint on `reference_doctype` — `frappe.db.get_value()` returns the most recently modified record if duplicates exist
- `get_alias_map` fetches ALL records from `reference_doctype` with no limit — on large doctypes (e.g., Item with 10K+ records) this could be slow; consider adding a `names` filter parameter if needed
- Only `System Manager` has permissions on both alias DocTypes — end-users cannot modify aliases
- `get_supported_doctypes` — LIMIT uses f-string interpolation (not %(param)s) because `start`/`page_len` are already sanitized to int by `@frappe.validate_and_sanitize_search_inputs`; safe to use directly
- `original_display_name` is read-only and **not persisted** — it is populated on every form load via JS `frappe.call`; if Python logic needs this value, must re-fetch via `get_original_display_name`, not read from DB
- Adding `original_display_name` field to `Alias Name` DocType **requires desk action** — cannot hand-edit `alias_name.json`; field must be added via Frappe desk UI then JSON auto-updates

## Dead Ends (searches that found nothing)

- No existing `report/` directory in this app — no Script Reports existed at time of implementation
- No `hooks.py` doc_events for `Alias Name` or `Alias Supported DocType`
- No `api/connect_diagnostics_core/` directory existed before this task — created as part of implementation
