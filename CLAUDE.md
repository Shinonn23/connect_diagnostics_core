# Connect Diagnostics Core — Project Rules

Custom ERPNext app for Connect Diagnostics. This file is **auto-loaded every
session** and is the contract for how we work: behavioral/engineering rules plus
**how we branch, version, and ship**. Workflow narrative:
[`.github/WORKFLOW.md`](.github/WORKFLOW.md). Deep per-domain design records live in
[`.github/domain/`](.github/domain/) and are read on demand.

> Procedural guides live in the slash skills — the skill carries its own IDs and
> steps, so this file no longer repeats them:
> `/ship-pr` `/dispatch-test` `/test-result` `/promote-uat` `/promote-prod`
> `/commit` `/pr` `/review`, the Notion task skills `/next-task` `/take-task`
> `/update-task`, `/workspace-navigation`, and the scaffold/check helpers.

---

## Agent Configuration Parity

- Any project change that affects architecture, behavior, commands, workflows,
  conventions, dependencies, testing, or releases must update both `CLAUDE.md`
  and `AGENTS.md` in the same change.
- Keep corresponding agent configuration synchronized in both directions:
  - `.claude/skills/<name>/` ↔ `.agents/skills/<name>/`
  - `.claude/knowledge/` ↔ `.codex/knowledge/`
  - `.claude/settings.json` ↔ `.codex/config.toml` when an equivalent setting exists
- `.github/domain/` is the **shared** domain-knowledge tree used by both assistants; it
  is not mirrored under `.claude` / `.codex`. Update the relevant file there when a
  domain's design changes.
- Keep the semantic content equivalent. Differences are allowed only when required
  by a platform, such as skill frontmatter, invocation syntax, or file location.
- When adding, updating, renaming, or removing an instruction, skill, knowledge
  note, domain doc, or supported setting on one side, mirror the change on the other.
- Before completing any project change, verify this parity and report any intentional
  platform-specific difference. Do not invent an unsupported setting merely to make
  the files textually identical.
- **Known exception:** `/next-task`, `/take-task`, and `/update-task` depend on the
  Notion MCP server, which Codex cannot reach, so they exist only under
  `.claude/skills/` and have no `.agents/` twin. Everything they do can also be done
  by hand in Notion. Do not create shell-only stubs for them.
- The Codex project instruction filename is `AGENTS.md` (plural). Do not create
  `AGENT.md`.

## Rule Priority

When rules conflict, follow this order:

1. **Security** — never compromise on SQL injection, permissions, secrets
2. **Correctness** — working, tested code over pretty code
3. **Backward Compatibility** — do not break existing APIs or data
4. **Style** — formatting, naming, conventions

## Project Context

- **Installed apps**: `frappe`, `erpnext`, `erpnext_thailand`, `hrms`, `connect_diagnostics_core`
- **Required apps** (from hooks.py): `erpnext`, `erpnext_thailand`, `hrms`
- **Frappe stack**: version-16 (frappe/erpnext/hrms on `version-16`)
- **Python**: 3.14 (required by Frappe v16) | **Node**: 24
- **Do NOT assume** any other apps exist (e.g., Healthcare, Education, E-Commerce)
- **Custom field definitions**: `connect_diagnostics_core/setup/*.py` (applied on
  `after_install` / `after_migrate`)
- **Custom field naming**: no prefix — the name must describe the data it holds
  (e.g., `print_date`, `product_group`, `dksh_item_code`); naming is important
- **People**: tester / UAT certifier is GitHub `newyodsapad` (Yodsapad Junta);
  owner / release approver is GitHub `Shinonn23` (Siwat). The exact promotion gating
  each role enforces lives in the `/promote-uat`, `/promote-prod`, and `/test-result`
  skills.
- **Bench**: `/home/erp/frappe`, dev site `deverp.connectdiagnostics.net`
  (= the `developments` environment). `gh` is authenticated as `Shinonn23`
  (scopes include `repo` + `project`). Run server code via
  `bench --site … console` with `exec(open(f).read(), globals())`.
