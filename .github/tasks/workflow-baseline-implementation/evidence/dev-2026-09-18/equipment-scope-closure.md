# DEV evidence: Equipment route closure

Date: 2026-09-18  
Target: DEV site `local`  
Bench: `/home/shinon/frappe/connect_diagnostics`  
Host: `dev.erp.connectdiagnostics.local`  
Source commit at verification: `2e80debe7349826a4f950a2d993517a595228f6b` (worktree dirty; commit does not include this slice)

## Route executed

`WF-08 Equipment Assignment/Installation` — closed as `disabled / out of scope`.

This slice does not rename Equipment Assignment into an Asset workflow. Asset Movement and Asset Disposal remain separate routes. Existing Workflow, Workflow State, Workflow Action Master and historical Workflow Action records were not deleted or rewritten.

## Changed files

- `.github/tasks/workflow-baseline-implementation/workflow-route-manifest.json`
  - revision `2026-09-18.workflow-blueprint.3`
  - WF-08 is `disabled`, with no document type or workflow name
- `connect_diagnostics_core/fixtures/workflow.json`
  - removed the Equipment Assignment Workflow fixture
- `connect_diagnostics_core/fixtures/workflow_state.json`
  - removed new-route Equipment Assignment state fixtures
- `connect_diagnostics_core/fixtures/workflow_action_master.json`
  - removed new-route Equipment Assignment action fixtures
- `connect_diagnostics_core/hooks.py`
  - removed Equipment Workflow/State/Action Master from fixture allowlists
- `connect_diagnostics_core/patches.txt`
  - registered `disable_equipment_assignment_workflow`
- `connect_diagnostics_core/patches/v1_0/disable_equipment_assignment_workflow.py`
  - idempotently sets the existing Workflow inactive without deleting records
- `connect_diagnostics_core/patches/v1_0/rollback_disable_equipment_assignment_workflow.py`
  - source rollback restores the prior active flag if the record exists
- `connect_diagnostics_core/patches/v1_0/tests/test_disable_equipment_assignment_workflow.py`
  - verifies write behavior and absent-record idempotency
- workflow fixture tests
  - verify WF-08 disabled and no Equipment Assignment fixture remains

## Migration and configuration result

- Backup created before migration: `/home/shinon/frappe/connect_diagnostics/sites/local/private/backups/20260918_143142-local-database.sql.gz` plus site/public/private file backups.
- First `bench --site local migrate`: passed; patch executed successfully.
- Repeat `bench --site local migrate`: passed; no second patch execution or duplicate mutation.
- Effective DEV Workflow query after migration:

  - `Connect Equipment Assignment Blueprint` / `Asset` / `is_active=0`
  - `Connect Asset Movement Approval` / `Asset Movement` / `is_active=1`
  - `Connect Payment Entry Approval` / `Payment Entry` / `is_active=1`
  - `Connect Stock Transfer Approval` / `Stock Entry` / `is_active=0`

- Equipment Workflow State and Action Master rows remain on DEV as historical/configuration records; no delete was performed.

## Tests and checks run

- `bench --site local run-tests --app connect_diagnostics_core --module connect_diagnostics_core.patches.v1_0.tests.test_disable_equipment_assignment_workflow` — 2 passed
- `bench --site local run-tests --app connect_diagnostics_core --module connect_diagnostics_core.setup.tests.test_workflow_fixture_blueprints` — 4 passed
- `bench --site local run-tests --app connect_diagnostics_core --module connect_diagnostics_core.setup.tests.test_workflow_reset` — 11 passed
- `pre-commit run --all-files` — passed after formatter changes
- JSON parse checks for workflow, state, action master and route manifest — passed
- `git diff --check` — passed

## Pending records inspected

Seven open Workflow Actions remain and were not mutated:

- Material Request: 2
- Purchase Order: 3
- Stock Count: 2

The exact-record inventory is retained for the next route-specific disposition. The two Stock Count records reference the retired model and were not revived or fabricated into a new approval history.

## Not tested in this slice

- Stock Transfer direct or transit business execution, approval, native stock ledger conservation, retry or API bypass
- Stock Item → Asset → immediate expense accounting proof, GL/NBV and reversal
- multi-user maker/reviewer/executor behavior for enabled business routes
- Payment, procurement, payroll, sales and Asset Disposal end-to-end native effects
- UI/browser evidence

## Stock Entry consolidation result

