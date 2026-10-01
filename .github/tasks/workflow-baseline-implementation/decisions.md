# Decision and configuration-conflict register

Fixed constraints in `README.md` are not decisions to reopen. A decision is approved only when
the named owner records the chosen policy, revision, effective date, enabled/deferred routes and
impacts. Test constants are not policy.

| ID | Required question | Decision owner | Affected tasks | Status |
| --- | --- | --- | --- | --- |
| D-TARGET | Which bench/site is the authorized implementation and test target, and what mutations are permitted? | Technical owner | Every runtime/config task | Approved for TSK-602 by `D-TARGET-2026-09-26`; shared DEV/UAT remain excluded |
| D-CORE | What are trusted source/operation/revision/provenance fields and current-state recheck boundary? | Technical + Security | All shared cores/adapters | Approved for the Self-Approval/SoD baseline by `D-CORE-2026-09-26`; domain critical fields remain adapter-owned |
| D-IDENTITY | What business identity defines requester/maker/checker/approver, scopes, delegation, backup, expiry/revocation and self-approval? | Security + all owners | WF-01–17, 531 Core | Approved for the Self-Approval/SoD baseline by `D-IDENTITY-2026-09-26`; delegation and backup approval remain out of scope |
| D-STOCK | What count evidence model, cutoff/reference time, blind-count visibility, exclusions, recount authority and monthly/annual adjustment rules apply? | Stock + Finance | Former WF-03/04/05 | Deferred outside normalized baseline; no Stock Count/recount engine, native Stock Reconciliation only |
| D-TRANSFER | Which direct/transit routes, scopes and receipt ordering are enabled? | Stock + Operations | Stock Entry route | Approved by `D-TRANSFER-2026-09-23`; direct Material Transfer only |
| D-ASSET | Which asset/equipment routes, identity, custody/site and acknowledgement ordering are enabled? | Asset + Operations | Asset Movement route | Approved by `D-ASSET-2026-09-26`; Equipment route excluded |
| D-ASSET-DISPOSAL | Which sale/scrap/write-off routes, authority, dates, accounts and evidence apply? | Asset + Finance | Retired route | Deferred outside normalized baseline; no active Asset Disposal Workflow |
| D-SALES | What exposure basis, thresholds, currencies, override authority and critical fields apply? | Sales + Finance | Sales Order route | Baseline approved by `D-NORMALIZED-ROUTES-2026-09-26`; no threshold/credit engine invented |
| D-CREDIT | What distinguishes physical return, price-only credit, retained credit, write-off and refund; what authority/period rules apply? | Sales + Finance | Sales Invoice route | Baseline approved by `D-NORMALIZED-ROUTES-2026-09-26`; native return/credit-note route only |
| D-PROCURE | Are RFQ/direct routes enabled; what supplier evidence, commitment, authority and currency basis apply? | Procurement + Finance | Purchase Order route | Baseline approved by `D-NORMALIZED-ROUTES-2026-09-26`; Purchase Order is approval boundary |
| D-AP | What supplier-invoice identity, matching tolerances, receipt owner, advance, direct-expense and Is Paid rules apply? | AP + Procurement | Purchase Invoice route | Baseline approved by `D-NORMALIZED-ROUTES-2026-09-26`; native ERPNext owns matching/posting |
| D-PAYMENT | What voucher matrix, beneficiary/account/currency/amount authority, bank evidence and settlement rules apply? | Finance + Management | Payment Entry route | Baseline approved by `D-NORMALIZED-ROUTES-2026-09-26`; advanced bank/settlement policy deferred |
| D-PAYROLL | What cutoff, grouping, off-cycle, correction/recovery, privacy and bank-handoff authority apply? | Payroll + Finance | Payroll Entry route | Baseline approved by `D-NORMALIZED-ROUTES-2026-09-26`; bank handoff remains native/deferred |
| CONFIG-PAYMENT | Retain approved site-owned PE Workflow or retire/replace it; who owns desired state and pending records? | Site Configuration Owner + Finance Owner, to be named | WF-13 / task `CONFIG-PAYMENT` | Route-blocking: retain unchanged until TSK-529 is independently accepted; does not block other routes |
| CONFIG-DIRTY | Who owns each dirty hooks/fixture/custom/setup/patch change, and which may be edited or discarded? | Repository technical owner / TSK-602 integration owner | task `CONFIG-DIRTY-OWNERSHIP` | Resolved for integration by `CONFIG-DIRTY-2026-09-26`; every child worktree is preserved and ports are file-by-file |
| CONFIG-PENDING | How are 7 open legacy Workflow Actions and their source documents resolved without fabricated history? | Material Request, Purchase Order and Stock owners | task `CONFIG-PENDING-ACTIONS` | Migration policy approved by `CONFIG-PENDING-2026-09-26`; production record closure remains owner-blocked |