- **Salary Slip submission**: submit only through Payroll Entry; never add a direct
  Salary Slip submit path. (The former review-workflow gate was removed.) See
  [`.github/domain/thai-payroll.md`](.github/domain/thai-payroll.md).
- **Approval ownership**: the app currently owns **no** Frappe Workflow — every
  app-owned approval/review/verification workflow was removed in the custom-workflow
  reset, and the baseline is standard ERPNext behavior plus genuine non-workflow
  validation. Do **not** enforce approval/review/verification states from global
  document hooks, and do not recreate app-owned workflows ad hoc. A new workflow
  starts from a written Workflow Behavior Specification and is owned by Frappe
  Workflow's native states/transitions/conditions (with a transition task only when
  richer execution is genuinely needed), not by `validate`/`before_submit` hooks. A
  direct `doc.submit()` bypassing a workflow transition is an accepted limitation.
- **Operational document naming**: automatically numbered transactional and operational
  DocTypes use `[prefix][YY-BE][MM][####]`; the central registry is
  `connect_diagnostics_core.setup.document_naming`. The month uses the document date,
  alternate series are selected from business fields, and company abbreviations are not
  prepended.

---

# Workflow, Branching & Releases

## Branch & environment topology

```
feature work ─PR→ developments ─PR→ user-acceptance-testing ─PR→ production
                  (DEV / default)    (UAT)                       (PROD)
```

All three long-lived branches are protected (required checks `Server` +
`Frappe Linter`, 1 review). We **merge first, release the batch, then test on the DEV
site** — code review + CI are the pre-merge gate; manual functional testing happens
after the Release PR merges and its `vX.Y.Z` release has deployed `developments` to
DEV. Rationale and full loop: [`.github/WORKFLOW.md`](.github/WORKFLOW.md).

## Automated deployment

DEV is **release-driven**: merging into `developments` does not deploy. Several merged
PRs accumulate in one Release PR, and publishing its `vX.Y.Z` release deploys the whole
batch to `DEV` once. `user-acceptance-testing` and `production` still deploy on push to
`UAT` and `PROD`. All three run the same flow in `.github/workflows/deploy.yml`, and
`workflow_dispatch` can target any environment directly — the escape hatch for a hotfix
that must reach DEV without cutting a release, or when Release Please produces no
release (for example a lone `revert`). The environment is resolved from the trigger and
**fails closed**: an unrecognized trigger stops the job instead of falling through to
PROD. The mechanics (the `BENCH_PATH` variable, SSH secrets, `flock`, per-environment
concurrency) live in that workflow and
[`.github/WORKFLOW.md`](.github/WORKFLOW.md). **Never cancel a running deployment**,
and anyone running `bench update` manually must wait for the workflow's remote lock
to release.

`Server` and `Vulnerable Dependency Check` always report — they are required checks, so
gating the jobs themselves would leave a PR pending forever — but skip their expensive
steps when `.github/actions/change-scope` finds no runtime impact: a Release Please
branch, or a diff confined to markdown, `.claude/`, `.agents/`, `.codex/`, `.vscode/`.
Anything under `connect_diagnostics_core/**` (custom fields in `setup/*.py`, DocType
JSON, fixtures), the dependency manifests, and `.github/workflows/**` still run in full.
When adding a path to that allowlist, the test is whether it can change app behaviour on
a site — not whether it looks like a small edit.

## Branch naming rule

`<type>/<short-kebab-summary>` — optionally `<type>/<issue#>-<summary>`.

- **type** ∈ `feat` `fix` `refactor` `chore` `style` `test` `docs` `perf` `build`
  `ci` `revert` — the same set the version bump understands (keep them aligned).
- lowercase, words separated by `-`, no spaces. One logical change = one branch = one PR.
  Examples: `feat/general-ledger-th`, `fix/employee-be-naming-series`, `chore/281-bump-deps`.
