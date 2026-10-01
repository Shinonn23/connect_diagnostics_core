# Decision and configuration-conflict register

Fixed constraints in `README.md` are not decisions to reopen. A decision is approved only when
the named owner records the chosen policy, revision, effective date, enabled/deferred routes and
impacts. Test constants are not policy.

| ID | Required question | Decision owner | Affected tasks | Status |
| --- | --- | --- | --- | --- |
| D-TARGET | Which bench/site is the authorized implementation and test target, and what mutations are permitted? | Technical owner | Every runtime/config task | Open; `/home/erp/frappe` missing, `local` audit-only |
| D-CORE | What are trusted source/operation/revision/provenance fields and current-state recheck boundary? | Technical + Security | All shared cores/adapters | Open |
| D-IDENTITY | What business identity defines requester/maker/checker/approver, scopes, delegation, backup, expiry/revocation and self-approval? | Security + all owners | WF-01–17, 531 Core | Open |
| D-STOCK | What count evidence model, cutoff/reference time, blind-count visibility, exclusions, recount authority and monthly/annual adjustment rules apply? | Stock + Finance | WF-03/04/05 | Open; retired code cannot be chosen |
| D-TRANSFER | Which direct/transit routes, scopes and receipt ordering are enabled? | Stock + Operations | WF-01/02, enabled TSK-512 | Open |
| D-ASSET | Which asset/equipment routes, identity, custody/site and acknowledgement ordering are enabled? | Asset + Operations | WF-06/08, enabled TSK-512 | Open |
| D-ASSET-DISPOSAL | Which sale/scrap/write-off routes, authority, dates, accounts and evidence apply? | Asset + Finance | WF-07 | Open |
| D-SALES | What exposure basis, thresholds, currencies, override authority and critical fields apply? | Sales + Finance | WF-09 | Open |
| D-CREDIT | What distinguishes physical return, price-only credit, retained credit, write-off and refund; what authority/period rules apply? | Sales + Finance | WF-10 | Open |
| D-PROCURE | Are RFQ/direct routes enabled; what supplier evidence, commitment, authority and currency basis apply? | Procurement + Finance | WF-11 | Open |
| D-AP | What supplier-invoice identity, matching tolerances, receipt owner, advance, direct-expense and Is Paid rules apply? | AP + Procurement | WF-12 | Open |
| D-PAYMENT | What voucher matrix, beneficiary/account/currency/amount authority, bank evidence and settlement rules apply? | Finance + Management | WF-10/12/13/14, 529 Core | Open |
| D-PAYROLL | What cutoff, grouping, off-cycle, correction/recovery, privacy and bank-handoff authority apply? | Payroll + Finance | WF-14 | Open |
| CONFIG-PAYMENT | Retain approved site-owned PE Workflow or retire/replace it; who owns desired state and pending records? | Site Configuration Owner + Finance Owner, to be named | WF-13 / task `CONFIG-PAYMENT` | Conflict open; evidence: `evidence/config-payment.md` (not created until owners approve access) |
| CONFIG-DIRTY | Who owns each dirty hooks/fixture/custom/setup/patch change, and which may be edited or discarded? | Repository Technical Owner, to be named | task `CONFIG-DIRTY-OWNERSHIP` | Partially resolved for TSK-590/600 by D-SIGNED-APPROVAL-2026-09-26: preserve all existing dirty work; serialize shared-file integration under the primary agent; all unrelated ownership remains open |
| CONFIG-PENDING | How are 7 open legacy Workflow Actions and their source documents resolved without fabricated history? | Material Request, Purchase Order and Stock business owners, to be named | task `CONFIG-PENDING-ACTIONS` | Conflict open; evidence: `evidence/config-pending-actions.md` (pending authorized investigation) |

## Approved Asset Movement route decision — 2026-09-26

