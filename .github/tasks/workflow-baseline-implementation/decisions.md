# Decision and configuration-conflict register

Fixed constraints in `README.md` are not decisions to reopen. A decision is approved only when
the named owner records the chosen policy, revision, effective date, enabled/deferred routes and
impacts. Test constants are not policy.

| ID | Required question | Decision owner | Affected tasks | Status |
| --- | --- | --- | --- | --- |
| D-TARGET | Which bench/site is the authorized implementation and test target, and what mutations are permitted? | Technical owner | Every runtime/config task | Open; `/home/erp/frappe` missing, `local` audit-only |
| D-CORE | What are trusted source/operation/revision/provenance fields and current-state recheck boundary? | Technical + Security | All shared cores/adapters | Approved for the Self-Approval/SoD baseline by `D-CORE-2026-09-26`; domain critical fields remain adapter-owned |
| D-IDENTITY | What business identity defines requester/maker/checker/approver, scopes, delegation, backup, expiry/revocation and self-approval? | Security + all owners | WF-01–17, 531 Core | Approved for the Self-Approval/SoD baseline by `D-IDENTITY-2026-09-26`; delegation and backup approval remain out of scope |
| D-STOCK | What count evidence model, cutoff/reference time, blind-count visibility, exclusions, recount authority and monthly/annual adjustment rules apply? | Stock + Finance | WF-03/04/05 | Open; retired code cannot be chosen |
| D-TRANSFER | Which direct/transit routes, scopes and receipt ordering are enabled? | Stock + Operations | WF-01/02, enabled TSK-512 | Open |
| D-ASSET | Which asset/equipment routes, identity, custody/site and acknowledgement ordering are enabled? | Asset + Operations | WF-06/08, enabled TSK-512 | Open |
| D-ASSET-DISPOSAL | Which sale/scrap/write-off routes, authority, dates, accounts and evidence apply? | Asset + Finance | WF-07 | Open |
| D-SALES | What exposure basis, thresholds, currencies, override authority and critical fields apply? | Sales + Finance | WF-09 | Open |
| D-CREDIT | What distinguishes physical return, price-only credit, retained credit, write-off and refund; what authority/period rules apply? | Sales + Finance | WF-10 | Approved by `D-CREDIT-2026-09-26` |
| D-PROCURE | Are RFQ/direct routes enabled; what supplier evidence, commitment, authority and currency basis apply? | Procurement + Finance | WF-11 | Open |
| D-AP | What supplier-invoice identity, matching tolerances, receipt owner, advance, direct-expense and Is Paid rules apply? | AP + Procurement | WF-12 | Open |
| D-PAYMENT | What voucher matrix, beneficiary/account/currency/amount authority, bank evidence and settlement rules apply? | Finance + Management | WF-10/12/13/14, 529 Core | Open |
| D-PAYROLL | What cutoff, grouping, off-cycle, correction/recovery, privacy and bank-handoff authority apply? | Payroll + Finance | WF-14 | Open |
| CONFIG-PAYMENT | Retain approved site-owned PE Workflow or retire/replace it; who owns desired state and pending records? | Site Configuration Owner + Finance Owner, to be named | WF-13 / task `CONFIG-PAYMENT` | Conflict open; evidence: `evidence/config-payment.md` (not created until owners approve access) |
| CONFIG-DIRTY | Who owns each dirty hooks/fixture/custom/setup/patch change, and which may be edited or discarded? | Repository Technical Owner, to be named | task `CONFIG-DIRTY-OWNERSHIP` | Partially resolved for TSK-590/600 by D-SIGNED-APPROVAL-2026-09-26: preserve all existing dirty work; serialize shared-file integration under the primary agent; all unrelated ownership remains open |
| CONFIG-PENDING | How are 7 open legacy Workflow Actions and their source documents resolved without fabricated history? | Material Request, Purchase Order and Stock business owners, to be named | task `CONFIG-PENDING-ACTIONS` | Conflict open; evidence: `evidence/config-pending-actions.md` (pending authorized investigation) |

## Approved Credit Note decision — 2026-09-26