- ❌ Never use the `codex/` prefix. ❌ Do not use `feature/` — use `feat/`.
- Do not create branches off anything but the intended base (default base = `developments`).
- Release Please's generated `release-please--*` branch is the sole automated
  exception to the work-branch naming rule.

## Commit & PR title rule

- **Conventional Commits**: `<type>: <summary>` (same type set as branches).
  Commits must be atomic — one logical change per commit.
- PR titles must use the same format and match the nature of the change.
- Release Please calculates the next version from Conventional Commits merged
  into `developments`; it does not use the PR title as its versioning input.

## Version bump rule

Single source of truth: `connect_diagnostics_core/__init__.py` → `__version__`,
SemVer **`0.MINOR.PATCH`** (MAJOR stays `0` until the owner declares production-stable).

| Merged commit type                                                 | Bump                                                    |
| ------------------------------------------------------------------ | ------------------------------------------------------- |
| `feat`                                                             | **+1 MINOR**, PATCH → 0                                 |
| `fix` `refactor` `chore` `style` `test` `docs` `perf` `build` `ci` | **+1 PATCH**                                            |
| Breaking change while `<1.0.0`                                    | **+1 MINOR**, PATCH → 0                                 |
| `revert` / unrecognized                                            | **skipped** unless the commit supplies `Release-As:`    |

- `.github/workflows/release-please.yml` runs on pushes to `developments` and
  maintains a cumulative Release PR that updates `CHANGELOG.md`,
  `connect_diagnostics_core/__init__.py`, and `.release-please-manifest.json`.
- Merge the Release PR once the batch of PRs that belong together is complete, and
  **before** testing it — merging is what deploys the batch to DEV. It creates a
  `vX.Y.Z` tag and published GitHub Release from `developments`, whose publication
  triggers the DEV deployment; promotion PRs never double-bump. Keep merging feature
  PRs while a batch is still forming: they cost no deployment until the Release PR
  merges.
- **Do not hand-edit `__version__` or the release manifest.** For a revert whose
  inverse version cannot be inferred safely, put `Release-As: X.Y.Z` in the
  Conventional Commit body and let Release Please update the version files.

## Issue ↔ PR rule

- 1 issue → 1 PR (default); 1 PR → many related issues (allowed when tightly related).
- A PR may have no issue when no related issue exists. Record `None` in the PR
  template; never create an issue solely to satisfy the template or a skill.
- When related issues exist, reference them with **`Refs #<n>`**, never
  `Closes #<n>` — issues stay open through testing and are closed only after
  `newyodsapad` certifies the tests pass.

---

# Engineering Rules

## General

- Follow all existing project configs (`pyproject.toml`, `.eslintrc`, `.prettierrc`, `.editorconfig`)
- Never introduce new dependencies without explicit approval
- No placeholder/TODO code — all code must be complete and functional
- Run `uvx --from pre-commit==4.6.1 pre-commit run --all-files` before considering
  any code change done. CI installs the same pinned runner version.
- The local `ty-check` hook uses `../../env/bin/python` by default. CI must set
  `TY_PYTHON` to its bench interpreter and run the hook only after bench installation.
- Copyright header on all Python files:
  ```python
  # Copyright (c) 2026, Siwat Sroisuwan and contributors
  # For license information, please see license.txt
  ```

### Uncertainty & Honesty

- If unsure or missing context, **DO NOT guess** — explicitly state uncertainty and request clarification
- Never fabricate APIs, fields, or behaviors not found in the codebase
- When referencing Frappe/ERPNext APIs, verify by searching the installed source at `apps/frappe`, `apps/erpnext`, `apps/hrms`
- If an API cannot be found in the source code, **stop and ask** — do not fall back to documentation, changelogs, or assumptions

**Must ask before proceeding when:**

- The task affects shared or overridden functionality used by other modules
- An existing API or hook already handles similar logic — unclear if should extend or replace
- The change could affect data integrity (field renames, type changes, deletions)
- Not found after full Context Discovery search (see below)

