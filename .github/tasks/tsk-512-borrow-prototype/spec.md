# TSK-512 Borrow prototype specification

## BORROW-P1 owned files

The implementation worker may add or change only these exact runtime files unless scope is
re-reviewed:

- `connect_diagnostics_core/setup/item.py`: add `allow_borrow` and `borrow_return_policy` definitions.
- `connect_diagnostics_core/setup/tests/test_item.py`: assert field definitions and eligibility setup.
- `connect_diagnostics_core/setup/stock_entry.py`: add Stock Borrow link, movement type, and physical
  receipt evidence fields to Stock Entry, plus Stock Borrow Item link on Stock Entry Detail.
- `connect_diagnostics_core/setup/tests/test_stock_entry.py`: assert exact field definitions.
- `connect_diagnostics_core/setup/document_naming.py`: register the Stock Borrow `SBR` prefix using
  the project Buddhist-year naming contract.
- `connect_diagnostics_core/setup/tests/test_document_naming.py`: assert the registered prefix.
- `connect_diagnostics_core/api/erpnext/item.py`: add Borrow eligibility validation to the existing
  Item validate handler.
- `connect_diagnostics_core/api/erpnext/tests/test_item.py`: focused validation tests.
- `connect_diagnostics_core/api/erpnext/stock_borrow.py`: permission checks, idempotent creation,
  draft builders, receipt gate, and totals rebuild/event handlers.
- `connect_diagnostics_core/api/erpnext/tests/test_stock_borrow.py`: focused service and hook tests.
- `connect_diagnostics_core/connect_diagnostics_stock/doctype/stock_borrow/stock_borrow.json`.
- `connect_diagnostics_core/connect_diagnostics_stock/doctype/stock_borrow/__init__.py`: generated
  by Frappe's `create_init_py` for the new DocType package.
- `connect_diagnostics_core/connect_diagnostics_stock/doctype/stock_borrow/stock_borrow.py`.
- `connect_diagnostics_core/connect_diagnostics_stock/doctype/stock_borrow/test_stock_borrow.py`:
  local.test integration tests.
- `connect_diagnostics_core/connect_diagnostics_stock/doctype/stock_borrow_item/stock_borrow_item.json`.
- `connect_diagnostics_core/connect_diagnostics_stock/doctype/stock_borrow_item/__init__.py`: generated
  by Frappe's `create_init_py` for the new child-DocType package.
- `connect_diagnostics_core/connect_diagnostics_stock/doctype/stock_borrow_item/stock_borrow_item.py`.
- `connect_diagnostics_core/tests/test_utils.py`: register Stock Borrow and its child as self-managed
  test records so Frappe does not traverse unrelated ERPNext dependency fixtures.
- `connect_diagnostics_core/hooks.py`: add only Stock Entry `before_submit`, `on_submit`, and
  `on_cancel` Stock Borrow handlers plus Stock Borrow permission-query/has-permission registrations.

Shared-file edits are serialized under the primary agent. Workflow fixtures, existing Dispatch,
Borrowed Asset Return Inspection, Borrowed Item Resolution, workspace definitions, print formats,
reports, `patches.txt`, and all patch modules are excluded from BORROW-P1. App-owned DocType JSON is
synced by normal migrate and third-party fields are applied by the existing idempotent setup path;
BORROW-P1 adds no data migration.

## Data model

`Stock Borrow` is the business-obligation record. Its item rows retain the Material Request Item
identity and requested quantity. Submitted Stock Entry facts linked to those rows are authoritative
for issued and returned quantities. Stored totals are derived caches rebuilt under a row lock.

The header also preserves `destination_type`, `destination_customer`, `destination_address`,
`expected_return_date`, the resolved employee Borrow Warehouse, and the Company return-hold
warehouse from the source request/configuration. Its naming series is `SBR.YYYY-BE.MM-DATE.####`.

- `Stock Borrow.material_request` is a required unique Link. One submitted Employee Borrow Material
  Request maps to one Stock Borrow containing all eligible request rows.
- `Stock Borrow Item.material_request_item` is a required unique Link within the prototype dataset.
- Creation first locks the Material Request row, then rechecks the unique link, then inserts the
  Stock Borrow and all child rows in the caller transaction. A duplicate-key race returns the
  existing record; any other failure rolls the transaction back.
