# Connect Diagnostics Core — Repository Policy

This is the sole repository-wide policy file. Codex loads it for work in this repository;
the scoped Frappe rules in [`connect_diagnostics_core/AGENTS.md`](connect_diagnostics_core/AGENTS.md)
apply to the app package. Procedural steps live in the repository skills, workflow narrative
lives in [`.github/workflow.md`](.github/workflow.md), final accepted product behavior lives in
[`docs/`](docs/), and active or paused implementation work lives in
[`.github/tasks/`](.github/tasks/). Read the relevant final documentation and active task record
before working in that area.

## Rule priority

When rules conflict, follow this order:

1. **Security** — never compromise on SQL injection, permissions, secrets
2. **Correctness** — working, tested code over pretty code
3. **Backward Compatibility** — do not break existing APIs or data
4. **Style** — formatting, naming, conventions

## Workflow & releases

```
feature work ─PR→ developments ─PR→ user-acceptance-testing ─PR→ production
                  (DEV / default)    (UAT)                       (PROD)
```

- **Branch name:** `<type>/<short-kebab-summary>` (optionally `<type>/<issue#>-<summary>`).
  `type` is one of `feat fix refactor chore style test docs perf build ci revert`; use lowercase
  hyphen-separated names, one logical change per branch and PR, and branch from the intended
  base (`developments` by default). Never use `codex/` or `feature/`; use `feat/`.
- **Commit and PR title:** Conventional Commits, `<type>: <summary>`, kept atomic.
- **Version:** SemVer `0.MINOR.PATCH`; Release Please owns
  `connect_diagnostics_core/__init__.py` and the release manifest. Do not hand-edit either.
  `feat` and pre-1.0 breaking changes bump the minor version; the other recognized change
  types bump the patch version. `revert` and unrecognized types are skipped unless the body
  contains `Release-As:`.
- **Issue ↔ PR:** one issue normally maps to one PR. A PR may reference related issues or
  none (record `None`); use `Refs #<n>`, never `Closes #<n>`.
- **Workflow-baseline decomposition exception:** branches matching `feat/wf-tsk-*` are child
  implementation branches of `feat/workflow-baseline-checkpoint-20260919`. Their PR target is the
  workflow-baseline parent branch, not `developments`; after child integration and full workflow
  validation, the parent branch is merged into `developments`. The canonical mapping is
  [`.github/tasks/workflow-baseline-implementation/branches.md`](.github/tasks/workflow-baseline-implementation/branches.md).

The complete delivery and promotion procedure is [`.github/workflow.md`](.github/workflow.md).

## Working agreement

- If unsure or missing context, do not guess. Verify behavior in the repository, installed
  source, approved specification, or test evidence before proceeding.
- For ordinary technical, implementation, configuration, permission-test, and test-environment
  decisions, resolve uncertainty through the primary agent with explorer/reviewer support and
  choose the smallest clean option that remains inside the approved requirement.
- Before code that touches more than one file or changes existing logic, list every file to
  change, why it changes, and what will not change. The approved task or plan is the approval
  checkpoint; if scope grows, re-propose the complete list.
- Do not create files or add dependencies outside the approved scope.
- Done means the pinned pre-commit command passes, relevant tests pass (or are explicitly
  waived in writing), and the requested change is fully implemented. State any human-only
  verification that remains.

## Multi-agent engineering protocol

The primary agent is the orchestrator, tech lead, integration owner, and single owner of the task
register. It plans the work, assigns bounded ownership, integrates results, and decides when each
gate is satisfied. The repository keeps five specialist roles under `.codex/agents/`:

- `explorer` — read-only source/configuration/framework investigation.
- `worker` — one bounded implementation task with exclusive write ownership and focused tests.
- `reviewer` — independent plan/code/test/security/lifecycle/documentation review.
- `browser_tester` — Computer Use acceptance on the approved DEV environment.
- `doc_writer` — final documentation after runtime acceptance.