**May proceed without asking when:**

- Adding a new standalone function with no callers yet (verified by searching for hooks, overrides, and indirect references)
- Fixing a clear bug where the correct behavior is unambiguous
- Applying style/formatting fixes that don't change logic

**When asking for clarification, state:**

1. What you found (or did not find) in the codebase
2. What assumption you would have made if forced to proceed
3. The specific question needed to unblock

**Decision boundaries — AI must NOT:**

- Choose between multiple valid architectural approaches without presenting options and requesting selection
- Assume business rules not explicitly defined in the task or codebase
- Infer missing validation rules
- Decide on naming, scope, or data model without explicit direction

**Definitions:**

- **"Explicitly requested"** means the user typed a clear, written instruction naming the specific change. A vague suggestion like "maybe add logging" does not count — ask for confirmation first.
- **"Explicitly waived"** (for tests) means the user wrote a clear statement in the conversation that tests are not needed for this specific task. Verbal-like ambiguity does not count.
- **"Explicitly approved"** means the user responded with clear confirmation to a proposed change (e.g., "yes", "go ahead", "approved"). Silence is not approval.

### Change Proposal

Before writing code that touches >1 file or modifies existing logic:

1. List every file that will be changed and why
2. State what will **NOT** be changed
3. Wait for explicit approval before proceeding

Do not create new files unless explicitly requested or part of an approved plan.

**Approval scope:** If the scope changes after approval (e.g., discovered additional files must be touched, or the fix in A requires modifying B), **re-propose** the full change list. Do not proceed unilaterally.

### Instruction Conflicts

If a user instruction contradicts these rules, **do not silently comply**. Explicitly state the conflict and which rule blocks it, then ask for explicit override confirmation.

### Partial Completion

If context is discovered to be insufficient mid-implementation:

1. **Stop immediately** — do not continue with guesses
2. List all files already modified
3. Request clarification before continuing

Do not "fill in" missing information to complete the task.

### Long-Running Commands

- Any command expected to run longer than 60 seconds must use a supervised session that can yield output; never start it as an unmonitored blocking call.
- Poll the session and report progress to the user at least once every 60 seconds while it is running.
- Apply a hard timeout to tests, pre-commit, code review, and other potentially long-running commands. The default maximum is 20 minutes.
- If a command produces no new output for 5 minutes, inspect its process state, CPU activity, and available logs instead of continuing to wait blindly.
- Stop the process when its timeout is reached and report what it was doing, the last useful output, and what remains incomplete.
- Do not rerun a timed-out or stalled command unchanged until the previous failure has been diagnosed.
- A command may exceed the 20-minute default only when its expected duration and a new explicit timeout are stated to the user before it starts.

### Task Completion

A task is considered done when **all** of the following are met:

- `uvx --from pre-commit==4.6.1 pre-commit run --all-files` passes with no errors
- `/check` passes with no unresolved issues
- Tests pass (or explicitly waived in written task description)
- Change proposal is fulfilled (all listed files changed, nothing extra)

If any step cannot be completed (e.g., cannot run tests locally), explicitly state what remains and mark it as a human responsibility.

**Multi-step tasks:** For tasks spanning multiple commits or phases, each phase requires its own approval checkpoint. If a later phase fails, do not rollback earlier committed phases — report the failure and ask how to proceed.

### Context Discovery

Before writing any code, search in this order:

1. **`hooks.py`** — find existing entry points and overrides for the target DocType
2. **`api/<system>/`** — find existing whitelisted methods and hook handlers within `connect_diagnostics_core`
3. **`apps/frappe`, `apps/erpnext`, `apps/erpnext_thailand`, `apps/hrms`** — verify the API exists in installed source
4. **`patches/`** — check if a related migration already exists
5. **Cross-reference usage** — grep for the function/class name across all apps to find indirect callers (JS form scripts, Jinja templates, background jobs, scheduled tasks)

If not found after all five steps: **stop and ask**. Do not assume it doesn't exist.