- Totals rebuilding locks the Stock Borrow row and sums submitted, non-cancelled Stock Entry Detail
  `transfer_qty` for the canonical Stock Borrow Item link and movement type.
- `pending_issue_qty = requested_qty - issued_qty`; business-obligation
  `outstanding_qty = issued_qty - returned_qty`. Neither value is reused for the other's meaning.
- API retries return the existing draft document/link and never create a second obligation or count
  a submitted movement twice.

## MVP item and quantity boundary

BORROW-P1 accepts only Stock Items where `allow_borrow = 1`, `has_serial_no = 0`, and
`has_batch_no = 0`. Requested, issued, returned, and outstanding quantities are stored and compared
in Stock UOM. Material Request `stock_qty` normalizes any request-UOM conversion. Draft builders use
the Item's Stock UOM with conversion factor `1`, so native `transfer_qty` is the authoritative
submitted quantity. Zero/negative quantities,
over-issue, over-return, wrong Item/row links, and source/target warehouse equality are rejected.
Serialized and batched Items remain disabled until the later native identity spike passes.

Prototype movement types:

- `Borrow Outbound`: Material Transfer, source selected by a stock user, target Employee Borrow
  Warehouse.
- `Borrow Exact Return`: Material Transfer, source Employee Borrow Warehouse, target Company return
  hold warehouse, submitted only after physical receipt is recorded.

Each return Stock Entry has read-only `borrow_receipt_confirmed_at` and
`borrow_receipt_confirmed_by` fields. A controlled whitelisted method may set them once while the
document is Draft. It requires write permission on the Stock Borrow and Stock Entry and membership
in `Stock User` or `Stock Manager`. The evidence cannot be cleared through the API. The Stock Entry
`before_submit` hook rejects a Borrow Exact Return without both fields.

Cancellation recomputes the obligation from remaining submitted facts. Users cannot edit issued,
returned, or outstanding totals directly.

## Permissions

- Requesters may create Employee Borrow Material Requests using eligible Stock Items.
- Stock users may prepare and post linked Stock Entries subject to native permissions.
- Stock Borrow grants DocType read/create/write to Stock User and Stock Manager, full access to
  System Manager, and read to Employee. A permission-query hook restricts Employee-role list access
  to `responsible_employee` records mapped to `frappe.session.user`; a matching has-permission hook
  allows only read when that mapping matches. System Manager and users with native Stock Borrow
  permissions retain their role permissions.
- Only controlled server methods may create links, mark physical receipt, or rebuild totals.
- Every whitelisted method checks the specific source/target document permission and validates all
  names and quantities server-side. Stock Entry creation additionally requires native create
  permission on Stock Entry.

## BORROW-P2 exact files

After BORROW-P1 passes and is reviewed, BORROW-P2 may propose changes to these exact surfaces:

- `connect_diagnostics_core/public/js/custom/material_request/doctype.js` and its frontend test, to
  expose Create/Open Stock Borrow only for submitted Employee Borrow requests.
- new `stock_borrow.js`, to expose Prepare Outbound, Prepare Exact Return, and Confirm Physical
  Receipt actions.
- `connect_diagnostics_core/setup/workspace.py` and `setup/tests/test_workspace.py`, using the
  repository workspace-navigation procedure to provide a deliberate Desk home.
- focused local.test integration tests and no workflow-fixture changes.

## Rollback

Before owner adoption, rollback is branch/worktree disposal plus controlled cleanup on `local.test`.
Enumerate prototype records by `Stock Borrow.material_request` and native entries by the required
`Stock Entry.stock_borrow` link. Submitted Stock Entries must be cancelled through native
cancellation and verified absent from active Stock Ledger effects; they are never deleted. Draft
Stock Entries may then be deleted through Frappe document APIs, followed by Stock Borrow records.
Normal migrate removes no schema automatically, so prototype Custom Fields/DocTypes remain on the
test site unless an explicit reviewed cleanup is run. No production cleanup or migration is
authorized.

## Regression boundary

Focused regression commands must cover native Material Request purposes, existing Employee
Borrow/Customer Demo/Customer Loan validation, existing Dispatch tests, and Stock Entry workflow
tests. The prototype is isolated by an unmerged branch and worktree import precedence and is never
enabled on DEV/UAT/production in this task.
