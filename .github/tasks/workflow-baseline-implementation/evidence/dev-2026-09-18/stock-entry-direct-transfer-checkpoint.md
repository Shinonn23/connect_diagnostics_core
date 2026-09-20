# DEV checkpoint: Stock Entry direct transfer and Freeze control

Date: 2026-09-18  
Target: DEV `local` on `/home/shinon/frappe/connect_diagnostics`  
Equipment evidence: [equipment-scope-closure.md](equipment-scope-closure.md)

## Freeze dependency audit

Before this checkpoint, `SE2569090002` was blocked by `stock_count_freeze.py`, which queried
`tabStock Count`, `tabStock Count Item`, and `tabStock Count Warehouse`. Those three records were
`docstatus=0` active records, so this was a live dependency on the retired Stock Count runtime,
not historical-only evidence. The fixed constraint was violated.

The fix is code/configuration only:

- `hooks.py` now routes every Freeze `before_submit` hook to
  `connect_diagnostics_core.api.erpnext.stock_reconciliation_freeze.validate_transaction`.
- The new guard queries only native `tabStock Reconciliation` and `tabStock Reconciliation Item`
  records with `docstatus=0`, excluding rejected/cancelled workflow states.
- The old Stock Count records were not deleted, mutated, or used to make the test pass.
- Native Stock Reconciliation remains the posting endpoint; no parallel posting path was added.

## Freeze lifecycle and exception boundary

- Activation starts when a native `Stock Reconciliation` is draft (`docstatus=0`), not in
  `Stock Reconciliation Rejected` or `Stock Reconciliation Cancelled`, and its item/warehouse
  scope intersects the transaction. This is the predicate in the SQL guard itself.
- The control ends when the reconciliation is submitted, cancelled, rejected, or no longer
  intersects the transaction scope. The guard therefore does not treat `docstatus=0` alone as
  the complete business explanation; it also evaluates workflow terminal state and scope.
- An exception is executable only for direct `Material Transfer` (no transit outbound and no
  transit receipt), with the exception flag and reason, completed native review evidence, and
  the current native `Post Emergency Stock Movement` transition task in the same request.
  Completed Workflow Action is supporting evidence; it is not itself Approve.
- Reject, stale history after a return/resubmit, spoofed state, changed critical item/warehouse/
  route fields, and transit routes do not satisfy that boundary. There is no broad bypass.

## Cases