### Codebase Knowledge Cache

- **Before starting any non-trivial task**, check `.claude/knowledge/` for existing notes on the relevant topic; read them before re-exploring the codebase
- **After completing any non-trivial task**, save exploration findings by running `/save-knowledge`
  - Knowledge files: `.claude/knowledge/<topic>.md` — lowercase, hyphen-separated names (e.g., `employee-autoname.md`, `customer-hooks.md`)
  - Contents: key files, functions/hooks used, patterns, non-obvious constraints
- Update the file if new findings extend or contradict prior notes
- `.claude/knowledge/` is an internal AI working directory — do not commit it (add to `.gitignore`)

### Hidden Dependency Detection

Before modifying any existing function or DocType, check for:

- `doc_events` and `override_whitelisted_methods` in `hooks.py`
- Scheduled jobs in `scheduler_events` (hooks.py)
- JS form scripts that call the function via `frappe.call()`
- Jinja templates that reference the function
- Background jobs that enqueue the function

### Code Reuse & Search

- **MUST search the codebase** for existing patterns before implementing new logic
- Reuse existing functions wherever possible; duplication is not allowed
- If a utility already exists, reference it — do not create a parallel version

### Reporting Discovered Issues

If a bug or issue is discovered during implementation (outside the current task scope):

- Report it in the response — do not fix it, do not add inline comments about it
- Format: `Discovered: <file>:<line> — <description>. Not in scope — file a separate issue if needed.`
- Never open GitHub issues or send notifications unless explicitly asked

### Side Effects

- Do not introduce side effects (DB writes, external calls, workflow triggers) unless explicitly required by the task
- Never commit to the database or trigger notifications as a side effect of read operations
- External calls (email, webhook, third-party API) must be explicitly approved and must document whether they are reversible
- If an external call is not reversible, implement a dry-run mode or confirmation flag where feasible

### Transaction Safety

- Multi-step DB operations must be atomic or explicitly documented as non-atomic with a reason
- Any write affecting multiple records must define failure handling and ensure no partial inconsistent state
- Must consider race conditions when updating shared records — use `frappe.db.get_value()` with `for_update=True` or application-level locks where needed

### Deterministic Behavior

- Avoid non-deterministic behavior (random values, time-dependent defaults, unordered dict iteration) unless explicitly required
- Use `frappe.utils.now()` or `frappe.utils.today()` instead of Python stdlib equivalents for consistent test behavior

## Python

- Formatting enforced by ruff via `pyproject.toml` — do not duplicate config here
- All function signatures **must** have type hints
- Use Frappe's `DF` type annotations for Document fields (`from frappe.types import DF`)
- Use `from __future__ import annotations` where needed
- Never modify auto-generated type blocks (between `# begin/end: auto-generated types`)
- Use `frappe.throw()` for validation errors with clear messages
- Hook functions follow `(doc: Document, method: str) -> None` pattern
- Import order: stdlib → third-party → frappe → local modules
- No wildcard imports (`from frappe import *`); no unused imports
- **Maximize type coverage** — type everything possible:
  - Use `cast()` to narrow types from frappe/erpnext: `doc = cast(ProductRegistration, frappe.get_doc(...))`
  - Always type `doc.get()` calls: `value: str = cast(str, doc.get("field") or "")`
  - Prefer `cast()` to narrow types over ignore directives — only use ignore as a last resort
  - When ignore is unavoidable, it must be specific with a reason: `# ty: ignore[unresolved-attribute] - runtime-injected custom field (setup/item.py)`
  - Custom field definitions: `connect_diagnostics_core/setup/*.py`
  - Never use bare `# type: ignore` or `# ty: ignore` without a specific error code and reason

### Error Handling

- Handle exceptions explicitly; do not allow silent failures
- Use `frappe.throw()` for user-facing errors in API and validation layers
- Use `try/except` with `frappe.log_error()` for background jobs and non-critical paths
- Always include the error context in log messages for debugging
- `frappe.throw()` messages must be in English, sentence case, descriptive (e.g., `"Registration number must be in FDA-XXX-#### format"`) — no error codes needed

