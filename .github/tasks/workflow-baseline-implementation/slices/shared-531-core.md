# Slice plan: SHARED-531-CORE

Status: contract plan reviewed; runtime module and tests blocked.

## Goal

Define the domain-neutral contract for trusted operation/source identity, revision/provenance,
current authorization, delegation/self-approval, current-state recheck and idempotent execution.
The first accepted phase is contract documentation. Runtime code is added only if approved
decisions prove a cross-domain invariant that native primitives and thin adapters do not own.

## Start gate

- D-TARGET, D-CORE and the required D-IDENTITY fields are approved.
- Exact exclusive files and exclusions are reviewed against current repository patterns.
- Current dependency commits and effective identity/permission configuration are captured.
- A second independent reviewer marks the runtime plan `ready`.

The minimum D-IDENTITY contract required by this core is:

- canonical immutable business-identity key for requester and actor;
- requester/actor/approver relationship and the exact self-approval prohibition;
- scope dimensions and comparison semantics (company, domain, resource, amount/currency where
  applicable), without choosing any domain threshold;
- delegation grantor, delegate, delegated scope and allowed action set;
- effective-from/expires-at boundary and timezone semantics;
- revocation fact and the current-state lookup/lock used at execution time;
- multi-role resolution and precedence when one identity holds conflicting roles;
- audit identity for background/generated actions and the trusted source of that identity.

Domain roles, thresholds, approval levels, fallback persons, currencies, warehouses, accounts and
route enablement are explicitly deferred to domain decisions and adapters.

## Native composition map

- Site-owned Workflow/Workflow Action owns transitions and pending approval actions.
- `frappe.has_permission`, roles and User Permission own native access/scope checks.
- `frappe.get_doc(..., for_update=True)` or the established database `FOR UPDATE` pattern owns
  transaction row locking; weak expiry-based `Document.lock` is not the critical race guard.
- Version and Workflow comments provide source/audit evidence but are not treated as an immutable
  approval or idempotency ledger.
- ToDo assignment may notify/assign work but never grants delegated approval authority.
- Domain adapters own native-document loading, policy values, operation claim/history and the
  first supported native effect.

## Candidate file ownership

No runtime path is approved for editing yet. After decisions demonstrate a missing shared
invariant, the worker may own:

- one narrowly scoped shared-control module under the existing app API/utility convention;
- one dedicated pure-contract unit test module;
- one dedicated integration test module only if the approved target is available;
- this slice evidence section.

Explicit exclusions: `hooks.py`, `patches.txt`, all fixtures/custom exports, setup modules,
migration ordering, retired Stock Count code, domain adapters, site records, and native dependency
source. A serialized integration task owns any later hook/adapter wiring.

## Acceptance criteria

- Authorized and denied scope are deterministic and server-side.
- Requester/approver business identity prevents self-approval across multi-role users.
- Delegation checks scope, effective time, expiry and revocation at execution time.
- Source/revision/provenance mismatch and critical-field change make approval stale.
- Trusted operation identity distinguishes retry from a legitimate same-amount operation.
- Current-state locking prevents double execution; failed work leaves no partial committed fact.
- Correction/history is preserved; no approval or execution history is silently overwritten.
- No stock, GL, AR, AP, asset, payment or payroll side effect is implemented.
- No Workflow/configuration record is created, changed or synchronized.
- Native permission, transition, audit and locking ownership is composed rather than duplicated.
- Core unit tests cannot claim adapter bypass, native transaction or end-to-end coverage.

## Proof

After D-CORE/D-IDENTITY approval, pure tests cover deterministic identity/scope decisions,
self-approval, delegation intervals/revocation, stale revision/digests and operation-key equality.
Concurrency, failed transaction, durable retry and history preservation require an approved
target-backed adapter/claim owner and cannot be simulated into core completion.

## Migration and recovery

Contract phase migration: none. A stateless helper may retain no shared claim/history. If a durable
claim is required, stop and re-plan an app-owned model with idempotent forward/rollback patches.
Before domain wiring, rollback is code rollback only. After a native effect commits, recovery uses
the native reversal route; database rollback does not undo bank/email/external effects.

## Review resolution

Independent review rejected a broad generic `approval_core.py`: it would encode unapproved
identity semantics and duplicate native authorization/Workflow ownership. This file preserves
that finding. Selecting the slice authorizes neither a module nor runtime tests.