```text
Decision ID: D-CREDIT-2026-09-26
Owner / approval source: Business-owner approval recorded in the Codex task on 2026-09-26
Approved policy / desired state: Protect native Sales Invoice Credit Notes that represent either a
physical goods return or a price-only credit. Every protected Credit Note must be an unsubmitted
Sales Invoice with is_return=1 and a submitted original Sales Invoice in return_against. Ordinary
Sales Invoices remain outside this route.
Revision: 2026-09-26.credit-note.1
Effective date/timezone: 2026-09-26 / Asia/Bangkok
Physical return: Native Sales Invoice return with stock effects where ERPNext permits update_stock.
Price-only credit: Native Sales Invoice return without stock movement; original invoice reference,
commercial reason, tax and accounting effects remain approval-critical.
Excluded routes: AR write-off and refund execution. A refund, when enabled, is a separate Payment
Entry route; this decision does not authorize payment. Named-user mapping, delegation and custom
posting are excluded.
Actors: Sales User Maker; Sales Manager Reviewer and native Post/Cancel executor; C-Level Approver
Final Approver. Maker, Reviewer and Final Approver must be distinct Users. Native ERPNext cancel
remains the recovery path after submission and is protected by the Sales Manager execution guard.
Period and source rules: Native ERPNext closed-period, return, company, customer, currency, item,
quantity, tax and accounting validation remains authoritative. The adapter adds no period bypass.
Approval evidence: Bind the original invoice identity and current server-read credit-note reason,
posting/accounting/tax/discount/total/item/warehouse facts. Any approval-critical change requires
Return, Resubmit and fresh Review/Approval.
Migration/recovery: Stop on open legacy Workflow Actions, affected pending documents or unrelated
site-owned collision. Never remap/delete/fabricate history. Posted recovery uses native cancel/reversal.
Required evidence: Three-actor UI/API/server parity, Sales User Maker, physical and price-only routes,
ordinary invoice bypass, stale data, direct submit/state spoof, retry, native GL/stock/outstanding and
cancel/reversal tests.
Sign-off: Business policy approved; technical/runtime sign-off pending route implementation.
```

## Approved Self-Approval/SoD identity decision — 2026-09-26

```text
Decision ID: D-IDENTITY-2026-09-26
Owner / approval source: Business-owner approval recorded in the Codex task on 2026-09-26
Approved policy / desired state: The authenticated enabled User is the canonical actor. Maker may
Send for Review and Resubmit, but may not Review or Approve the same protected document. Reviewers
and Final Approvers must be distinct where the route declares three actors. Multiple roles never
erase identity separation. Native Workflow owns transitions; adapters recheck current permission,
state, distinct actors and approval-bound critical data at the final native boundary.
Revision: 2026-09-26.sod-baseline.1
Effective date/timezone: 2026-09-26 / Asia/Bangkok
Trusted identity: Capture maker, reviewer and final approver from frappe.session.user at the
corresponding native transition. Resolve Employee only server-side for active employment and signed
snapshot evidence. Client-editable identity fields are never authority. Generated documents retain
trusted source-document/requester provenance.
Actor contracts: Stock Entry Material Transfer = Stock User / Stock Manager / C-Level Approver;
Stock Reconciliation = Stock User / Stock Manager / Accounts Manager; Asset Movement = Stock User /
Stock Manager / C-Level Approver (the Stock User may also be the asset custodian, but custodian status
alone grants no Workflow role or document permission); manual Journal Entry = Accounts User /
Accounts Manager / C-Level Approver; Sales Order credit approval = Sales User / Sales Manager /
Accounts Manager; Sales Invoice Credit Note = Sales User / Sales Manager / C-Level Approver, with
Sales Manager as Post/Cancel executor; Purchase Order = Purchase User / Purchase Manager / C-Level Approver; Purchase
Invoice = Accounts User / Purchase Manager / Accounts Manager; Payment Entry = Accounts User /
Accounts Manager / C-Level Approver; Payroll Entry = HR User / HR Manager / Accounts Manager.
Execution after approval: The declared execution role may perform the native Post/Submit after a
distinct Final Approver has approved. Post/Submit is execution, not another approval, and must recheck the
approved state and snapshots immediately before the native effect.
Administrator and service identities: Administrator is not a normal business approver and receives
no Self-Approval/SoD bypass. Background/service identities cannot Review or Approve; they may execute
only after complete current approval evidence. Operational recovery is a separate audited path and
does not fabricate approval history.
Included routes: The ten actor contracts above. Journal Entry covers manual entries only. Material
Request is excluded as a protected route but may supply trusted requester provenance to Purchase
Order. Salary Slip remains submit-through-Payroll-Entry only.
Excluded routes: Delegation, Backup Approver, named-user mapping, amount thresholds, system-generated
Journal Entries and any custom posting/state engine.
Required negative evidence: self approval, multi-role self approval, reviewer/final reuse, wrong
role, direct apply_workflow RPC, direct submit/state spoof, permission revocation, stale critical
data and repeated action. Maker Send/Resubmit must remain possible.
Sales Invoice Credit Note route states use the native `Sales Invoice Draft` and `Sales Invoice
Submitted` states because Frappe permits one active Workflow per DocType. The route remains scoped
to return/credit-note invoices; ordinary Sales Invoices retain their direct native submit path,
while the intermediate credit-note review states remain route-specific.
Configuration impact: Protected Review/Approve transitions use allow_self_approval=0. Maker
Send/Resubmit transitions may use allow_self_approval=1. Existing routes are changed only by their
own approved domain branch with collision-aware migration and recovery.
Sign-off: Business policy approved; each domain adapter still requires independent plan/code review,
automated local.test evidence, Computer Use acceptance and final documentation before acceptance.
```

