# Knowledge: API & Hook Patterns

_Last updated: 2026-05-07_

## Key Files (Reference Implementations)

- `connect_diagnostics_core/api/connect_diagnostics_core/alias_name.py` — `get_supported_doctypes` (Link search query pattern) + `get_alias_map` (report utility pattern)

- `connect_diagnostics_core/connect_diagnostics_core/doctype/rename_tool_v2/rename_tool_v2.py` — whitelisted method pattern (`@frappe.whitelist`, permission check, `frappe.enqueue`)
- `connect_diagnostics_core/api/erpnext/customer.py` — doc_events `autoname` hook pattern
- `connect_diagnostics_core/api/erpnext/employee.py` — `autoname` + `validate` hooks, Thai date logic, private helpers
- `connect_diagnostics_core/master_data/comparator.py` — `@dataclass` return types, `cast(list[dict], frappe.get_all(...))` pattern
- `connect_diagnostics_core/master_data/mapper.py` — `frappe.get_meta()` field validation pattern

## Whitelisted Method Pattern

```python
# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations
from typing import cast
import frappe

@frappe.whitelist()
def my_method(param: str) -> dict[str, ...]:
    if not frappe.has_permission(param, "read"):
        raise frappe.PermissionError
    # ... logic ...
    return {"data": <payload>}
```

- No `hooks.py` entry needed — Frappe auto-discovers `@frappe.whitelist()` via router
- `override_whitelisted_methods` in `hooks.py` is ONLY for replacing existing Frappe/ERPNext endpoints
- Whitelisted methods can live in any `.py` file, including doctype controller files

## API Response Shape (mandatory)

```python
return {"data": <payload>}           # with data
return {"data": {}, "message": "..."}  # with optional human-readable status
```
- `data` key always present; value is `dict`, `list`, or `None`
- Never return raw strings or bare lists from whitelisted methods
- Existing response shapes are immutable — changing them is a breaking change

## Hook Handler Signature

```python
def autoname(doc: SomeDocument, _method: str) -> None: ...
def validate(doc: SomeDocument, _method: str) -> None: ...
```
- Always typed with the specific Frappe/ERPNext document class (import from source)
- `_method` prefix on unused parameter to satisfy linter

## Type Annotation Conventions

- `cast(str, frappe.db.get_value(...) or "")` — narrow DB result + collapse None to ""
- `cast(list[dict], frappe.get_all(...))` — narrow get_all return
- Custom fields: `# ty: ignore[unresolved-attribute] - runtime-injected custom field (cd_stock/custom/item.json)`
- Never bare `# type: ignore` — must include error code and reason

## Query Patterns

```python
# Single field from one record (filtered)
value = frappe.db.get_value("DocType", {"field": val, "flag": 1}, "target_field")

# Multiple records, specific fields only (no full doc loads)
rows = frappe.get_all("DocType", filters={"key": val}, fields=["name", "field1"])

# Single value from list
names = frappe.db.sql_list("SELECT name FROM tabDocType WHERE ...")
```

- Always use `fields=[]` in `frappe.get_all()` — never omit (returns all fields if omitted)
- Validate dynamic field names against `frappe.get_meta(doctype).has_field(field)` before querying

## Link Field Search Query Pattern (custom `set_query`)

เมื่อต้องการจำกัด options ของ Link field ด้วย server-side logic ที่ซับซ้อน:

**Python** — ต้องมีทั้งสอง decorator, signature ตายตัว, คืน list of tuples:
```python
@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def my_query(doctype, txt, searchfield, start, page_len, filters) -> list:
    # start, page_len ถูก sanitize เป็น int แล้วโดย decorator
    return frappe.db.sql(
        f"SELECT name FROM tabFoo WHERE ... LIMIT {start}, {page_len}",
        {"txt": f"%{txt}%"},
    )
```

**JavaScript** — ใช้ใน `refresh` event:
```javascript
frm.set_query("field_name", function() {
    return { query: "app.module.path.function_name" };
});
```

**Key facts:**
- `@frappe.validate_and_sanitize_search_inputs` sanitizes `searchfield` (SQL injection guard) + casts `start`/`page_len` to int — ไม่ต้องทำเอง
- Function ต้อง return list of tuples `[(name,), ...]` — `build_for_autosuggest` ใน Frappe expect tuples (`item[0]`, `item[1]`, ...)
- `frappe.get_all(..., pluck="fieldname")` — คืน `list[str]` flat list สะดวกสำหรับ IN clause
- `is_whitelisted()` ถูก check ก่อน call — `@frappe.whitelist()` จำเป็นต้องมี
- `IN %(supported)s` กับ `tuple` ใน PyMySQL — ขยายเป็น `IN ('A', 'B', ...)` ถูกต้อง; ต้อง convert list → tuple ก่อน
- Source อ้างอิง: `frappe/desk/search.py` (`search_widget`, `build_for_autosuggest`), `frappe/contacts/doctype/address/address.py` (`address_query`), `erpnext/controllers/queries.py` (`item_query`)

## Dynamic Select Field Options (JS form script)

เมื่อ Select field ต้องการ options ที่ขึ้นกับ field อื่น:
```javascript
frappe.model.with_doctype(frm.doc.reference_doctype, function() {
    const meta = frappe.get_meta(frm.doc.reference_doctype);
    const fields = meta.fields
        .filter(f => ALLOWED_TYPES.includes(f.fieldtype) && !f.hidden && f.label)
        .map(f => f.fieldname);
    frm.set_df_property("select_field", "options", ["", ...fields]);
    frm.refresh_field("select_field");
});
```
- `frappe.model.with_doctype(doctype, cb)` — async meta loader; ensures meta cached ก่อน `frappe.get_meta()`
- ต้อง trigger event ใน `refresh` ด้วย เพื่อ repopulate เมื่อเปิด form ที่ save ไว้แล้ว
- Clear dependent field เมื่อ parent field ถูก clear เพื่อป้องกัน stale value

## Background Job Pattern (from rename_tool_v2.py)

```python
frappe.enqueue(
    method=bulk_rename,
    queue="long",
    doctype=select_doctype,
    rows=rows[i : i + 500],
)
```
- Always set `queue` explicitly
- Use `job_id` to prevent duplicate enqueues

## Thai-Specific Logic (employee.py)

- Buddhist year: `thai_year_4 = str(gregorian_year + 543)`
- Employee autoname pattern: resolves from `Employment Type.custom_format` if set, else falls back to `{YY}{MM}.###`
- Token replacement: `{YYYY}`, `{YY}`, `{MM}`, `{DD}` in format strings

## Custom Field Access Pattern

```python
# Accessing runtime-injected custom fields:
doc.custom_dksh_customer_code  # ty:ignore[unresolved-attribute] - runtime-injected custom field
doc.get("custom_field_name")   # safe alternative using dict-style access
```

## Dead Ends

- No `frappe.cache()` usage found in this app as of 2026-05-07 (pattern exists in master_data/client.py for external calls)
- No `frappe.enqueue` with `job_id` found — bulk rename uses bare enqueue
