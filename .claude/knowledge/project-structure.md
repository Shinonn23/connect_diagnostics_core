# Knowledge: Project Structure

_Last updated: 2026-05-07_

## Key Files

- `connect_diagnostics_core/hooks.py` — all entry points: `doc_events`, `override_whitelisted_methods`, `fixtures`, `required_apps`
- `connect_diagnostics_core/api/erpnext/` — hook handlers for ERPNext doctypes (customer, employee, employment_type)
- `connect_diagnostics_core/api/frappe/` — hook handlers for Frappe core doctypes (contact)
- `connect_diagnostics_core/api/connect_diagnostics_core/` — whitelisted APIs for this app's own doctypes (created 2026-05-07)
- `connect_diagnostics_core/master_data/` — master data verification logic (comparator, mapper, reporter, client)
- `connect_diagnostics_core/tests/` — integration tests (test_master_data_verify.py, test_employee_autoname_format.py)
- `connect_diagnostics_core/cd_stock/custom/*.json` — custom field definitions for Item, Item Barcode, Item Group
- `connect_diagnostics_core/fixtures/property_setter.json` — fixtures exported via hooks.py

## Installed Apps (from hooks.py)

- `frappe` — core framework
- `erpnext` — ERP logic
- `erpnext_thailand` — Thai-specific extensions (required)
- `hrms` — HR module (required)
- `connect_diagnostics_core` — this app

## Module Layout Convention

```
api/<system>/<doctype_name>.py
```
- `<system>` = `erpnext` for ERPNext doctypes, `frappe` for Frappe core, `connect_diagnostics_core` for this app's own doctypes
- No `__init__.py` required — Frappe resolves modules by filesystem path (namespace packages)
- All `api/` files referenced by full dotted path in `hooks.py` or `override_whitelisted_methods`

## hooks.py Active Entries (as of 2026-05-07)

```python
required_apps = ["erpnext", "erpnext_thailand", "hrms"]

doc_events = {
    "Customer": {"autoname": "connect_diagnostics_core.api.erpnext.customer.autoname"},
    # Employee and Employment Type hooks exist but are commented out
}

override_whitelisted_methods = {
    "erpnext.utilities.doctype.rename_tool.rename_tool.upload": "connect_diagnostics_core.api.erpnext.rename_tool.upload",
    "frappe.core.doctype.rename_tool.rename_tool.upload":       "connect_diagnostics_core.api.erpnext.rename_tool.upload",
}

fixtures = [
    {"doctype": "Property Setter", "filters": [["module", "=", "Connect Diagnostics Core"]]},
]

export_python_type_annotations = True
```

## Scheduler, Auth, Web Hooks

- **All commented out** — no scheduled tasks, no before_request/after_request hooks active as of 2026-05-07

## Custom Fields

- Defined in `cd_stock/custom/*.json` (managed by Frappe desk, never hand-edited)
- Prefix: `cd_` on all custom field names
- Current files: `item.json`, `item_barcode.json`, `item_group.json`
- Reference in code with: `# ty: ignore[unresolved-attribute] - runtime-injected custom field (cd_stock/custom/item.json)`

## Dead Ends

- No `utils.py` at app root — no shared utility module exists
- No `report/` directory — no Script Reports existed as of 2026-05-07
- No `patches/` directory checked — not explored this session