## Approved Self-Approval/SoD core decision — 2026-09-26

```text
Decision ID: D-CORE-2026-09-26
Owner / approval source: Technical implementation decision under the approved
D-IDENTITY-2026-09-26 business policy
Approved policy / desired state: Native Workflow remains the state engine and native ERPNext/HRMS
controllers remain the effect owners. Shared code owns only canonical route declarations, actor
normalization/separation, signed snapshot capture and server-only snapshot-write capability. Domain
adapters own critical payloads, trusted source provenance, locks and final native-boundary guards.
Revision: 2026-09-26.sod-core.1
Effective date/timezone: 2026-09-26 / Asia/Bangkok
Source identity: (doctype, name) plus the adapter's trusted source-document/requester references.
Protected operation identity: declared route, current persisted Workflow state, native action and
authenticated session User. Equal amounts or matching payloads are never operation identity.
Revision binding: A deterministic digest is computed only from freshly server-read, adapter-declared
critical values. Review persists the digest; Final Approval verifies and carries it forward; the
native submit boundary recomputes and compares it. Any mismatch requires Return/Resubmit/Review.
Actor persistence: Maker User is captured at the first native Send for Review. Reviewer and Final
Approver Users and signed Employee snapshots are captured by synchronous native transition tasks.
The transition, state update and snapshot save remain one database transaction.
Snapshot write control: Approval fields are hidden/read-only/no-copy as UI hardening, but adapters
also reject inserted or changed approval fields unless the current document holds an opaque,
request-local object-identity capability minted by the shared server helper for the declared native
transition. API/import/state spoof cannot mint that capability. Direct database/server-console access
is privileged operational access and must never be represented as business approval.
Interactive actor boundary: Protected Review and Approve require a non-Guest, non-Administrator
session, a current HTTP request, the declared role, current document permission, exactly one active
linked Employee and a non-empty approval signature. Background/import/service execution cannot
Review or Approve. Native execution after approval may run synchronously or in the native submission
queue only after the adapter's final persisted-evidence recheck.
Lock and recheck boundary: At each protected transition task and immediately before native submit,
the adapter locks the source document row with FOR UPDATE, rereads persisted Workflow state and
approval fields, and rejects stale state, actor reuse, missing snapshot, permission loss or digest
mismatch. Related domain resources are locked in deterministic order where native invariants require
it. No approval decision is cached across requests.
Idempotency: Native Workflow state/docstatus plus the locked source row reject repeated protected
actions. Native ERPNext/HRMS posting and reversal remain responsible for effect idempotency. If a
domain needs an additional durable operation claim, that adapter stops and replans an app-owned model
instead of adding generic persistence.
Administrator/recovery: Administrator has no protected Review/Approve bypass. Recovery is a separate
audited operational procedure and cannot write or fabricate business approval snapshots.
Required tests: capability forgery and direct field mutation through save/API/import, direct state
spoof, Administrator/Guest/no-request protected actions, background protected action, permission and
role revocation, stale state/digest, duplicate action, transaction rollback, native queued submit and
route-specific generated-document exclusions.
Migration/recovery: Setup-managed fields are additive and idempotent. Route configuration changes
remain collision-aware domain migrations. Rollback removes only unused added fields while exact
expected configuration matches; historical evidence is preserved once referenced by a transaction.
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
