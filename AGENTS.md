# Connect Diagnostics Core — Repository Policy

This is the sole repository-wide policy file. Codex loads it for work in this repository;
the scoped Frappe rules in [`connect_diagnostics_core/AGENTS.md`](connect_diagnostics_core/AGENTS.md)
apply to the app package. Reusable procedures live in repository skills, GitHub Actions live in
[`.github/workflows/`](.github/workflows/) with the reusable change-scope action under
[`.github/actions/change-scope/`](.github/actions/change-scope/), and final accepted product
behavior lives in [`docs/`](docs/). Read relevant final documentation before changing accepted
behavior.

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
## Working agreement

- If unsure or missing context, do not guess. Verify behavior in the repository, installed
  source, approved specification, or test evidence before proceeding.
- For ordinary technical, implementation, configuration, permission-test, and test-environment
  decisions, the primary resolves uncertainty with relevant agent help and chooses the smallest
  clean option inside the approved requirement.
- Before code that touches more than one file or changes existing logic, list every file to
  change, why it changes, and what will not change. The approved task or plan is the approval
  checkpoint; if scope grows, re-propose the complete list.
- Do not create files or add dependencies outside the approved scope.
- Done means the pinned pre-commit command passes, relevant tests pass, and the requested change is
  fully implemented. State any human-only
  verification that remains.

## Agent-assisted implementation

The primary agent owns the plan, scope, integration, and completion decision. For work that benefits
from additional expertise, call the relevant specialist agents in sequence:

1. Use `explorer` to trace existing code, installed framework behavior, migrations, and tests before
   changing existing behavior.
2. Write a bounded plan with acceptance criteria, files and reasons, dependencies, risks,
   migration/rollback effects, tests, UI coverage, and documentation impact.
3. Assign implementation slices to `worker` agents with exclusive file ownership. Keep shared
   surfaces such as `hooks.py`, `patches.txt`, setup exports, and migration ordering with one owner
   at a time.
4. Run focused tests after each slice. When a test fails, assign or make the fix, rerun affected
   tests, and repeat until the relevant tests pass. Then run the final automated gates.
5. For user-visible workflows, use `browser_tester` for the real Desk journey after automated tests
   pass; use `ux_tester` for visual checks when they add useful coverage. Fix failures and rerun the
   affected journey from its start.
6. After behavior and required tests pass, use `doc_writer` for canonical documentation when
   accepted behavior changed. The primary checks the result and completes the work.

Do not delegate merely to add coordination. Specialists report findings, changes, test results,
and blockers directly to the primary. Scope growth or a missing material security, data, billing,
or hard-to-reverse decision returns to the primary for resolution.

- Local development has two Frappe sites with distinct responsibilities:
  - `local` is the normal interactive development site; its Desk host is
    `dev.erp.connectdiagnostics.local`.
  - `local.test` is the dedicated test site; its Desk host is
    `dev.erp.connectdiagnostics.test`.
  All automated test commands must target `local.test` unless the task explicitly authorizes a
  different site. Do not run automated tests against `local` by default.
- Playwright UI acceptance runs only after final automated gates pass. Use isolated
  BrowserContexts for each authenticated workflow actor on `local.test` through
  `dev.erp.connectdiagnostics.test`. Drive document forms and native Workflow actions through
  visible UI controls; do not mutate business state through APIs or direct database calls in the
  UI suite. Supply test-user passwords via environment variables only. Retain actor-specific
  recordings, screenshots, and the ordered action/state manifest with the test run. If the Desk,
  actor credentials, or required test records are unavailable, mark the UI gate not run/blocked
  with exact evidence; never simulate or claim a pass.
- Final documentation describes accepted shipped behavior under `docs/`; the primary checks it
  against accepted code and test evidence before completion.
- Agents may delegate bounded work when a concurrency slot is available. The project limit is
  configured in `.codex/config.toml`; avoid delegation that adds more coordination cost than value.
- All project agents, including the primary, use `gpt-6-luna`. Select reasoning effort when
  dispatching each task: `low` for straightforward lookup/checks, `medium` for bounded
  implementation or testing, and `high` for complex cross-module, security, lifecycle, or visual UX
  review. Explicitly override the role default at dispatch when task complexity differs; TOML
  defaults do not automatically adapt during a running task. Keep the model on Luna.
- `ux_tester` captures and inspects real Playwright screenshots for assigned routes and reports
  findings to the primary. This supplements automated tests and workflow acceptance by
  `browser_tester`.
- **Agent decision protocol:** when a task, test, or blocker raises an ordinary engineering
  question, the primary agent resolves it internally. Gather only the evidence needed, use the
  relevant explorer/worker, and select the smallest clean solution
  that satisfies the approved requirement. Prefer native Frappe/ERPNext behavior, least privilege,
  minimal code/configuration change, reversibility, low migration risk, deterministic testability,
  and low maintenance cost. Preserve the decision rationale and rollback evidence for later review.
- If an external capability cannot be completed by the agents, such as MFA, CAPTCHA, unavailable
  credentials, or an inaccessible external service, mark that path blocked with complete evidence
  and continue all independent work instead of waiting on that path.

Specialists report material progress, changed assumptions, ownership conflicts, test evidence, and
blockers directly to the primary. No repository task register is required.

## Documentation system

`docs/` is the canonical final product/operations knowledge base. Organize it by module first:

- `docs/<module>/behavior.md` — module-wide invariants, ownership, shared semantics, and boundaries.
- `docs/<module>/<workflow>/README.md` — one accepted workflow/process.
- Add `permissions.md`, `data-model.md`, `integration.md`, or `operations.md` only when the
  workflow is complex enough to need a separate stable reference.

Final documentation describes only accepted current behavior. It must not contain TODOs,
implementation backlogs, agent findings, temporary evidence, branch/commit checkpoints,
speculative future design, or historical working notes. Keep temporary work notes out of the
repository; Git history records completed changes.

## Long-running commands

Run commands expected to exceed 60 seconds in a supervised session that yields output. Report
progress at least every 60 seconds, use a hard timeout of 20 minutes unless a longer timeout is
announced first, and inspect a stalled process instead of rerunning it unchanged.

## Context discovery

Before changing existing behavior, search in order: entry points and overrides; existing APIs
and utilities; installed-source implementations; related migrations; and cross-references in
client scripts, templates, jobs, and tests. Check hooks and scheduled events before changing an
existing function. Reuse existing utilities. If the required behavior still cannot be verified,
route the uncertainty to the primary agent for internal resolution with relevant specialist help.

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
role registration, `agents/` for specialist role contracts, `hooks.json` for deterministic
lifecycle checks, and `rules/` only for destructive-operation safety policy. Normal Git workflow
commands such as staging and committing must not be blocked or approval-gated by repository Codex
rules. Reusable procedures live under `.agents/skills/`. `AGENTS.md` remains the repository-wide
policy source; agent files specialize execution roles and must not contradict it.
