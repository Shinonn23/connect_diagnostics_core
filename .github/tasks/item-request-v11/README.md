# Item Request / Asset Fulfillment v11 — paused checkpoint

Status: **Paused by user request on 2026-09-16 (Asia/Bangkok). Not production-ready.**

The active agents were stopped before this checkpoint was written. No implementation work
may resume until the backlog is re-read, file ownership is reassigned, and the first task's
plan review is confirmed. The frozen business contract is in [spec.md](spec.md), remaining
work is in [backlog.md](backlog.md), and test evidence is in
[verification.md](verification.md).

Commit preparation is also paused: the repository command policy requires interactive approval
for `git add` and `git commit`, while this session has approval prompts disabled. The worktree is
therefore intentionally left unstaged. The proposed checkpoint message is:

```text
chore(item-request): checkpoint v11 implementation
```

## Current product boundary

- Routes are `Stock | Asset`; Equipment is removed from v11.
- Demo is server-routed Asset-first. Stock User never selects route, Asset, warehouse,
  location, batch, or serial.
- A return expected within 30 calendar days and no later than Required By creates one
  request-level choice: `Wait for Return` or `Convert Stock Now`.
- Stock conversion is per physical unit in THB: value below 10,000 uses Material Issue to
  the configured expense account plus a zero-NBV Existing Asset with no depreciation; value
  at or above 10,000 uses Composite Asset plus Asset Capitalization and normal depreciation.
- Accepted Asset release returns to the frozen original internal source. Future-Asset lock
  handoff happens only after accepted QA and physical release.
- The system is greenfield DEV. No legacy migration is required.

## What exists

- App-owned Item Request, Plan, Fulfillment, Obligation, Return, Return Match, technical lock,
  operation, inspection, resolution, and provisioning schemas/controllers are present.
- Approval/decision binding, direct dispatch primitives, receipt primitives, quantity ledger,
  native Asset planner, generated-voucher guards, Stock return kernels, equivalent-return
  kernels, and much of Shipment orchestration exist.
- Equipment routes and the old Equipment module are outside the v11 graph.
- Several focused suites pass, but native end-to-end coverage is incomplete and known P1
  defects remain. Passing unit tests do not make this feature usable yet.

## Known stop-point blockers

1. Provisioning submit still has conflicting Mutation/Physical identity residue and incomplete
   parent-child native lineage protection.
2. The low/high-value provisioning coordinator currently fails before a real native submit
   because of invalid operation grants, state ordering, a high-value argument mismatch, and
   incomplete generated references.
3. Automatic Demo planning has an accepted direction but still needs final plan confirmation
   and implementation of committed A/B/C orchestration.
4. Return aggregate planning is approved, but physical Shipment Return, Asset Return,
   equivalent integration, and named reversals are not implemented end to end.
5. QA/repair/release, terminal resolution, configuration actions, close/reopen, complete API
   surface, Desk actions, clean migrate, full tests, pre-commit, and per-role Desk verification
   remain open.
6. The latest pre-commit attempt failed the repository-wide Semgrep gate; exact findings are
   recorded in `verification.md`.

## Restart rule

Resume with `IR11-F0` in [backlog.md](backlog.md). Do not start Plan, Return, Resolution, or UI
work by editing shared operation/voucher files concurrently. The repository policy permits at
most three spawned agents at once; rotate those slots and preserve exclusive file ownership.
