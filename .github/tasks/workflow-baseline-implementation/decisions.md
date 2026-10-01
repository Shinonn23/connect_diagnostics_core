# Decision and configuration-conflict register

Fixed constraints in `README.md` are not decisions to reopen. A decision is approved only when
the named owner records the chosen policy, revision, effective date, enabled/deferred routes and
impacts. Test constants are not policy.

| ID | Required question | Decision owner | Affected tasks | Status |
| --- | --- | --- | --- | --- |
| D-TARGET | Which bench/site is the authorized implementation and test target, and what mutations are permitted? | Technical owner | Every runtime/config task | PI trial route approved on local.test as D-TARGET-PI-TRIAL-2026-09-23; global target decision remains open |
| D-CORE | What are trusted source/operation/revision/provenance fields and current-state recheck boundary? | Technical + Security | All shared cores/adapters | Open |
| D-IDENTITY | What business identity defines requester/maker/checker/approver, scopes, delegation, backup, expiry/revocation and self-approval? | Security + all owners | WF-01–17, 531 Core | Open |
| D-STOCK | What count evidence model, cutoff/reference time, blind-count visibility, exclusions, recount authority and monthly/annual adjustment rules apply? | Stock + Finance | WF-03/04/05 | Open; retired code cannot be chosen |
| D-STOCK-COMPAT | May the existing native-draft generator's incomplete adjustment metadata/tests be repaired without reopening Stock Count policy or posting behavior? | Stock + Repository Technical Owner | TSK-77 compatibility defect; TSK-527 full-gate unblocker | Approved by `D-STOCK-COMPAT-2026-09-26` below; does not resolve D-STOCK |
| D-TRANSFER | Which direct/transit routes, scopes and receipt ordering are enabled? | Stock + Operations | WF-01/02, enabled TSK-512 | Open |
| D-ASSET | Which asset/equipment routes, identity, custody/site and acknowledgement ordering are enabled? | Asset + Operations | WF-06/08, enabled TSK-512 | Open |
| D-ASSET-DISPOSAL | Which sale/scrap/write-off routes, authority, dates, accounts and evidence apply? | Asset + Finance | WF-07 | Open |
| D-SALES | What exposure basis, thresholds, currencies, override authority and critical fields apply? | Sales + Finance | WF-09 | Open |
| D-CREDIT | What distinguishes physical return, price-only credit, retained credit, write-off and refund; what authority/period rules apply? | Sales + Finance | WF-10 | Open |
| D-PROCURE | Are RFQ/direct routes enabled; what supplier evidence, commitment, authority and currency basis apply? | Procurement + Finance | WF-11 | Open |
| D-AP | What supplier-invoice identity, matching tolerances, receipt owner, advance, direct-expense and Is Paid rules apply? | AP + Procurement | WF-12 | Temporary local.test policy approved as D-AP-TRIAL-2026-09-23; production decision remains open |
| D-PAYMENT | What voucher matrix, beneficiary/account/currency/amount authority, bank evidence and settlement rules apply? | Finance + Management | WF-10/12/13/14, 529 Core | Open |
| D-PAYROLL | What cutoff, grouping, off-cycle, correction/recovery, privacy and bank-handoff authority apply? | Payroll + Finance | WF-14 | Open |
| CONFIG-PAYMENT | Retain approved site-owned PE Workflow or retire/replace it; who owns desired state and pending records? | Site Configuration Owner + Finance Owner, to be named | WF-13 / task `CONFIG-PAYMENT` | Conflict open; evidence: `evidence/config-payment.md` (not created until owners approve access) |
| CONFIG-DIRTY | Who owns each dirty hooks/fixture/custom/setup/patch change, and which may be edited or discarded? | Repository Technical Owner, to be named | task `CONFIG-DIRTY-OWNERSHIP` | Partially resolved for TSK-590/600 by D-SIGNED-APPROVAL-2026-09-26: preserve all existing dirty work; serialize shared-file integration under the primary agent; all unrelated ownership remains open |
| CONFIG-PENDING | How are 7 open legacy Workflow Actions and their source documents resolved without fabricated history? | Material Request, Purchase Order and Stock business owners, to be named | task `CONFIG-PENDING-ACTIONS` | Conflict open; evidence: `evidence/config-pending-actions.md` (pending authorized investigation) |