Do not create separate architect or UI-test-author roles. Architecture/decomposition belongs to the
primary agent, supported by explorers. If automated browser/UI tests are required, a worker writes
them from the accepted browser evidence.

For substantial engineering work, use this lifecycle:

```text
PLAN
  -> PLAN REVIEW
  -> READY
  -> IMPLEMENT
  -> FOCUSED AUTOMATED TESTS
  -> CODE REVIEW
  -> FIX <-> RE-REVIEW
  -> FINAL AUTOMATED GATES
  -> COMPUTER USE ACCEPTANCE
  -> FINAL DOCUMENTATION
  -> DOCUMENTATION REVIEW
  -> ACCEPTED
```

- A task is substantial when it crosses modules or changes a data model, DocType, hook, permission,
  transaction, migration, workflow, integration, or user-visible behavior with material regression
  risk.
- Before implementation, the primary agent records the goal, bounded scope, acceptance criteria,
  owned files, dependencies, risks, tests, migration/rollback impact, Computer Use coverage, and
  documentation impact. An independent reviewer must mark the plan ready.
- Parallel writers require exclusive file ownership. Read-only explorers/reviewers may inspect any
  file. Serialize work that edits the same file or shared integration surfaces such as `hooks.py`,
  `patches.txt`, setup/configuration exports, and migration ordering.
- No self-approval. The implementing worker cannot be final reviewer. P0/P1 findings block the
  next gate; fixes are re-reviewed.
- Automated tests are the deterministic correctness gate. Computer Use is an end-to-end acceptance
  layer for Desk-visible behavior, workflows, permissions, role handoffs, and visible side effects;
  it never substitutes for automated coverage.
- Local development has two Frappe sites with distinct responsibilities:
  - `local` is the normal interactive development site; its Desk host is
    `dev.erp.connectdiagnostics.local`.
  - `local.test` is the dedicated test site; its Desk host is
    `dev.erp.connectdiagnostics.test`.
  All automated test commands must target `local.test` unless the task explicitly authorizes a
  different site. Do not run automated tests against `local` by default.
- Computer Use acceptance runs only after final automated gates pass. For local development,
  `browser_tester` must use `local.test` through `dev.erp.connectdiagnostics.test`; use
  `dev.erp.connectdiagnostics.local` only for ordinary interactive development/manual inspection.
  Repository access may be local or Remote SSH, but browser/Computer Use runs from the ChatGPT
  desktop host and does not require a GUI browser on the SSH host. If the current Codex host cannot
  use Computer Use or the test Desk host is unreachable from the desktop, the browser tester must
  mark the gate blocked rather than simulate or claim a pass.
- Final documentation runs only after runtime acceptance. `doc_writer` writes current shipped
  behavior under `docs/`; an independent reviewer checks it against accepted code and runtime
  evidence before the task closes.
- Agents may delegate only bounded independent work when a concurrency slot is available. The
  project limit is configured in `.codex/config.toml`; treat it as a shared budget and avoid
  delegation that adds more coordination cost than value.
- **Agent decision protocol:** when a task, test, or blocker raises an ordinary engineering
  question, the primary agent resolves it internally. Gather only the evidence needed, use the
  relevant explorer/worker/reviewer to challenge options, and select the smallest clean solution
  that satisfies the approved requirement. Prefer native Frappe/ERPNext behavior, least privilege,
  minimal code/configuration change, reversibility, low migration risk, deterministic testability,
  and low maintenance cost. Preserve the decision rationale and rollback evidence for later review.
- If an external capability cannot be completed by the agents, such as MFA, CAPTCHA, unavailable
  credentials, or an inaccessible external service, mark that path blocked with complete evidence
  and continue all independent work instead of waiting on that path.

Every specialist reports material transitions to its parent using:

```text
TASK_UPDATE
id: <stable task id>
status: proposed | planning | plan_review | ready | active | blocked | completed | code_review | browser_acceptance | documentation | accepted
owner: <agent role/name>
scope: <bounded goal and owned files>
evidence: <plan, commands, findings, test/browser/doc result>
dependencies: <open or resolved ids>
next: <next concrete action>
blocker: <none or specific blocker>
```

