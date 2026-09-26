# Shared slice: TSK-600/601 approval controls

Status: accepted; ready for atomic dependency commit

## Goal

Provide one domain-neutral, fail-closed server contract for approval-critical digests, canonical User
identity, current document permission, distinct protected actors, and required signed Employee action
snapshots. Domain adapters own workflow roles/states, critical payloads, persistence fields, and native
effect boundaries.

The shared module must not import Stock Entry, Asset Movement, or any other domain adapter. It does not
register hooks or workflow tasks and changes no runtime behavior until an approved adapter calls it.

## Exact owned files

- `connect_diagnostics_core/api/frappe/approval_controls.py`
- `connect_diagnostics_core/api/frappe/tests/test_approval_controls.py`
- `.github/tasks/workflow-baseline-implementation/slices/tsk-600-601-shared-approval-controls.md`

No other file may change. In particular this slice does not own `print_actions.py`,
`print_action_fields.py`, `hooks.py`, setup fields, fixtures, patches, migrations, or domain adapters.

## Public contract

- `critical_digest(payload)` returns a deterministic SHA-256 digest of a server-built mapping. It
  canonicalizes with UTF-8 JSON, sorted string mapping keys, compact separators, Unicode preserved,
  and `allow_nan=False`. Lists and tuples are ordered JSON arrays; null, booleans, strings, integers,
  and finite floats retain their JSON types. `Decimal`, `date`, `datetime`, and `time` use explicit
  tagged string objects so they cannot collide with ordinary strings. Non-string mapping keys,
  non-finite floats, sets, Documents, and every unsupported value fail closed. Adapters build payloads
  only from freshly server-read document values and recompute the digest; a client-supplied digest is
  never approval evidence.
- `resolve_user(identity)` accepts a User name or Employee name and returns the canonical enabled User.
  An Employee identity must name an active Employee with non-empty `user_id`; the linked User must
  exist and be enabled. A User identity must exist and be enabled. After resolving the User, more than
  one active Employee linked to that User is ambiguous and fails closed; zero active Employees may be
  resolved for an unprotected maker identity, but signed capture requires exactly one. If the same
  input names both a User and Employee that resolve differently, it fails closed. Empty, disabled,
  inactive, unlinked, unresolved, or ambiguous identities fail closed.
- `require_permission(doc, permission)` calls
  `frappe.has_permission(doc.doctype, ptype=permission, doc=doc, user=frappe.session.user)` and raises
  `frappe.PermissionError` on denial. Administrator/system users receive only the permission result
  Frappe grants them; protected capture still requires distinct identity and a valid signed Employee.
- `require_distinct_actors(maker_identity, actor_identity, previous_identities)` accepts one non-empty
  maker identity, one non-empty actor identity, and an ordered iterable of non-empty prior protected
  identities. It canonicalizes all identities before comparison. Empty values, duplicate prior users,
  a prior user equal to the maker, maker self-approval, actor reuse, and User/Employee aliases that
  resolve to the same User fail closed. The maker is supplied separately and must not be repeated in
  `previous_identities`.
- `capture_signed_approval_actor(doc, maker_identity, previous_identities=(), permission="write")`
  uses only `frappe.session.user` as the current actor, rechecks permission and actor separation,
  requires exactly one active linked Employee with a non-empty approval signature, and returns an
  immutable frozen `SignedApprovalSnapshot` containing `user: str`, `employee: str`,
  `employee_name: str`, `acted_at: datetime`, and `signature: str`. It queries active Employees for
  the canonical current User with a limit of two and requires exactly one row. `acted_at` comes from
  `frappe.utils.now_datetime()`. The signature string is copied verbatim into the snapshot; adapters
  persist the returned scalar values directly in their setup-managed fields so later Employee edits
  cannot change historical evidence. The shared function does not write domain fields or serialize
  the frozen object itself.

Native Workflow owns role/transition authorization. Each adapter additionally rechecks its expected
state/role at its protected native boundary; the shared contract never guesses domain roles.

## Acceptance criteria

- Every function has type hints and user-facing failures use sentence-case `frappe.throw()` messages.
- Digest output is stable across mapping key order and nested sequences.
- User and Employee aliases normalize to one enabled User; disabled/unlinked/ambiguous identities fail.
- Maker, Reviewer, and Approver separation works for mixed User/Employee inputs and multi-role users.
- Permission revocation blocks capture before Employee/signature data is returned.
- Missing, inactive, duplicate-linked, or unsigned Employee blocks capture.
- Snapshot is immutable and uses `frappe.utils.now_datetime()` for deterministic tests.
- Tests use `frappe.tests.UnitTestCase` and cover positive, negative, alias, permission, signature,
  ambiguity, disabled-user, and deterministic-digest cases.
- Focused tests pass on `local.test`; Ruff, type checks for the changed module, and `git diff --check`
  pass; independent code review has no P0/P1 findings.

Reproducible focused gates from Bench `/home/user_2/frappe/connect_diagnostics`:

```text
env PYTHONPATH=/home/user_2/frappe/connect_diagnostics/worktrees/wf-tsk-531-approval-controls bench --site local.test run-tests --module connect_diagnostics_core.api.frappe.tests.test_approval_controls
uvx pre-commit run ruff-check --files connect_diagnostics_core/api/frappe/approval_controls.py connect_diagnostics_core/api/frappe/tests/test_approval_controls.py
uvx pre-commit run ruff-format --files connect_diagnostics_core/api/frappe/approval_controls.py connect_diagnostics_core/api/frappe/tests/test_approval_controls.py
uvx --from ty==0.0.43 ty check --python /home/user_2/frappe/connect_diagnostics/env/bin/python connect_diagnostics_core/api/frappe/approval_controls.py
git diff --check
```

## Integration and ownership

After acceptance, this slice is committed atomically on `feat/wf-tsk-531-approval-controls`.
TSK-521 and TSK-523 stack that exact commit. Stock Entry and Asset Movement adapters persist the
returned snapshot in their own setup-managed fields and supply their own critical payload/state/role
checks. Shared API changes after acceptance require independent compatibility review.

## Acceptance evidence

- Independent plan review: READY after identity, permission, snapshot, digest, and actor semantics were
  made explicit.
- Focused `local.test`: 18/18 tests passed from the dependency worktree.
- Ruff check/format, focused `ty` check, Python compilation, and `git diff --check`: passed.
- Independent code review and re-review: no remaining P0, P1, or P2 findings.
- Scope audit: only this record, `approval_controls.py`, and its focused test file changed; no hook,
  fixture, field, migration, patch, site configuration, or domain adapter was activated.
