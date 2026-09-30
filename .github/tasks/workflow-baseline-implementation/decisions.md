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
| D-STOCK-COMPAT | May the existing native-draft generator's incomplete adjustment metadata/tests be repaired without reopening Stock Count policy or posting behavior? | Stock + Repository Technical Owner | TSK-77 compatibility defect; TSK-527 full-gate unblocker | Approved by `D-STOCK-COMPAT-2026-09-26` below; does not resolve D-STOCK |
| D-TRANSFER | Which direct/transit routes, scopes and receipt ordering are enabled? | Stock + Operations | WF-01/02, enabled TSK-512 | Open |
| D-ASSET | Which asset/equipment routes, identity, custody/site and acknowledgement ordering are enabled? | Asset + Operations | WF-06/08, enabled TSK-512 | Open |
| D-ASSET-DISPOSAL | Which sale/scrap/write-off routes, authority, dates, accounts and evidence apply? | Asset + Finance | WF-07 | Open |
| D-SALES | What exposure basis, thresholds, currencies, override authority and critical fields apply? | Sales + Finance | WF-09 | Open |
| D-CREDIT | What distinguishes physical return, price-only credit, retained credit, write-off and refund; what authority/period rules apply? | Sales + Finance | WF-10 | Open |
| D-PROCURE | Are RFQ/direct routes enabled; what supplier evidence, commitment, authority and currency basis apply? | Procurement + Finance | WF-11 | Approved for PO route by `D-PROCURE-PO-2026-09-26` below |
| D-AP | What supplier-invoice identity, matching tolerances, receipt owner, advance, direct-expense and Is Paid rules apply? | AP + Procurement | WF-12 | Open |
| D-PAYMENT | What voucher matrix, beneficiary/account/currency/amount authority, bank evidence and settlement rules apply? | Finance + Management | WF-10/12/13/14, 529 Core | Open |
| D-PAYROLL | What cutoff, grouping, off-cycle, correction/recovery, privacy and bank-handoff authority apply? | Payroll + Finance | WF-14 | Open |
| CONFIG-PAYMENT | Retain approved site-owned PE Workflow or retire/replace it; who owns desired state and pending records? | Site Configuration Owner + Finance Owner, to be named | WF-13 / task `CONFIG-PAYMENT` | Conflict open; evidence: `evidence/config-payment.md` (not created until owners approve access) |
| CONFIG-DIRTY | Who owns each dirty hooks/fixture/custom/setup/patch change, and which may be edited or discarded? | Repository Technical Owner, to be named | task `CONFIG-DIRTY-OWNERSHIP` | Conflict open; evidence: `evidence/config-dirty-ownership.md` (pending owner) |
| CONFIG-PENDING | How are 7 open legacy Workflow Actions and their source documents resolved without fabricated history? | Material Request, Purchase Order and Stock business owners, to be named | task `CONFIG-PENDING-ACTIONS` | Conflict open; evidence: `evidence/config-pending-actions.md` (pending authorized investigation) |

## Approved Purchase Order decision — 2026-09-26

```text
Decision ID: D-PROCURE-PO-2026-09-26
Owner / backup owner: Siwat Sroisuwan / not assigned
Approved policy / desired state: Purchase Order is the sole procurement approval boundary. RFQ and Supplier Quotation remain optional native upstream evidence, and direct Purchase Order is enabled. Every Purchase Order, regardless of value or transaction currency, follows Purchase User Maker -> Purchase Manager Reviewer -> C-Level Approver Final Approver. The three protected actors must be distinct users; a multi-role user may not collapse or skip a protected step. No Material Request Workflow is introduced.
Revision: 2026-09-26.purchase-order.1
Effective date/timezone: 2026-09-26 / Asia/Bangkok
Enabled routes: Standard ERPNext Purchase Order from native RFQ/Supplier Quotation references and direct Purchase Order
Deferred/disabled routes and reason: Category-specific mandatory sourcing evidence, threshold/currency bypasses, delegation, and named-user exceptions are disabled until a later approved revision; Material Request approval is removed from the canonical baseline by TSK-602
Affected existing documents/configuration: Connect Purchase Order Blueprint; Connect Material Request Blueprint; recorded three Purchase Order and two Material Request open Workflow Actions on shared DEV; existing native RFQ, Supplier Quotation, Purchase Receipt, and Purchase Invoice behavior
Allowed target and mutation scope: implementation, automated tests, and migration rehearsal on local.test; Computer Use on dev.erp.connectdiagnostics.test; shared DEV/UAT mutation stops while affected open Workflow Actions lack record-level owner disposition
Required permissions/roles/scopes: Purchase User Maker, Purchase Manager Reviewer, C-Level Approver Final Approver; current authenticated server identity and current role/permission recheck; Maker, Reviewer, and Final Approver are distinct
Required tests and evidence: native RFQ/Supplier Quotation and direct-PO paths; role/self-approval/multi-role/API/state-spoof denial; commitment-field mutation and re-approval; retry/concurrency; Return/Reject; native cancel/amend, Purchase Receipt/Purchase Invoice references and pending quantities; migration/re-run/recovery; distinct-user Computer Use and Timeline evidence
Migration/re-run behavior: deterministic and idempotent PO-only target; preserve Workflow Action, Version, Timeline, and source-document history; if an affected open PO/MR Workflow Action lacks record-level disposition, stop before changing either Workflow
Collision behavior: stop the WF-11 route on an unrelated active Purchase Order Workflow, changed owned fingerprint, or unresolved affected Workflow Action; never auto-complete, reject, cancel, close, delete, or recreate a pending action
Rollback/recovery behavior: restore captured prior configuration only while the expected post-migration fingerprint matches; recover submitted Purchase Order effects only through native cancel/amend behavior
Business sign-off: approved in Codex task on 2026-09-26
Technical sign-off: pending implementation review
Security/Finance sign-off (if applicable): pending shared-control and runtime review
```

