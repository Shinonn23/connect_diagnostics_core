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

## Approved route decision — 2026-09-23

```text
Decision ID: D-TRANSFER-2026-09-23
Owner / backup owner: Siwat Sroisuwan / not assigned
Approved policy / desired state: Direct Material Transfer only. Stock User is Maker, Stock Manager is Reviewer, and C-Level Approver is Final Approver. Maker may Send/Resubmit. Maker may not Review or Approve, and Reviewer may not Final Approve. Review and Approve require signed action snapshots; Return and Reject do not. Emergency Freeze is removed from the active baseline by the baseline migration owner while historical records remain intact. TSK-600/601 shared controls are implemented before TSK-590 wiring and are not duplicated in the Stock Entry adapter.
Revision: 2026-09-23.warehouse-transfer.1
Effective date/timezone: 2026-09-23 / Asia/Bangkok
Enabled routes: Stock Entry purpose = Material Transfer, excluding add_to_transit and outgoing_stock_entry transit legs
Deferred/disabled routes and reason: Native transit legs deferred until receipt/approval ordering is approved; Emergency Freeze, Borrow/Demo, exact-location/WMS, and custom posting are outside this route
Affected existing documents/configuration: Connect Stock Transfer Approval and its normal direct-transfer states/actions; legacy Emergency states/actions require non-destructive TSK-602 disposition
Allowed target and mutation scope: automated tests and migration rehearsal on local.test; Computer Use on dev.erp.connectdiagnostics.test
Dirty-work ownership: Existing dirty Stock Entry route/configuration changes remain TSK-590-owned and must be preserved. TSK-600 may extend the shared declaration/helper and only non-Stock-Entry Workflow rows after TSK-590 writing stops; the primary agent owns the serialized integration. No unrelated dirty file is authorized for modification or discard.
Required permissions/roles/scopes: Stock User Maker, Stock Manager Reviewer, C-Level Approver Final Approver; authenticated server identity and current role/permission recheck
Required tests and evidence: TSK-590 automated matrix, full app tests, pre-commit, independent review, and Computer Use acceptance
Migration/re-run behavior: deterministic and idempotent; do not fabricate or delete Workflow Action, Version, or Timeline history
Collision behavior: stop only the Stock Entry route on an unrelated site-owned collision and obtain owner disposition
Rollback/recovery behavior: restore the prior active configuration from captured evidence; native cancel/reversal owns posted-stock recovery
Business sign-off: approved in Codex task on 2026-09-23
Technical sign-off: pending implementation review
Security/Finance sign-off (if applicable): pending shared-control and runtime review
```

## Approved signed-action decision — 2026-09-26

```text
Decision ID: D-SIGNED-APPROVAL-2026-09-26
Owner / backup owner: Siwat Sroisuwan / not assigned
Approved policy / desired state: Every baseline Approve action for Stock Entry, Stock Reconciliation, Asset Movement, Journal Entry, Sales Order, Sales Invoice Credit, Material Request, Purchase Order, Purchase Invoice, Payment Entry, and Payroll Entry requires a server-resolved active Employee approval signature. Review requires a signature only for Stock Entry. Return, Reject, Submit/Post, and other print events are not made protected by this decision.
Revision: 2026-09-26.signed-approval.1
Effective date/timezone: 2026-09-26 / Asia/Bangkok
Enabled routes: Existing approved or manifest-declared baseline Workflows; Journal Entry declaration/fields only until a separate Journal Entry Workflow is approved
Deferred/disabled routes and reason: Journal Entry transition wiring is deferred because the current manifest has no Journal Entry Workflow; no Workflow may be invented by this cross-cutting slice
Affected existing documents/configuration: Existing compatible *_by, *_at, and *_signature fields; Employee.approval_signature remains the sole signature source
Allowed target and mutation scope: automated tests and migration rehearsal on local.test; Computer Use on dev.erp.connectdiagnostics.test
Required permissions/roles/scopes: Existing Workflow roles and permissions remain authoritative; this decision adds only the signed-action requirement
Required tests and evidence: declaration coverage, server-identity and fail-closed tests, idempotent migration, two Workflow integrations, full app tests, pre-commit, independent review, and Computer Use acceptance
Migration/re-run behavior: additive, collision-checked, deterministic, and idempotent; no duplicate fields or transition tasks
Collision behavior: stop the affected route on an unrelated site-owned field/task conflict and obtain owner disposition
Rollback/recovery behavior: restore only exact configuration owned by this slice; preserve document snapshots and native Workflow Action, Version, and Timeline history
Business sign-off: approved in Codex task on 2026-09-26
Technical sign-off: pending implementation review
Security/Finance sign-off (if applicable): pending implementation and runtime review
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

## Recommended technical defaults for SHARED-531-CORE

These are a proposal for owner approval, not an approved policy:

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

D-CORE owners must accept or amend these defaults. D-IDENTITY owners must still decide the
canonical business identity, missing-scope behavior, correction/reversal self-approval,
delegation timezone/bounds/revocation, multi-role precedence and service identities.

`CONFIG-PAYMENT` may not disable the existing control before its approved replacement is active
and verified. Dirty fixture/setup/patch content may not be synced merely because nobody edits it.
Missing named owners are blockers, not assignments inferred by an agent. Evidence paths above are
reserved contracts and must not be populated with document identifiers or user data without
authorized target access.