### Logging & Observability

- Add meaningful logging for critical operations using `frappe.logger(__name__)`
- Log at appropriate levels: `.info()` for flow tracking, `.warning()` for recoverable issues, `.error()` for failures
- Do not log sensitive data (passwords, tokens, personal information)
- Do not log inside tight loops or bulk operation iterations — log summary counts instead
- Avoid high-frequency logging in hot paths (API handlers, hooks, validators) — log only on error or unexpected state

### Idempotency

- Ensure operations are idempotent where applicable — safe to run multiple times with the same result
- Background jobs and data transformations must handle re-runs without duplicating data

## JavaScript/TypeScript

- Formatting enforced by `.eslintrc`/`.prettierrc`/`.editorconfig` — do not duplicate config here
- Declare Frappe globals from `.eslintrc` (`cur_frm`, `frappe`, `locals`, etc.)
- Keep form scripts minimal — delegate business logic to Python APIs
- Use `frappe.call()` to invoke whitelisted Python methods from the client

## Frappe Architecture

- **hooks.py**: organize by hook type, references point to `api/` module functions
- **API files**: `connect_diagnostics_core/api/<system>/<doctype_name>.py`
  - `<system>` = `erpnext` for ERPNext doctypes, `frappe` for Frappe core doctypes
  - `<doctype_name>` = lowercase, spaces → underscores
- **APIs**: expose via `@frappe.whitelist()` with `frappe.has_permission()` checks; validate all inputs server-side
- **DocTypes**: standard DocTypes owned by this app are code-managed. Define their
  JSON, controller, tests, and schema migrations in the repository; do not create
  ad hoc site-local schema through Desk or console. Existing or third-party
  DocTypes remain managed through their documented Frappe mechanism.
- **Workspace navigation**: every new app Module and user-facing app DocType must
  receive a deliberate Desk home in the same change. When it belongs to an existing
  ERPNext domain (for example Stock or Accounting), embed it in the relevant existing
  Workspace card and contextual Sidebar section; do not create a separate Connect
  Diagnostics group. When it is an independent, major Connect Diagnostics domain
  (for example Loan), create its own Module and Workspace. Independent workspaces
  follow ERPNext's information architecture: Home, important DocTypes, collapsible
  Reports and Setup sections, then Settings. Standard Workspace and Sidebar sync
  must preserve unmanaged user rows across migrations. Child-table and technical
  DocTypes with no standalone Desk route are exempt; document the reason in the change.
- **Desk home icons**: app-owned Desktop Icons — including `Folder` icons that group
  related workspaces — ship as `connect_diagnostics_core/desktop_icon/<scrub(label)>.json`
  with matching `public/icons/desktop_icons/{subtle,solid}/<scrub(label)>.svg` artwork.
  Never create them in setup code: migrate deletes any standard icon this app has no
  file for. Regrouping an icon owned by another app is reconciled idempotently in
  `setup/workspace.py` instead, and must save through `_save_without_export` so the
  change is not written back into that app's source.
- **Overrides**: use `override_whitelisted_methods` in hooks.py — never monkey-patch

### API Response Shape

Whitelisted methods must return a consistent structure:

```python
return {"data": <payload>, "message": <str>}
```

- `data`: the payload (dict, list, or `None`). Use `None` when there is no data to return.
- `message`: human-readable status description. Optional — omit when not meaningful.
- Never return raw strings, bare lists, or inconsistent shapes.
- Existing API response structures are immutable — do not change the shape of an existing endpoint unless explicitly approved

### Domain knowledge

Deep design records — the "why it is built this way" for each domain — live in
[`.github/domain/`](.github/domain/) and are loaded **on demand** to keep session-start
context small. Read the relevant file **before** working in that area, and update it
in the same change when a domain's architecture, behavior, or constraints change.