## Approved Stock Count compatibility remediation — 2026-09-26

```text
Decision ID: D-STOCK-COMPAT-2026-09-26
Owner / backup owner: Siwat Sroisuwan / not assigned
Approved policy / desired state: Complete the metadata and integration-test half of the already-present native-draft boundary introduced by workflow checkpoint d4db188. Monthly holding transfers remain native Stock Entry drafts. Yearly adjustments remain one native Stock Reconciliation draft carrying accepted target quantities. Neither path submits, posts stock/GL effects, or gives the retired Stock Count model Workflow/posting ownership.
Revision: 2026-09-26.stock-count-compat.1
Effective date/timezone: 2026-09-26 / Asia/Bangkok
Enabled routes: compatibility persistence of Stock Count Adjustment rows that link a generated native Stock Reconciliation draft; regression verification of the existing monthly native Stock Entry draft path
Deferred/disabled routes and reason: all unresolved D-STOCK count evidence, cutoff, blind-count, exclusions, recount authority, and adjustment policy remain deferred; no new/changed runtime route, Workflow, permission, posting, or shared-DEV behavior is authorized
Affected existing documents/configuration: app-owned Stock Count Adjustment child metadata and its focused integration expectations only; existing Stock Count, Stock Entry, Stock Reconciliation, Stock Ledger Entry, GL Entry, Workflow, and Workflow Action records are read-only evidence during this remediation
Allowed target and mutation scope: on branch feat/wf-tsk-527-procurement-approval from parent feat/workflow-baseline-checkpoint-20260919, the TSK-527 integration owner temporarily owns only stock_count_adjustment.json, test_stock_count_adjustments.py, decisions.md, and the TSK-527 task record to unblock the already-running full-app gate; migrate/test only local.test; no shared DEV/UAT/PROD mutation
Required permissions/roles/scopes: no production permission change; generated drafts retain native Stock Entry or Stock Reconciliation Workflow/permission ownership
Required tests and evidence: source and site metadata allow Stock Reconciliation; monthly Stock Entry is docstatus 0 and linked; yearly native Stock Reconciliation is docstatus 0 in Stock Reconciliation Draft state and linked; accepted target quantities and per-line warehouses are preserved; no Stock Ledger Entry or GL Entry exists for either unsubmitted draft; duplicate/type/docstatus guards remain; focused module, full app, pre-commit, and independent review pass
Migration/re-run behavior: app-owned DocType JSON metadata sync during bench --site local.test migrate is the only migration mechanism; no data patch is required. Before migration, record current field options and distinct persisted adjustment entry_type/link combinations and take a files-inclusive backup. Update the JSON modified timestamp from the site's configured timezone. After the first and repeated migrate, verify the additive option is present, prior rows/links/counts are unchanged, and source/site metadata converge. Clean-install metadata is defined by the same reviewed JSON and its focused metadata assertion.
Collision behavior: stop if the target has an entry_type outside the prior allowlist plus Stock Reconciliation, a Stock Reconciliation adjustment missing its native link, an unexpected metadata owner/source, or concurrent ownership of either implementation file; do not rewrite, delete, submit, cancel, or fabricate any business document
Rollback/recovery behavior: before release, revert the additive JSON/test change through Git. After deployment or after any Stock Reconciliation adjustment row exists, the TSK-527 integration owner must inventory distinct values and linked native documents and obtain a new Stock-owner decision before removal; retain the harmless additive option meanwhile. Never rewrite/delete adjustment rows or linked native documents as rollback.
Business sign-off: approved by the repository owner in the current Codex task on 2026-09-26 with the instruction to continue and fix the discovered Stock Count problem
Technical sign-off: accepted on 2026-09-26 after focused 11/11, full-app 704 unit + 81 integration, repeated-migrate, all pre-commit hooks, and independent review with no P0/P1/P2 findings
Security/Finance sign-off (if applicable): no policy, permission, submission, ledger, or GL change; automated no-effect evidence and independent review required before technical sign-off
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
