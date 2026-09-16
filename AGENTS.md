# Connect Diagnostics Core — Repository Policy

This is the sole repository-wide policy file. Codex loads it for work in this repository;
the scoped Frappe rules in [`connect_diagnostics_core/AGENTS.md`](connect_diagnostics_core/AGENTS.md)
apply to the app package. Procedural steps live in the repository skills, workflow narrative
lives in [`.github/workflow.md`](.github/workflow.md), stable domain references live in
[`docs/domains/`](docs/domains/), and active or paused work lives in
[`.github/tasks/`](.github/tasks/). Read the relevant reference and task record before working
in that area.

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

The complete delivery and promotion procedure is [`.github/workflow.md`](.github/workflow.md).

## Working agreement

- If unsure or missing context, do not guess. State the uncertainty and verify behavior in
  the repository or installed source before proceeding.
- Ask before changing shared or overridden functionality, data-integrity-sensitive behavior,
  or an area where extending versus replacing existing logic is unclear. Standalone additions,
  unambiguous bug fixes, and pure style fixes may proceed when their scope is clear.
- Before code that touches more than one file or changes existing logic, list every file to
  change, why it changes, and what will not change. The approved task or plan is the approval
  checkpoint; if scope grows, re-propose the complete list.
- Do not create files or add dependencies outside the approved scope.
- Done means the pinned pre-commit command passes, relevant tests pass (or are explicitly
  waived in writing), and the requested change is fully implemented. State any human-only
  verification that remains.

## Multi-agent engineering protocol

For non-trivial engineering work, work as a coordinated team. The primary agent is the tech
lead, integration owner, and communication broker. It owns the single task register: task graph,
owner, scope, file ownership, dependencies, status, review state, integration, and final
validation. Do not create a shared status file merely for agent coordination.

- Treat work as non-trivial when it crosses modules, changes a data model, DocType, hook,
  permission, transaction, migration, or has material regression risk. Explore and decompose it
  before implementation.
- Use the project agents deliberately: `architect` plans and decomposes, `explorer` gathers
  read-only evidence, `worker` implements one bounded task, and `reviewer` independently reviews
  plans or changes.
- Every substantial task follows this loop: owner creates a domain plan → an independent agent
  reviews the plan → owner resolves findings and revises it → parent marks the plan ready → work
  begins. A plan is ready only when its goal, acceptance criteria, owned files, dependencies,
  risks, tests, and rollback or migration impact are known or explicitly deferred.
- If an owner's plan is too broad to have exclusive file ownership, contains independent
  subsystems, cannot state acceptance criteria, or exceeds the current agent's domain knowledge,
  the owner must decompose it into child tasks. Each child gets a bounded goal, owner, file scope,
  dependencies, acceptance criteria, and plan-review state before implementation. Do not pass a
  vague task to another agent.
- Agents may delegate only when a bounded, independent subproblem benefits materially and a
  concurrency slot is available. Prefer recursive delegation for read-heavy investigation; be
  conservative with write-heavy delegation.
- The runtime permits at most three spawned agents concurrently. Treat this as a shared budget
  across every level of the agent tree; schedule work in waves and do not saturate it without a
  clear benefit.
- Before parallel edits, assign each active worker exclusive ownership of its files. Read-only
  agents may inspect any file. Serialize tasks that need to edit the same file.
- Every agent reports material state transitions to its direct parent using this compact format:

  ```text
  TASK_UPDATE
  id: <stable task id>
  status: proposed | planning | plan_review | ready | active | blocked | completed | code_review | accepted
  owner: <agent role/name>
  scope: <bounded goal and owned files>
  evidence: <plan, commands, findings, or test result>
  dependencies: <open or resolved ids>
  next: <next concrete action>
  blocker: <none or specific blocker>
  ```

  The parent updates its task register, assigns or queues follow-up work, and sends only the
  relevant status and dependency changes to affected children. A child must report a conflict,
  changed assumption, or scope expansion before continuing.
- No self-approval: an implementing worker cannot be the final reviewer of its own changes.
  For substantial changes, independently review the original request, relevant architecture,
  final diff, and test evidence. P0/P1 findings block completion; resolve or explicitly accept
  P2 findings, then re-review fixes before final integration.
- Do not use delegation merely to create activity. Small, isolated work may be completed by a
  single agent when delegation would add more coordination cost than value.

## Long-running commands

Run commands expected to exceed 60 seconds in a supervised session that yields output. Report
progress at least every 60 seconds, use a hard timeout of 20 minutes unless a longer timeout is
announced first, and inspect a stalled process instead of rerunning it unchanged.

## Context discovery

Before changing existing behavior, search in order: entry points and overrides; existing APIs
and utilities; installed-source implementations; related migrations; and cross-references in
client scripts, templates, jobs, and tests. Check hooks and scheduled events before changing an
existing function. Reuse existing utilities and stop to ask when the required behavior cannot
be verified.

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
- When multiple valid architectures exist, present the options instead of choosing silently.

## Codex configuration

Trusted project configuration lives under `.codex/`: `config.toml` for project settings,
`hooks.json` for deterministic lifecycle checks, and `rules/` for command execution policy.
Reusable procedures live under `.agents/skills/`. The repository does not keep agent-specific
policy copies or internal knowledge caches.
