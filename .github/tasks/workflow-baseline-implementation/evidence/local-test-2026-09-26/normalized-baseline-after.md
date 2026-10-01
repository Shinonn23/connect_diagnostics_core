# Normalized workflow baseline — local.test rehearsal

Date: 2026-09-26. Target: Bench `/home/user_2/frappe/connect_diagnostics`, site `local.test` only. Source worktree: `feat/workflow-baseline-checkpoint-20260919` in `worktrees/workflow-baseline-normalization`. No shared DEV/UAT or `local` mutation was authorized.

## Configuration result

- The first migration attempt stopped on an incorrectly transcribed allowlisted predecessor fingerprint before fixture sync. The fingerprint was corrected from the source fixture.
- The second attempt stopped on the exact Material Request retirement fingerprint after creating the recovery snapshot and six empty Payment Entry fields. The incomplete-apply recovery removed those fields and the snapshot, and its postcondition checks passed. Retirement preflight was then moved before mutation.
- The third `bench --site local.test migrate` succeeded; a fourth migrate succeeded without additional normalization. The Patch Log contains `connect_diagnostics_core.patches.v1_0.normalize_workflow_baseline`.
- Exactly ten canonical Workflows are active, one per target DocType. The Material Request and Asset Disposal Workflows are inactive. All ten canonical rows match their shipped fixture fingerprints. Sixty Workflow Transition Tasks containers exist, each with one enabled matching task. No open Workflow Action existed on this test site during the migration checks.
- The private recovery File remains available for an operator-run, fingerprint-guarded rollback. The manifest SHA-256 is `1af0c916bf9d7aa4f8e5071d0039352f9822dbf4fa80673aa3c8e95c51666109`.

## Automated verification

- Focused fixture, migration, recovery, shared-control, route unit, and live integration checks passed after the final route corrections. Examples: Purchase Invoice 14 unit and one live post/cancel test; Asset Movement 36 unit and two live tests; Sales Order two live tests; Payment Entry live fixture/task test; Stock Entry three unit tests. Independent code review reported no P0/P1/P2 finding.
- The user approved a narrow Stock Count compatibility addendum. The Stock Count Adjustment Select now allows the already-written `Stock Reconciliation` value; tests assert draft native documents instead of immediate posting. `bench --site local.test migrate` succeeded after the additive schema change, and all ten focused Stock Count adjustment integration tests passed. No Stock Count Workflow or posting engine was added.
- The pinned pre-commit hooks passed on the changed/untracked files: format, lint, type check, Semgrep, and pip audit.
- The final full app suite passed: 821 unit tests and 91 integration tests, zero failures/errors. Independent schema/code review cleared its rollback-check follow-up; no P0–P2 findings remain.
- Rollback preflight was run read-only and correctly refused to restore `Connect Stock Reconciliation Blueprint`: `local.test` now has documents in that route. No rollback mutation was attempted, and no data was removed to make the rehearsal pass. Unit tests cover rollback fingerprint and incomplete-apply recovery guards.

## Remaining gates

Computer Use acceptance on `dev.erp.connectdiagnostics.test` is blocked at Step 0 in this session. The independent browser tester found no usable desktop browser click/type/screenshot or recording capability; no Chrome profile, actor, document, or route was accessed. All ten routes are therefore **not executed**, not passed. Acceptance must restart from Step 0 in a capable desktop session. Canonical `docs/` must wait until runtime acceptance and independent documentation review. Historical open actions on the separate `local` audit site are unchanged and still require owner disposition before any promotion to that target. An operator must check the child-row count specified in the task addendum before reverting the additive Stock Count Adjustment Select option; any nonzero count or query failure stops that rollback.
