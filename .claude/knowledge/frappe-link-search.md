# Knowledge: Frappe Link Field Search Mechanism

_Last updated: 2026-05-07_

## Key Source Files Read

- `apps/frappe/frappe/__init__.py` — `validate_and_sanitize_search_inputs`, `get_all`, `get_meta`
- `apps/frappe/frappe/desk/search.py` — `search_link`, `search_widget`, `build_for_autosuggest`, `sanitize_searchfield`
- `apps/frappe/frappe/database/database.py` — `get_all`, `get_value`, `pluck` parameter internals
- `apps/frappe/frappe/contacts/doctype/address/address.py` — `address_query` (reference implementation for custom Link search)
- `apps/erpnext/erpnext/controllers/queries.py` — `item_query` (reference implementation, uses `frappe.get_meta` + `get_search_fields`)

---

## `validate_and_sanitize_search_inputs` (frappe/__init__.py)

```python
def validate_and_sanitize_search_inputs(fn):
    def wrapper(*args, **kwargs):
        from frappe.desk.search import sanitize_searchfield
        kwargs.update(dict(zip(fn.__code__.co_varnames, args)))
        sanitize_searchfield(kwargs["searchfield"])
        kwargs["start"] = cint(kwargs["start"])
        kwargs["page_len"] = cint(kwargs["page_len"])
        if kwargs["doctype"] and not db.exists("DocType", kwargs["doctype"]):
            return []
        return fn(**kwargs)
    return wrapper
```

- Converts positional args → kwargs using `fn.__code__.co_varnames` — **function parameter names must match exactly**: `doctype, txt, searchfield, start, page_len, filters`
- Sanitizes `searchfield` against SQL injection (regex whitelist)
- Casts `start` and `page_len` to `int` via `cint()` — safe to use directly in f-string `LIMIT {start}, {page_len}`
- Returns `[]` early if `doctype` doesn't exist in DB
- Does NOT itself check permissions — `@frappe.whitelist()` must be added separately

---

## `search_widget` + `search_link` Flow (frappe/desk/search.py)

Call chain when `set_query({ query: "path.to.fn" })` is used:

```
JS frappe.call("search_link") 
  → search_link() 
  → search_widget()
      → is_whitelisted(frappe.get_attr(query))  ← @frappe.whitelist() required
      → frappe.call(query, doctype, txt, searchfield, start, page_length, filters)
      → returns result of custom fn directly
  → build_for_autosuggest(results, doctype=doctype)
```

- `search_widget` **returns** the custom function's result (does NOT set `frappe.response["results"]` when a query is provided) — the custom function must **return** its data, not set response
- `build_for_autosuggest` processes `res` as `list[tuple]` — uses `item[0]`, `item[1]`, etc. — custom query function must return tuples (from `frappe.db.sql`) not dicts

---

## `build_for_autosuggest` (frappe/desk/search.py)

- Input: `list[tuple]` — e.g. `[("Item",), ("Customer",)]`
- Uses `item[0]` as the `value`, `item[1:]` as description parts
- When `meta.show_title_field_in_link` is set: swaps label/name display
- Output: `list[{"value": ..., "description": ..., "label": ...}]`
- **Cannot handle dicts** — `item[0]` on a dict raises `KeyError`; `frappe.get_all()` results (dicts) will break it

---

## `frappe.get_all` with `pluck` (frappe/database/database.py)

- `frappe.get_all("DocType", filters={...}, pluck="fieldname")` — returns `list[str]` (flat list of that field's values)
- Implemented in `database.py` via `_return_as_iterator` and standard `sql()` pluck path
- Equivalent to: `[row["fieldname"] for row in frappe.get_all(..., fields=["fieldname"])]`
- Available since Frappe v14+; safe to use in this project (Python 3.13, Frappe v15/v16)
- Can be combined with `"in"` filter: `frappe.get_all("User", filters={"email": ["in", emails]}, pluck="email")`

---

## `frappe.db.sql` with `IN` and tuple (PyMySQL behavior)

```python
frappe.db.sql(
    "SELECT name FROM tabDocType WHERE name IN %(names)s",
    {"names": tuple(name_list)},
)
```

- PyMySQL expands `tuple` → `('A', 'B', 'C')` correctly in `IN` clause
- Must convert `list` → `tuple` before passing — `list` is NOT expanded the same way
- Empty tuple `()` causes invalid SQL — guard with `if not list: return []` before the query
- `LIMIT {start}, {page_len}` using f-string is safe when values are already `int` (sanitized by `validate_and_sanitize_search_inputs`)

---

## Standard Hooks in `hooks.py`

- `standard_queries` hook — maps doctype name to a custom search query function path; `search_widget` checks this automatically before checking the `query` param; not used in this project
- `override_whitelisted_methods` — replaces existing Frappe/ERPNext whitelisted endpoints by dotted path; used in this project only for `rename_tool.upload`

---

## Dead Ends

- `address_query` in `frappe/contacts/doctype/address/address.py` calls `search_widget` internally — this looks recursive but is NOT because it passes a different doctype (`"Address"`) with `query=None`, so the inner call takes the default search path
- `frappe.validate_and_sanitize_search_inputs` does NOT add whitelist — both decorators are needed
- `frappe.response["results"]` is NOT set by `search_widget` when a custom `query` is used — the return value is used directly; old Frappe versions may have differed