## Normalized-baseline migration decisions — 2026-09-26

```text
Decision ID: D-NORMALIZED-ROUTES-2026-09-26
Owner / approval source: Normalized-baseline implementation request plus D-IDENTITY-2026-09-26
Approved policy: Exactly ten native business Workflows. Stock Entry covers direct Material
Transfer only. Sales Invoice covers native returns/credit notes only. Journal Entry covers manual
entries only; generated entries remain native drafts and receive no approval bypass. The other
seven routes cover their standard native DocType. Actor roles follow D-IDENTITY-2026-09-26.
No amount, currency, credit, tolerance, bank-settlement, count/recount, delegation, or backup rule
is introduced. Native ERPNext/HRMS permissions, validation, posting, cancel/amend, and reversal
remain authoritative. Advanced domain questions remain deferred and cannot expand this baseline.
Revision/effective date: 2026-09-26.normalized-routes.1 / Asia/Bangkok
```

```text
Decision ID: D-IDENTITY-2026-09-26
Owner / approval source: Business-owner approval recorded in the workflow implementation tasks
Approved policy: The authenticated enabled User is the canonical actor. Maker may Send/Resubmit
but may not Review or Approve the same protected document. Reviewer and Final Approver must be
distinct on three-actor routes; multiple roles do not erase identity separation. Administrator,
Guest, background, and service identities cannot perform protected Review/Approve actions.
Actor source: frappe.session.user, with exactly one active Employee and approval signature resolved
server-side for protected transitions. Client-editable identity fields are never authority.
Excluded: delegation, backup approver, named-user mapping, amount thresholds, and generated
Journal Entry approval routes.
Revision/effective date: 2026-09-26.sod-baseline.1 / Asia/Bangkok
```

```text
Decision ID: D-CORE-2026-09-26
Owner / approval source: Technical implementation decision under D-IDENTITY-2026-09-26
Approved policy: Native Workflow owns state/actions and ERPNext/HRMS controllers own effects.
Shared code owns route declarations, actor separation, signed snapshot capture, and server-only
snapshot-write capability. Each adapter owns critical fields, provenance, row locks, and the final
native-boundary recheck. Review binds a deterministic critical-field digest; approval and native
submit reread persisted state under FOR UPDATE and reject actor reuse, stale data, permission loss,
or digest mismatch. Native state/docstatus supplies idempotency unless a route separately plans an
app-owned durable claim. Recovery never fabricates approval evidence.
Revision/effective date: 2026-09-26.sod-core.1 / Asia/Bangkok
```

```text
Decision ID: D-TARGET-2026-09-26
Owner / approval source: Repository policy plus the normalized-baseline implementation request
Approved target: local.test for automated tests and reversible migration rehearsal;
dev.erp.connectdiagnostics.test for Computer Use after automated gates
Excluded targets: local remains ordinary interactive/audit use; shared DEV/UAT/production receive
no mutation in this task
Revision/effective date: 2026-09-26.normalized-target.1 / Asia/Bangkok
```

```text
Decision ID: CONFIG-DIRTY-2026-09-26
Owner: TSK-602 integration owner
Approved policy: Preserve every dirty child worktree. Integrate only files enumerated in the
reviewed TSK-602 plan. Never reset, broad-merge, or infer acceptance from task prose. Shared
fixtures, hooks, setup, task records, and patches.txt have one serialized integration owner.
Revision/effective date: 2026-09-26.file-by-file-integration.1 / Asia/Bangkok
```

```text
Decision ID: CONFIG-PENDING-2026-09-26
Owner / approval source: Normalized-baseline migration request; record-level closure remains with
the Material Request, Purchase Order, and Stock business owners
Evidence reconciliation: The 2026-09-17 local audit recorded two Material Request, three Purchase
Order, and two Stock Count open Workflow Actions. The 2026-09-26 local.test snapshot has zero open
Workflow Actions. These are different target datasets.
Policy: Material Request and Stock Count records stay under their legacy route until authorized
resolution; Purchase Order records remain on the retained native Purchase Order route. Never
delete, close, migrate, or fabricate an action. On a target with open legacy actions, retain all
referenced configuration/history and block only the affected route. Closed records are
historical-only and remain auditable.
Revision/effective date: 2026-09-26.pending-preservation.1 / Asia/Bangkok
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
