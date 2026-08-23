# Connect Diagnostics Core — Frappe Rules

These rules apply to the `connect_diagnostics_core/` app package and supplement the repository
policy in [`../AGENTS.md`](../AGENTS.md).

## App context

- Installed apps are `frappe`, `erpnext`, `erpnext_thailand`, `hrms`, and
  `connect_diagnostics_core`. The required dependencies declared by `hooks.py` are `erpnext`,
  `erpnext_thailand`, and `hrms`; do not assume Healthcare, Education, or E-Commerce exists.
- The stack is Frappe/ERPNext/HRMS `version-16`, Python 3.14, and Node 24.
- Custom fields are code-managed in `setup/*.py` and applied from `after_install` /
  `after_migrate`.
- The development Bench is `/home/erp/frappe`, and the development site is
  `deverp.connectdiagnostics.net`. Run server code with
  `bench --site … console` and `exec(open(f).read(), globals())`.
- Salary Slips are submitted only through Payroll Entry. Never add a direct Salary Slip submit
  path.
- The app owns no Frappe Workflow. Do not enforce approval, review, or verification states from
  global document hooks or recreate app-owned workflows ad hoc. A new workflow starts from a
  written specification and is owned by Frappe Workflow's native states and transitions.
- Auto-numbered transactional and operational DocTypes use
  `[prefix][YY-BE][MM][####]`; the registry is `setup.document_naming`. Month uses the document
  date, alternate series use business fields, and company abbreviations are not prepended.

## Python and Frappe conventions

- Every function signature has type hints. Use `DF` annotations for Document fields and
  `from __future__ import annotations` when needed.
- Prefer `cast()` to narrow Frappe/ERPNext types. An unavoidable type ignore must name a
  specific code and reason, for example `# ty: ignore[unresolved-attribute] - runtime custom
  field (setup/item.py)`; never use a bare ignore.
- Use `frappe.throw()` for user-facing errors: English, sentence case, descriptive, and without
  error codes. Use `frappe.utils.now()` / `frappe.utils.today()` for deterministic tests.
- `frappe.conf[<key>]` is site-scoped. Never read or write the `frappe.conf` object directly,
  and never keep site-specific data in module-level variables; use `frappe.cache()` or the DB.
- Race-prone updates to shared records use `frappe.db.get_value(..., for_update=True)`.
- Hook handlers use `(doc: Document, method: str) -> None`. Imports are ordered stdlib →
  third-party → frappe → local; do not use wildcard or unused imports.
- Python files carry this header:

  ```python
  # Copyright (c) 2026, Siwat Sroisuwan and contributors
  # For license information, please see license.txt
  ```

- The `ty-check` hook uses `../../env/bin/python` by default. CI sets `TY_PYTHON` to the Bench
  interpreter and runs the hook only after Bench installation.

## JavaScript and TypeScript

Declare Frappe globals from `.eslintrc` (`cur_frm`, `frappe`, `locals`, and so on). Keep form
scripts minimal and delegate business logic to whitelisted Python through `frappe.call()`.

## Frappe architecture

- API files live at `api/<system>/<doctype_name>.py`; use `erpnext` for ERPNext DocTypes and
  `frappe` for Frappe core. Whitelisted methods perform `frappe.has_permission()` checks and
  validate all server-side inputs. Register overrides through `override_whitelisted_methods`
  in `hooks.py`; never monkey-patch.
- Whitelisted responses have the immutable shape
  `{"data": <payload|None>, "message": <str>}`. Never return bare strings or lists.
- App-owned DocTypes are code-managed: keep JSON, controllers, tests, and migrations together
  in this repository. Existing third-party DocTypes remain managed through their documented
  Frappe mechanism.
- Every new app Module and user-facing DocType gets a deliberate Desk home in the same change.
  Embed it in an existing ERPNext Workspace/Sidebar or create an independent Module and
  Workspace for a genuinely independent major domain. App-owned Desktop Icons are file-managed
  under `desktop_icon/` and `public/icons/`; never create them in setup code. Regrouping another
  app's icon goes through `setup/workspace.py` via `_save_without_export`.

## Custom fields

- Define fields in `setup/<doctype>.py` (`CUSTOM_FIELDS` / `PROPERTY_SETTERS`) and apply them
  idempotently from `after_install` / `after_migrate`; never create them ad hoc through Desk or
  the console.
- Fieldnames describe their data without `cd_`, `custom_`, or another namespace prefix.
- Renaming or removing a field requires a data-migration patch in `patches/`; every schema
  change requires an idempotent patch and a matching real `rollback_<patch_name>.py`. A code
  reference to a custom field carries a `# ty: ignore` naming its `setup/*.py` source.

## Security and performance

| Area | Rule |
| --- | --- |
| SQL | Parameterized only: `frappe.db.sql("... WHERE name=%s", (name,))` |
| Permissions | Check `frappe.has_permission()` before data access in whitelisted methods |
| Input | Validate all user inputs server-side |
| XSS | Escape dynamic content and use Jinja auto-escaping |
| Secrets | Use site config or environment variables; never hardcode secrets |
| File uploads | Validate file type and size before processing |

Prefer `frappe.db.get_value()` and `frappe.get_all(fields=[…])` over full-document loads. A
loop containing a query needs a documented reason; nested loops with database access are a
review concern. Use idempotent `frappe.enqueue()` jobs with explicit queue, timeout, retry, and
deduplicating `job_id` for long work.

## Generated files

- App-owned `doctype/**/*.json` files are code-managed and may be edited directly, but their
  schema, controller, tests, and migrations must remain consistent.
- Do not directly edit `# begin/end: auto-generated types` blocks or module-level `__init__.py`
  files. Frappe manages those generated artifacts; use the proper Frappe mechanism and commit
  the generated result.

## Schema and migration

Never rename or remove fields from an existing DocType without explicit instruction and a plan.
Adding a required field needs a backfill patch. Test patches against a populated database before
committing, or state that testing is a human verification step. All schema changes require human
review before merge.

## Testing

- New features include tests unless the task explicitly waives them. Minimum coverage is one
  test per hook handler and one per whitelisted API method.
- Import test bases from `frappe.tests`: `UnitTestCase` for isolated/mocked tests and
  `IntegrationTestCase` when a site, DB, metadata, or real Documents are needed. Do not use
  legacy `FrappeTestCase` or bare `unittest.TestCase` for app tests.
- Test documents use descriptive prefixes such as `_Test Registration` and clean up after
  themselves.
- Cover Thai-specific edge cases: address format, THB rounding to 2dp with banker's rounding,
  13-digit tax-ID format and checksum, and Buddhist-year (BE) ↔ Gregorian (CE) conversion.
- Do not pin literal wording, labels, or CSS class names for Desk-editable Print Format
  content. Test structural and security invariants instead; see
  `utils/tests/test_print_formats.py`.