```text
Decision ID: D-ASSET-2026-09-26
Owner / backup owner: Siwat Sroisuwan / not assigned
Approved policy / desired state: Generic native Asset Movement uses Stock User Maker, Stock Manager Reviewer, and C-Level Approver Final Approver. Maker, Reviewer, and Final Approver must be distinct server-resolved users. Review and Approve require signed TSK-600 snapshots and TSK-601 separation-of-duties enforcement. Return and Reject do not change Asset location/custodian. Native Asset-generated Receipt and Cancel operations are exempt only through the reviewed server-only object capability and exact native shape validation; no client-visible field or reference tuple grants a bypass. Every user-created Asset Movement, including intentionally linked Material Request movements, requires approval.
Revision: 2026-09-26.asset-movement.1
Effective date/timezone: 2026-09-26 / Asia/Bangkok
Enabled routes: WF-06 generic ERPNext Asset Movement purposes Issue, Receipt, Transfer, and Transfer and Issue; linked Material Request validation remains an additional constraint
Deferred/disabled routes and reason: WF-08 Equipment Assignment/Installation, Borrow/Demo business workflows, exact-location engines, and Asset Disposal remain outside this baseline
Affected existing documents/configuration: Connect Asset Movement Approval, its Asset Movement states/actions/tasks, setup-managed approval fields, and pending draft Asset Movement documents; historical Workflow Action, Version, Timeline, submitted Asset Movement, and Asset Activity records are preserved
Allowed target and mutation scope: automated tests and guarded migration rehearsal on local.test; Computer Use on dev.erp.connectdiagnostics.test after automated gates
Required permissions/roles/scopes: Stock User Maker, Stock Manager Reviewer/authorized native Submit and Cancel, C-Level Approver Final Approver; current document permission is rechecked server-side at each protected boundary
Required tests and evidence: generic no-MR and linked-MR paths, Return/Reject, self-approval/wrong-role/direct-submit/state-spoof/stale mutation, native Asset Receipt/Cancel, retry/concurrency, multi-Asset native state/history, migration repeat/recovery, full app tests, pre-commit, independent review, and Computer Use acceptance
Migration/re-run behavior: collision-aware, deterministic, and idempotent; do not fabricate or delete Workflow Action, Version, Timeline, Asset Movement, or Asset Activity history
Collision behavior: stop WF-06 on an unrelated active Asset Movement Workflow, incompatible same-name record, conflicting transition task, incompatible setup field, or unresolved pending action and obtain owner disposition
Rollback/recovery behavior: restore the captured prior WF-06 configuration only on the expected post-migration fingerprint; recover submitted movements through native cancel/reversal, never direct Asset writes
Business sign-off: requester confirmed the proposed roles and native Asset Receipt/Cancel exemption in the Codex task on 2026-09-26
Technical sign-off: TSK-523A native-boundary plan, code, migration, and focused integration evidence independently reviewed with no P0/P1 findings; Computer Use acceptance is blocked by unavailable browser capability
Security sign-off: shared TSK-600/601 integration and full route re-review pending
```

## Decision request format

```text
Decision ID:
Owner:
Approved policy / desired state:
Revision and effective date:
Enabled routes:
Deferred/disabled routes and reason:
Affected existing documents/configuration:
Required tests and sign-off:
```

## Historical SHARED-531-CORE proposal

This proposal predates and is superseded for TSK-602 by D-CORE-2026-09-26 and
D-IDENTITY-2026-09-26. It remains only as historical rationale:

- compose native Workflow/Workflow Action for site-owned transition state and approval queues;
- compose `frappe.has_permission` and User Permission for current document/scope access;
- use `frappe.get_doc(..., for_update=True)` or the established database `FOR UPDATE` pattern at
  the protected transaction boundary; do not use expiry-based `Document.lock` as a race guard;
- use native Version and Workflow comments as source/audit evidence, without treating them as an
  immutable approval ledger;
- canonical operation identity is `(source_system, source_doctype, source_name,
  source_revision, action, operation_id)`; amount is never an idempotency key;
- bind an approval snapshot to source identity/revision/action, critical-field digest,
  provenance digest, requester identity and approval time; any mismatch is stale;
- recheck current authorization/state immediately before the adapter's first native effect;
- do not create shared persistence in the first slice. A domain adapter supplies its atomic
  operation claim/history, or the task stops and re-plans an app-owned schema with migration;
- ToDo assignment is notification/work assignment, not delegated approval authority.

Any behavior beyond the approved normalized route/core/identity decisions requires a new decision;
delegation and backup approval remain excluded.

`CONFIG-PAYMENT` may not disable the existing control before its approved replacement is active
and verified. Dirty fixture/setup/patch content may not be synced merely because nobody edits it.
Missing named owners are blockers, not assignments inferred by an agent. Evidence paths above are
reserved contracts and must not be populated with document identifiers or user data without
authorized target access.