| Case | User/role | Document ID | Expected | Actual / ledger-state evidence | Result |
| --- | --- | --- | --- | --- | --- |
| Direct positive | maker `Stock User` → approver `C-Level Approver` → executor `Stock Manager` | `SE2569090001` | Send for Review, approve, native Submit and ledger transfer | `Stock Transfer Submitted`, docstatus `1`; source `-1/-16.82`, target `+1/+16.82` | PASS |
| Native/API bypass | maker `Stock User` | Direct transfer draft from the prior runtime proof | Native Submit without approved state must be rejected | Existing guard unit proof rejects draft state; no accepted direct bypass is claimed | PASS (unit/API guard) |
| Native Freeze block | maker/approver/executor roles | `SE2569090005`; native control `SR2569090003` | Approved route must still be blocked by active native reconciliation | Remained `Stock Transfer Approved`, docstatus `0`; error names `SR2569090003`; ledger `[]` | PASS |
| Retired-reference regression | executor `Stock Manager` | `SE2569090002` | Old Stock Count records must not control runtime | After hook replacement, an attempted replay posted because no native reconciliation existed; native cancel recovery completed; cancellation ledger rows are marked `is_cancelled=1` | DEFECT FOUND → RECOVERED |
| Reject | maker `Stock User` → approver `C-Level Approver` | `SE2569090008` | Reject should end in rejected/docstatus 0 with no ledger | `Stock Transfer Rejected`, docstatus `0`, ledger `[]` | PASS |
| Valid Freeze Exception | maker `Stock User` → approver `C-Level Approver` → executor `Stock Manager` | `SE2569090007` | Native Emergency approval may bypass only the active native reconciliation and then native-submit | `Emergency Stock Movement Pending Review` action completed by `C-Level Approver`; then `Emergency Stock Movement Submitted`, docstatus `1`; source `-1/-16.82`, target `+1/+16.82`; native cancel ended docstatus `2`, all original/cancellation SLE rows `is_cancelled=1` | PASS |
| Invalid Freeze Exception / state spoof | executor `Stock Manager` | `SE2569090006` | State/checkbox/reason alone must not bypass native approval | Server rejected spoofed `Emergency Stock Movement Submitted` with no completed native approval; no ledger | PASS |
| Freeze scope proof (unit/direct only) | transaction guard unit + direct runtime | `SE2569090005`; native control `SR2569090003` | Native reconciliation predicate covers the direct route and is not backed by retired Stock Count | Guard source queries only `tabStock Reconciliation` / `tabStock Reconciliation Item`; 6 unit tests passed; no separate non-transfer runtime case was run | PASS (unit/direct only; non-transfer runtime not claimed) |
| Restricted role action | maker `Stock User` attempting approver action | `SE2569090006` | User without approval role cannot approve | Native `WorkflowTransitionError: Not a valid Workflow Action`; state remained unchanged; no ledger | PASS (server/native workflow proof; Browser not claimed) |
| Role absence (not revocation) | `wf-maker-20260918@example.com` | workflow transition `Approve Emergency Stock Movement` | A user without approver role must not receive the action | Inspected roles exclude `Stock Manager`/`C-Level Approver`; native transition rejected | PASS (role-absence API proof; no role was revoked in this case) |
| Critical-field change after Send for Review | maker `Stock User` | `SE2569090006` | Critical item/warehouse/route changes require resubmission | Server rejected quantity change with `Critical Stock Entry fields cannot change after Emergency review starts.`; persisted state unchanged | PASS |
| Concurrent execution | two executor sessions, both `Stock Manager` | `SE2569090009` | One native posting and no duplicate ledger | One process posted `docstatus 1` with source `-1/-16.82`, target `+1/+16.82`; the concurrent process hit native optimistic-lock `QueryDeadlockError (1020)`; exactly one non-cancelled posting set; native cancel then produced retained `is_cancelled=1` rows | PASS |
| Recovery/reapply | migration operator | DEV configuration | Reapply keeps canonical Workflow, fields, conditions, and native Freeze hook | `bench --site local migrate` passed after field/config changes; second repeated migrate passed; active=`Connect Stock Transfer Approval`, retired collision inactive; fields present in native metadata | PASS |
| Emergency Reject with Completed history | approver role | `SE2569090006` | Completed Workflow Action is supporting evidence only; Reject must not authorize posting | Existing Completed history plus no request-scoped native Post provenance; `is_authorized_freeze_exception()` remained false and no posting was permitted | PASS (unit/source proof; no fabricated history) |
| Stale approval after Return/Resubmit | approval lifecycle | no new document created | A prior Completed action must not authorize a later execution without the current native Post transition | Request-scoped provenance is cleared between calls; stale Completed evidence alone returns false | PASS (unit proof; full Desk/browser Return/Resubmit flow pending) |
| State spoof with prior history | executor role | `SE2569090006` | Prior Workflow Action history plus spoofed state must not post | Native submit guard rejected the spoof; no new SLE | PASS |
| Freeze changed before Execute | maker `Stock User` → approver `C-Level Approver` → executor `Stock Manager` | `SE2569090017`; approved scope included `SR2569090003`; added `SR2569090007` | New Freeze after approval must not be bypassed | Native Post failed with `ValidationError: Emergency Stock Movement must have a completed native approval before posting.`; state remained `Emergency Stock Movement Approved`, docstatus `0`, SLE `[]`; added Freeze was moved to terminal workflow state for recovery | PASS |

## Technical tests

- Native reconciliation Freeze unit tests: 7 passed.
- Stock Entry route/exception guard unit tests: 11 passed.
- Transition-task collision/rollback unit tests: 2 passed.
- API/runtime: native `apply_workflow`, native `Workflow Action`, native `submit`, native `cancel`, and SLE results recorded above.
- Server-method/unit tests are not Browser or authenticated-HTTP evidence. Browser/UI remains **Pending**; independent review remains **Pending**.
- Python compile and static checks were run before this checkpoint; final pre-commit after the
- Python compile, `git diff --check`, and final `pre-commit run --all-files`: passed, including
  SQL-injection semgrep rules.
- `bench --site local migrate`: passed after the hook replacement, exception schema, role
  transition, and provenance hardening; repeated migrate also passed with no patch/configuration flip.
- Recovery/reapply: the accidental native posting on `SE2569090002` was recovered by native
  cancel; cancellation ledger rows are retained and marked cancelled. Reapplying migration kept
  the canonical Stock Entry Workflow active and the native Reconciliation Freeze hook installed.
- Current source-build positive: `SE2569090016` captured the active native Freeze scope during
  approval, passed the native Post transition task, produced SLE `+1/-1` at `16.82`, and was
  natively cancelled to docstatus `2`.
- Current changed-Freeze negative: `SE2569090017` was approved before `SR2569090007` was added;
  the Post transition rejected the scope mismatch and produced no SLE.

## Runtime records preserved

Pending Workflow Actions unrelated to Stock Entry were not modified. The old Stock Count records
remain available for separate historical disposition; they are no longer referenced by the active
Freeze hook.

Source bundle: `source-snapshot-2026-09-18.txt` records this revision; full reviewable source and
diff are in the changed repository files. Browser/UI and independent review remain Pending.