The primary agent updates the task register from these reports. A child must report changed
assumptions, ownership conflicts, or scope expansion before continuing.

## Documentation system

`docs/` is the canonical final product/operations knowledge base. Organize it by module first:

- `docs/<module>/behavior.md` — module-wide invariants, ownership, shared semantics, and boundaries.
- `docs/<module>/<workflow>/README.md` — one accepted workflow/process.
- Add `permissions.md`, `data-model.md`, `integration.md`, or `operations.md` only when the
  workflow is complex enough to need a separate stable reference.

Final documentation describes only accepted current behavior. It must not contain TODOs, task
status, implementation backlogs, agent findings, temporary evidence, branch/commit checkpoints,
speculative future design, or historical working notes. Those belong in `.github/tasks/` while
work is active and in Git/GitHub history after closure. Do not create a permanent task archive in
`docs/`.

## Long-running commands

Run commands expected to exceed 60 seconds in a supervised session that yields output. Report
progress at least every 60 seconds, use a hard timeout of 20 minutes unless a longer timeout is
announced first, and inspect a stalled process instead of rerunning it unchanged.

## Context discovery

Before changing existing behavior, search in order: entry points and overrides; existing APIs
and utilities; installed-source implementations; related migrations; and cross-references in
client scripts, templates, jobs, and tests. Check hooks and scheduled events before changing an
existing function. Reuse existing utilities. If the required behavior still cannot be verified,
route the uncertainty to the primary agent for internal resolution and independent review.

## Print Format rendering

- When inspecting or comparing any Print Format visually, render it through Frappe's native
  Chrome/Chromium PDF renderer with the real site assets, fonts, print media, and document
  settings. Do not use standalone/file-based browser screenshots as the source of truth.
- The DEV Bench must have Frappe's bundled headless Chromium and all runtime libraries listed
  in its `deb.deps` installed before Chrome rendering is considered verified.
- Treat the Frappe `printview`/PDF output as the visual baseline; verify borders, typography,
  assets, pagination, and page dimensions from the actual Desk/site route.

## Reporting discovered issues

Bugs outside the current scope are reported, not fixed or silently commented in place:
`Discovered: <file>:<line> — <description>. Not in scope — file a separate issue if needed.`
Never open issues or send notifications unless asked.

## Security

- Never hardcode secrets or put credentials in source, logs, tests, or documentation.
- Validate external input and escape dynamic output at its rendering boundary.
- Use parameterized queries and least-privilege access in any persistence integration.
- Validate file type and size before processing uploads.
- Treat shell commands, paths, and repository automation as untrusted inputs; avoid broad or
  destructive targets and prefer recoverable operations.

## Performance

Avoid unnecessary full-document loads, N+1 queries, and nested database access. Long-running
work belongs in idempotent background jobs with explicit queue, timeout, retry, and deduplication
settings.

## Anti-patterns

- No hallucinated APIs, guessed business rules, or placeholder code.
- No unnecessary abstractions, dependencies, refactors, or scope creep.
- Do not change signatures, side effects, or execution order while doing a style/refactor task.
- Do not duplicate existing logic or catch and discard exceptions silently.
- When multiple valid architectures exist, resolve them through the agent decision protocol and
  record the selected option plus the reason broader or riskier alternatives were rejected.

## Codex configuration

Trusted project configuration lives under `.codex/`: `config.toml` for project settings and
role registration, `agents/` for the five specialist role contracts, `hooks.json` for deterministic
lifecycle checks, and `rules/` only for destructive-operation safety policy. Normal Git workflow
commands such as staging and committing must not be blocked or approval-gated by repository Codex
rules. Reusable procedures live under `.agents/skills/`. `AGENTS.md` remains the repository-wide
policy source; agent files specialize execution roles and must not contradict it.