| Domain | Read before touching |
| ------ | -------------------- |
| Leave notifications | [`.github/domain/leave-notifications.md`](.github/domain/leave-notifications.md) |
| Thai payroll | [`.github/domain/thai-payroll.md`](.github/domain/thai-payroll.md) |
| Accounting dimensions (Department) | [`.github/domain/accounting-dimensions.md`](.github/domain/accounting-dimensions.md) |
| Payment Request approval | [`.github/domain/payment-approval.md`](.github/domain/payment-approval.md) |
| Customer onboarding & master data | [`.github/domain/customer-master-data.md`](.github/domain/customer-master-data.md) |
| Customer sales document requirements | [`.github/domain/sales-requirements.md`](.github/domain/sales-requirements.md) |
| Regulatory module | [`.github/domain/regulatory.md`](.github/domain/regulatory.md) |
| DKSH module | [`.github/domain/dksh.md`](.github/domain/dksh.md) |
| Print formats & audit log | [`.github/domain/print.md`](.github/domain/print.md) |

### Custom Fields

- Custom fields are code-managed: define them in `connect_diagnostics_core/setup/<doctype>.py`
  (`CUSTOM_FIELDS` / `PROPERTY_SETTERS`), applied idempotently on `after_install` and
  `after_migrate` — do not create fields ad hoc via desk or console
- **Naming is important** — no prefix; the fieldname must describe the data it holds
  (e.g., `print_date`, `product_group`, `dksh_item_code`). Do not add `cd_`, `custom_`,
  or any other namespace prefix
- Renaming or removing an existing field requires a data-migration patch in
  `connect_diagnostics_core/patches/` (see `remove_cd_prefix_from_custom_fields.py`)
- To reference a custom field in code, declare the `# ty: ignore` with the source
  `setup/*.py` file
- Print-format and Print Log specifics live in [`.github/domain/print.md`](.github/domain/print.md).

### Multi-Tenancy

- Never read or write `frappe.conf` directly — use `frappe.conf[<key>]` which is site-scoped
- Never store site-specific data in module-level variables — use `frappe.cache()` or the database
- Background jobs run in site context — do not assume a specific site name

### Backward Compatibility

- Do not break existing APIs or data structures without explicit instruction
- When modifying shared functions, ensure all callers still work
- Prefer adding new parameters with defaults over changing existing signatures

### Deprecation

- When removing or replacing existing functionality, add a deprecation path: log a warning for at least one release cycle before removal
- Never delete a public function, API endpoint, or hook in the same PR that introduces its replacement — deprecate first, remove later

### Configuration Over Hardcoding

- Prefer configuration-driven logic over hardcoded values
- Use Frappe's single doctype settings or site config for configurable values
- Avoid embedding business rules (thresholds, formats, endpoints) directly in logic

## Security

| Area            | Rule                                                                                                                                |
| --------------- | ----------------------------------------------------------------------------------------------------------------------------------- |
| SQL             | Parameterized queries only: `frappe.db.sql("... WHERE name=%s", (name,))`                                                           |
| Permissions     | Check `frappe.has_permission()` before data access in whitelisted methods                                                           |
| Input           | Validate all user inputs server-side                                                                                                |
| XSS             | Escape dynamic content; use Jinja auto-escaping                                                                                     |
| Secrets         | No hardcoded secrets — use site config or env vars                                                                                  |
| Secret scanning | If user-provided context contains secrets (API keys, passwords, tokens), refuse to embed them in code and warn the user immediately |
| File Uploads    | Validate file types and sizes before processing                                                                                     |

## Performance

- Avoid N+1 queries — use `frappe.get_all()` with specific fields instead of loading full documents
- **Avoid full document loads unless necessary** — prefer field-level queries: `frappe.db.get_value()`, `frappe.get_all()` with `fields=[]`
- Use `frappe.cache()` for frequently accessed, rarely changed data
- Use `frappe.enqueue()` for long-running tasks
- Any loop containing a DB query must justify its query strategy — flag nested loops with DB access as a code review concern