The pre-migration collision was `Connect Emergency Stock Movement Blueprint` active versus `Connect Stock Transfer Approval` inactive. The configuration is now consolidated into one native Workflow; the legacy record remains for history but is inactive. Conditions use native `purpose`, `add_to_transit`, and `outgoing_stock_entry` fields, excluding both transit legs. The server-side before-submit guard protects the same invariant for native/API submit bypasses.

Source snapshot including dirty tracked and untracked paths: `source-snapshot-2026-09-18.txt`.

### Changed files/configuration

- `connect_diagnostics_core/fixtures/workflow.json`: one active native Stock Entry Workflow; direct and emergency transitions are explicit; submit transitions permit maker submission while approval/post/cancel transitions retain `allow_self_approval=0`.
- `connect_diagnostics_core/hooks.py`: added server-side direct-transfer submit guard before native Stock Entry submit.
- `connect_diagnostics_core/api/erpnext/stock_entry_workflow.py`: shared direct-route predicate and bypass validation.
- `connect_diagnostics_core/patches/v1_0/consolidate_stock_entry_workflow.py`: idempotent activation of the canonical Workflow and deactivation of the legacy collision; safe rollback only for the expected consolidated state.
- `connect_diagnostics_core/patches/v1_0/rollback_consolidate_stock_entry_workflow.py`: repository-native rollback entry point.
- `connect_diagnostics_core/patches/v1_0/tests/test_consolidate_stock_entry_workflow.py`: forward/idempotence and non-destructive rollback tests.
- Fixture/reset tests updated for consolidated states, route conditions, and native submit semantics.

### Migration/recovery evidence

- Backup before Stock Entry migration: `/home/shinon/frappe/connect_diagnostics/sites/local/private/backups/20260918_161137-local-database.sql.gz` plus site/public/private file backups.
- First `bench --site local migrate`: passed; consolidation patch executed successfully.
- Repeated `bench --site local migrate`: passed; no duplicate patch execution or configuration flip.
- Effective DEV configuration after migration: `Connect Stock Transfer Approval` / `Stock Entry` / `is_active=1`; `Connect Emergency Stock Movement Blueprint` / `Stock Entry` / `is_active=0`.
- Existing documents remained unchanged: `CD-SE69070001` docstatus 2/cancelled; `SE26050046`, `SE26050047`, `SE26050049` docstatus 1/submitted; `SE26050048` docstatus 0/draft.
- Unit rollback proof passed: rollback reverses only canonical-active/legacy-inactive state and does nothing when state no longer matches.

### Real DEV document evidence

- Direct positive: `SE2569090001` — maker → C-Level Approver → Stock Manager/native submit; final `Stock Transfer Submitted`, docstatus 1.
- Native ledger for `SE2569090001`: source `LAB DAN MAKHAM TIA - CD`, actual_qty `-1`, stock value `-16.82`; target `LAB THAMMASART - CD`, actual_qty `+1`, stock value `+16.82`; no cancelled rows.
- Retry of `SE2569090001` produced no additional Stock Ledger Entry; the original two rows remained.
- Maker separation: native self-approval error was observed; after allowing only submit transitions, maker could submit but could not approve.
- Freeze negative: `SE2569090002` reached `Stock Transfer Approved`/docstatus 0, then native post was blocked by active Stock Counts `PL-STK-20260905-MONTHLY-SIG`, `PL-STK-20260905-YEARLY-SIG`, and `STK-CNT-2026-00003`; no ledger rows were created.
- Non-transfer regression: `SE2569090003` (`Material Issue`) submitted natively with docstatus 1 and created one ledger row, actual_qty `-1`, stock value `-16.82`.
- Transit isolation: focused tests verified native transit outbound (`add_to_transit=1`) and receipt (`outgoing_stock_entry` set) are excluded; no transit posting was opened in this slice.

### Tests/checks

- Stock Entry guard: 4 passed.
- Consolidation patch: 3 passed.
- Workflow fixture blueprint: 4 passed.
- Workflow reset: 11 passed.
- JSON parse, Python compile, `git diff --check`: passed.
- `pre-commit run --all-files`: passed after the final fixture, typed-test, and evidence changes.

### Remaining untested

- Browser/Desk UI evidence and separately permission-restricted unauthorized API calls were not run.
- Transit outbound/receipt native posting effects were intentionally not opened; only route isolation was tested.
- Asset immediate-expense accounting proof remains outside this Stock Entry slice.

No new business-policy question was opened. Pending Workflow Actions not belonging to this route remain preserved and separately tracked.
