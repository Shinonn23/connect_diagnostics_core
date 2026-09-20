# Connect Diagnostics Core — Frappe Rules

These rules apply to the `connect_diagnostics_core/` app package and supplement the repository
policy in [`../AGENTS.md`](../AGENTS.md).

## App context

- Installed apps are `frappe`, `erpnext`, `erpnext_thailand`, `hrms`, and
  `connect_diagnostics_core`. The required dependencies declared by `hooks.py` are `erpnext`,
  `erpnext_thailand`, and `hrms`; do not assume Healthcare, Education, or E-Commerce exists.
- The stack is Frappe/ERPNext/HRMS `version-16`, Python 3.14, and Node 24.
- Customizations on third-party DocTypes are code-managed from `setup/*.py`. Define Custom Fields
  and Property Setters in the relevant setup module and apply them idempotently from the app's
  install/migrate configuration path. Follow the existing fieldnames used by this project; do not
  add a `custom_` prefix merely because the field is a Custom Field.
- Shared/remote DEV uses Bench `/home/erp/frappe` and site `deverp.connectdiagnostics.net`.
- Local development uses Bench `/home/shinon/frappe/connect_diagnostics` with two sites:
  - `local` — normal interactive development; Desk host `dev.erp.connectdiagnostics.local`.
  - `local.test` — dedicated automated/UI acceptance test site; Desk host
    `dev.erp.connectdiagnostics.test`.
- Run automated tests only against `local.test` by default, for example
  `bench --site local.test run-tests --app connect_diagnostics_core`. Do not use `local` for test
  runs unless the task explicitly requires it.
- Use `local.test` for local Computer Use/browser acceptance as well. `local` is for ordinary
  development and manual inspection. Run server inspection with `bench --site <site> console` and
  `exec(open(f).read(), globals())` against the site appropriate to the task.
- Salary Slips are submitted only through Payroll Entry. Never add a direct Salary Slip submit
  path.
- The app may ship explicit, reviewed, filtered fixtures for native `Workflow`, `Workflow State`,
  and `Workflow Action Master` records only when every record belongs to an approved named route
  and appears in that route's configuration manifest. These are declarative configuration
  artifacts: they do not authorize a target, grant permissions, assign approvers or delegated
  authority, or perform posting effects.
- Every Workflow fixture set requires an approved specification and revision, an exact allowlist,
  configuration owner, target and route scope, collision policy, deterministic migrate/re-run
  behavior, recovery plan, and independent validation. Fixture sync must not silently overwrite,
  disable, delete, or repurpose an existing site-owned record; unresolved collisions stop the
  change for owner disposition. Do not create or modify business Workflow records through ad hoc
  setup, startup, hooks, or runtime code.
- Native Frappe Workflow owns transitions and Workflow Action owns pending actions. ERPNext/HRMS
  controllers remain the only owners of posting and transaction effects. Do not introduce a
  Salary Slip Workflow, a parallel posting engine, or retired Stock Count code; Salary Slips remain
  submit-through-Payroll-Entry only and native Stock Reconciliation remains the stock-count
  posting endpoint. This exception does not change the `setup/*.py` ownership of third-party
  Custom Fields/Property Setters or permit arbitrary fixture doctypes.
- Auto-numbered transactional and operational DocTypes use
  `[prefix][YYYY-BE][MM-DATE][####]`; the registry is `setup.document_naming`. The Buddhist year
  and month use ERPNext Thailand's document-date resolution, alternate series use business fields,
  and company abbreviations are not prepended.

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

## Documentation impact

- A change to accepted module-wide behavior updates `docs/<module>/behavior.md` after runtime
  acceptance. A change to an accepted workflow/process updates `docs/<module>/<workflow>/`.
- Final docs describe current shipped behavior only. Do not copy task backlog, TODOs, temporary
  evidence, review findings, or unimplemented design from `.github/tasks/` into `docs/`.
- Documentation is the last implementation gate: automated checks and required Computer Use
  acceptance pass first, then `doc_writer` updates canonical docs and an independent reviewer
  verifies them against the accepted implementation.

## Custom fields

- Custom Fields and Property Setters on third-party DocTypes are owned by the relevant
  `setup/*.py` module. Use the project's established setup helpers such as
  `create_custom_fields` / `make_property_setter` where appropriate, and make every setup
  operation idempotent so repeated install/migrate runs converge safely.
- Keep field definitions, Property Setters, tests, and runtime references in the same logical
  change. New fieldnames follow the project's domain naming; they do **not** require Frappe's
  `custom_` prefix.
- Do not maintain the same third-party field simultaneously in `setup/*.py` and exported
  `custom/*.json`. Setup code is the source of truth unless a task explicitly establishes a
  different mechanism for a specific DocType.
- Native fields generated by ERPNext features remain native. For example, Department and Territory
  Accounting Dimension fields are generated/maintained by ERPNext; keep the Accounting Dimension
  records in `fixtures/accounting_dimension.json` rather than creating duplicate Custom Fields.
- App-owned DocTypes keep their fields in the DocType JSON.
- Renaming or removing an existing field requires an idempotent data-migration patch and matching
  rollback where the repository migration policy requires one. Update setup definitions and all
  code/test references in the same change.
- When static typing cannot see a runtime field, a targeted `# ty: ignore[unresolved-attribute]`
  must name the owning setup module/reason; never use a bare ignore.

## Security and performance

| Area         | Rule                                                                      |
| ------------ | ------------------------------------------------------------------------- |
| SQL          | Parameterized only: `frappe.db.sql("... WHERE name=%s", (name,))`         |
| Permissions  | Check `frappe.has_permission()` before data access in whitelisted methods |
| Input        | Validate all user inputs server-side                                      |
| XSS          | Escape dynamic content and use Jinja auto-escaping                        |
| Secrets      | Use site config or environment variables; never hardcode secrets          |
| File uploads | Validate file type and size before processing                             |

Prefer `frappe.db.get_value()` and `frappe.get_all(fields=[…])` over full-document loads. A
loop containing a query needs a documented reason; nested loops with database access are a
review concern. Use idempotent `frappe.enqueue()` jobs with explicit queue, timeout, retry, and
deduplicating `job_id` for long work.

## Generated files

- App-owned `doctype/**/*.json` files are code-managed and may be edited directly, but their
  schema, controller, tests, and migrations must remain consistent.
- Third-party Custom Fields and Property Setters are code-managed in `setup/*.py`; do not create
  a parallel exported `custom/*.json` source for the same customization unless an explicit task
  requires that mechanism.
- `fixtures/accounting_dimension.json` is the source of truth for the app's Department and
  Territory Accounting Dimension records. Their generated document fields are owned by ERPNext.
- Whenever a Frappe JSON schema is changed, update its top-level `modified` value in the same
  change. Use the current Frappe system timezone (`System Settings.time_zone`, verified with
  `bench --site <site> execute frappe.utils.get_system_timezone`) and the format
  `YYYY-MM-DD HH:MM:SS.ffffff`; do not leave a stale timestamp or use the developer machine's
  local timezone implicitly.
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