### Background Jobs

- Always set `queue`, `timeout`, and `retry` explicitly in `frappe.enqueue()` calls
- Handle job failure gracefully — log errors with context, do not silently discard
- Ensure enqueued jobs are idempotent — safe to retry without side effects
- Use the `job_id` parameter in `frappe.enqueue()` to prevent duplicate enqueues of the same work

## Anti-Patterns (BANNED)

| Anti-Pattern          | Why                                                                                                                  |
| --------------------- | -------------------------------------------------------------------------------------------------------------------- |
| Hallucinated APIs     | Only use documented Frappe/ERPNext APIs                                                                              |
| Guessing when unsure  | Stop and ask instead of fabricating answers                                                                          |
| Over-engineering      | No unnecessary abstractions or patterns                                                                              |
| Unnecessary comments  | Self-documenting code; no "added by AI" markers                                                                      |
| Generated boilerplate | No placeholder methods, empty docstrings, unused imports                                                             |
| Changing working code | Don't refactor unless explicitly asked; if refactoring, must not change signatures, side effects, or execution order |
| Silent compliance     | When multiple valid implementations exist, present options — do not choose alone                                     |
| Adding dependencies   | No pip/npm install without approval                                                                                  |
| Scope creep           | Stay within the task; report related issues but do not fix unless instructed                                         |
| Inventing patterns    | Follow existing codebase patterns                                                                                    |
| Silent failures       | Never catch and discard exceptions silently                                                                          |
| Duplicating logic     | Reuse existing functions; search before writing                                                                      |
| Unrequested files     | Do not create new files unless explicitly requested or part of an approved plan                                      |
| Mid-task guessing     | Stop immediately if context runs out mid-implementation; do not fill in blanks                                       |

## Auto-Generated Files — DO NOT MODIFY

| File                                       | Why                    |
| ------------------------------------------ | ---------------------- |
| `doctype/**/*.json`                        | Managed by Frappe desk |
| `# begin/end: auto-generated types` blocks | Frappe manages these   |
| Module-level `__init__.py`                 | Generated by Frappe    |

If a change is truly needed, document the exact reason and get explicit approval.

## Schema & Migration

- Never rename or remove fields from existing DocTypes without explicit instruction and a migration plan
- Adding a new required field to an existing DocType requires a patch to backfill existing records
- Schema changes must include a corresponding patch file in `connect_diagnostics_core/patches/`
- Patches must be idempotent — safe to run multiple times without error or duplication
- Every patch must have a corresponding `rollback_<patch_name>.py` in the same directory — not just a comment
- Test patches against a populated database before committing — do not assume empty tables
- If patch testing cannot be performed in the current session, explicitly mark it as a human verification step before merge
- All schema changes require human review before merge, even if PM has approved the feature

## Testing

- All new features must include corresponding tests unless the task description explicitly states tests are not needed
- Test currency-formatting helpers directly, but do not require every Print Format to use `print_currency`; formats may intentionally render numeric amounts without a currency symbol
- Minimum coverage: one test per hook handler and one per whitelisted API method
- Test method names must use `test_<expected_behavior>` pattern (e.g., `test_validates_registration_uniqueness`)
- Test documents created during tests must use descriptive prefixes (e.g., `_Test Registration`) for easy identification and cleanup
- Tests must clean up after themselves — no leftover test data on the site
- Import test bases from `frappe.tests`: use `UnitTestCase` for isolated or fully
  mocked tests and `IntegrationTestCase` for tests that require a site, database,
  DocType metadata, or real Documents. Never use legacy `FrappeTestCase` or bare
  `unittest.TestCase`; every test must be categorized by the Frappe v16 runner.
- Test edge cases: empty inputs, boundary values, Thai-specific logic where applicable:
  - Thai address format validation
  - THB currency rounding (2 decimal places, banker's rounding)
  - Thai tax ID (13-digit) format and checksum validation
  - Buddhist year (BE) vs Gregorian year (CE) conversion