## Temporary Purchase Invoice trial decision — 2026-09-23

```text
Decision ID: D-TARGET-PI-TRIAL-2026-09-23
Owner / backup owner: Siwat Sroisuwan / waived for this reversible local.test-only trial
Approved target: Bench /home/user_2/frappe/connect_diagnostics, site local.test, Desk host
dev.erp.connectdiagnostics.test
Revision: 2026-09-23.pi-trial-target.1
Effective date/timezone: 2026-09-23 / Asia/Bangkok
Permitted mutations: repository changes on feat/wf-tsk-528-ap-payment-handoff; automated test data;
guarded PI fixture/setup/patch migration rehearsal after code review and focused tests; isolated test
users/documents; Computer Use acceptance; deterministic cleanup/recovery on local.test
Excluded targets: local, deverp.connectdiagnostics.net, shared DEV, UAT, production, and every site
not named above
Safety boundary: stop on fingerprint, existing PI, open Workflow Action, metadata, role, pending
document, or recovery-precondition mismatch; do not infer authorization for another route/site
Backup-owner waiver: the route is an isolated reversible test with no production data and an
explicit promotion prohibition. A named backup owner and permanent global D-TARGET decision are
mandatory before UAT/production or any shared-site mutation.
Approval evidence: the task requester explicitly authorized the recommended defaults as temporary
test values and requested a complete working trial system on 2026-09-23.
```

## Temporary Purchase Invoice policy decision — 2026-09-23

```text
Decision ID: D-AP-TRIAL-2026-09-23
Owner / backup owner: Siwat Sroisuwan / waived for this reversible local.test-only trial
Approved policy / desired state: Trial-only Purchase Invoice approval. Accounts User is Maker,
Purchase Manager is Receipt/Source Verifier, and Accounts Manager is Final Accounting Approver.
Maker, Verifier, and Final Approver must be distinct current users. A PI must reference both a
submitted Purchase Order and submitted Purchase Receipt; direct-expense/no-PO and
invoice-before-receipt routes are disabled. ERPNext native previous-document, partial billing,
advance allocation, update-stock, duplicate Supplier Invoice, AP/GL, cancel, and amend semantics
remain authoritative. No custom matching tolerance or duplicate identity is added. PI approval
must not create, submit, or approve a Payment Entry.
Revision: 2026-09-23.pi-trial.1
Effective date/timezone: 2026-09-23 / Asia/Bangkok
Enabled routes: local.test PO + Purchase Receipt + Purchase Invoice trial route only
Deferred/disabled routes and reason: direct expense/no PO, invoice before receipt, Is Paid at PI,
custom tolerance, custom duplicate identity, and all payment execution are deferred for Finance
policy; UAT and production are prohibited until this decision is replaced
Affected existing documents/configuration: Connect Purchase Invoice Blueprint on local.test only;
read-only inventory found no PI documents and no open PI Workflow Actions before implementation
Allowed target and mutation scope: automated tests, guarded migration rehearsal, and Computer Use
on local.test / dev.erp.connectdiagnostics.test only
Required permissions/roles/scopes: Accounts User Maker, Purchase Manager Verifier, Accounts Manager
Final Approver; authenticated current identity, document permission, and distinct-actor recheck
Required tests and evidence: TSK-528 automated matrix, native AP/GL and no-payment evidence, full app
tests, pre-commit, independent review, migration rerun/recovery, and Computer Use acceptance
Migration/re-run behavior: deterministic and idempotent; fail closed on configuration fingerprint,
pending action, document, role, or metadata mismatch; never fabricate/delete audit history
Collision behavior: stop the PI trial route and obtain owner disposition
Rollback/recovery behavior: before acceptance, remove unreleased repository artifacts only; after a
site rehearsal, use only the separately reviewed captured-fingerprint recovery procedure
Mandatory reminder: this is test policy, not Finance sign-off. Replace D-AP-TRIAL with a permanent
D-AP decision before any UAT/production promotion, then remove the visible trial-policy warning.
Business sign-off: trial defaults approved by Siwat Sroisuwan in Codex task on 2026-09-23
Technical sign-off: pending implementation review
Finance/security sign-off: not granted; required before UAT/production
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
