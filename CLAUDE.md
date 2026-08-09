# Connect Diagnostics Core — Project Rules

Custom ERPNext app for Connect Diagnostics. This file is **auto-loaded every
session** and is the contract for how we work: behavioral/engineering rules plus
**how we branch, version, and ship**. Workflow narrative:
[`.github/WORKFLOW.md`](.github/WORKFLOW.md).

> For procedural guides, use the slash skills:
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
- Keep the semantic content equivalent. Differences are allowed only when required
  by a platform, such as skill frontmatter, invocation syntax, or file location.
- When adding, updating, renaming, or removing an instruction, skill, knowledge
  note, or supported setting on one side, mirror the change on the other side.
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
- **Bench**: `/home/frappe/frappe-bench`, dev site `dev.erp.connectdiacnostics.local`
  (= the `developments` environment). `gh` is authenticated as `Shinonn23`
  (scopes include `repo` + `project`). Run server code via
  `bench --site … console` with `exec(open(f).read(), globals())`.

---

# Workflow, Branching & Releases

## Roles

- **Tester / UAT certifier:** GitHub `newyodsapad` (Yodsapad Junta). Only his
  target-qualified `/test-pass — all steps verified on <environment> @ <full
  SHA>` matching the task's current Test target counts as certification to
  promote; a bare, stale, or target-mismatched marker does not. The owner may
  explicitly bypass the UAT manual-test gate with
  `/promote-uat --bypass-test "<reason>"`; a bypass is not certification and must
  not change test results. A later `/test-fail` reopens the source issue and
  invalidates its earlier UAT approval. Deferred certification must name the exact
  deployed environment and commit tested. Each bypassed source issue carries an
  owner-authored `/test-bypass` marker linked to the matching UAT PR audit entry.
- **Owner / release approver:** GitHub `Shinonn23` (Siwat). `/uat-approve` sign-off
  must be newer than the latest `/test-fail` on each source issue; a generic marker
  on a shared test task blocks promotion until its failing source issues are
  identified. Production deployment does not close bypassed or otherwise
  uncertified source issues, regardless of the Test Status enum. Failed or active
  re-test issues normally block production promotion. An unresolved failure on an
  already-PROD issue globally
  blocks unrelated production batches until it passes and receives newer approval.
  A remediation-only batch may deploy a fix when every included developments PR
  directly `Refs` an actively held source; the hold remains until that new PROD
  target passes. Any source without either target-matched certification or a
  matching bypass audit is a production blocker, even if Test Status says Passed.
  Each current source must use the UAT promotion PR that introduced its latest
  included developments PR; cumulative PROD batches may map sources to different
  UAT promotions.

## Branch & environment topology

```
feature work ─PR→ developments ─PR→ user-acceptance-testing ─PR→ production
                  (DEV / default)    (UAT)                       (PROD)
```

All three long-lived branches are protected (required checks `Server` +
`Frappe Linter`, 1 review). We **merge first, then test on the DEV site** — code
review + CI are the pre-merge gate; manual functional testing happens after merge
on `developments`. Rationale and full loop: `.github/WORKFLOW.md`.

## Automated DEV and UAT deployment

- `.github/workflows/deploy.yml` deploys every push to `developments` to GitHub
  Environment `DEV` (`34.143.156.218`) and every push to
  `user-acceptance-testing` to `UAT` (`136.110.8.47`). It does not deploy PROD.
- `workflow_dispatch` supports an explicit `DEV` or `UAT` target for retrying or
  manually starting the same deployment flow.
- Both GitHub Environments require an Environment secret named `BENCH_PATH`,
  initially `/home/erp/frappe`; it is the Frappe Bench root, not the CLI path.
  Repository secret `SSH_PRIVATE_KEY` contains the passphrase-free
  `google_compute_engine` key; `SSH_KNOWN_HOSTS` contains verified host-key entries
  for both servers. Never print these values in workflow logs.
- Deployment connects as `erp`, validates the directory and `flock`, prepends
  `$HOME/.local/bin` and `/usr/local/bin` to `PATH`, initializes
  `$HOME/.nvm/nvm.sh`, selects Node.js 24, and validates executable `node`, `npm`,
  `yarn`, and `bench` commands before running `bench update --reset` from
  `BENCH_PATH`. Jobs have a 120-minute timeout; the remote lock waits up to 60
  minutes before failing. Do not source interactive shell configuration such as
  `.zshrc` in deployment automation.
- DEV and UAT have separate concurrency groups with `cancel-in-progress: false`.
  Never cancel a running deployment or enable cancellation mid-deploy. GitHub
  preserves the running job and retains only the newest pending job per environment.
- The remote `flock` coordinates GitHub workflow deployments only. Anyone running
  `bench update` manually must wait for the workflow deployment to finish.

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
  maintains a cumulative Release PR. The PR updates `CHANGELOG.md`,
  `connect_diagnostics_core/__init__.py`, and `.release-please-manifest.json`.
- Merge the Release PR after its DEV batch is tested and before promoting that
  batch to UAT. Merging it creates a `vX.Y.Z` tag and published GitHub Release
  from `developments`; promotion PRs never double-bump.
- Release Please uses the `RELEASE_PLEASE_TOKEN` Actions secret so its PR triggers
  the protected-branch checks. The token must have write access to Contents,
  Pull requests, and Issues (for Release PR labels).
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

## Ship & promote — use the skills

| Skill                                            | What it does                                                                                                |
| ------------------------------------------------ | ----------------------------------------------------------------------------------------------------------- |
| `/ship-pr`                                       | from a work branch → ready-to-merge PR into `developments`; dispatch testing only after DEV deployment      |
| `/dispatch-test <PR#>`                           | bind a manual-test task to the exact deployed environment and commit                                          |
| `/test-result <PR#\|issue#> pass\|fail [reason]` | record revision-bound results; map failures and create post-PROD holds                                         |
| `/promote-uat [--bypass-test "<reason>"]`        | gate tests; record matching PR and source-issue bypass audit markers                                           |
| `/promote-prod`                                  | map UAT batches; enforce holds, approvals, audits, and remediation-only releases                            |

## Board #6 reference (for skills using `gh project`)

- Owner `Shinonn23`, project number `6`, id `PVT_kwHOB1tcMM4BLM7I`
- **Status** field `PVTSSF_lAHOB1tcMM4BLM7Izg62NJg`: TODO `f75ad846` · DEV Ready `61e4505c` · Dev In progress `47fc9ee4` · Dev review `df73e18b` · Test In progress `18955566` · Test Review `6c769416` · UAT Deploy `98236657` · PROD Deploy `dba9dd7f` · Hold `232c6587`
- **Test Status** field `PVTSSF_lAHOB1tcMM4BLM7IzhWdi_0`: Not Tested `9d66b7d0` · Testing `2556afad` · Passed `97d946bc` · Failed `15087b1c`
- **Tested By** field `PVTF_lAHOB1tcMM4BLM7IzhWdjBE` (text)
- Set a value: `gh project item-edit --id <ITEM_ID> --field-id <FIELD_ID> --project-id PVT_kwHOB1tcMM4BLM7I --single-select-option-id <OPT_ID>` (text fields use `--text`).
- An issue's board **item id** comes from `gh project item-list 6 --owner Shinonn23 --format json --limit 1000`.

## Notion Task Tracker reference (for skills using the Notion MCP)

The client-facing task list. Separate from board #6 and not synchronized with it —
a Notion task may span several GitHub issues, or none.

- Database **Task Tracker** `4c1c5f86101c46d18557190f96aa9aab`, under the page
  *ERPNext Connect Diagnostics*; tasks are referred to as `TSK-<Task ID>`
- Data source `collection://bcd5f7fa-c9c1-43dc-bfd7-c30272a1d100` — use this string
  as the table name in SQL: `SELECT ... FROM "collection://bcd5f7fa-..."`
- All Tasks view `view://320d5160-c409-40a4-87e2-b0f6962bf6ae`
- **Status**: `Not started` · `Backlog` · `In progress` · `In review` · `Done` · `Cancelled`
- **Priority**: `🔴 Critical` · `🟠 High` · `🟡 Medium` · `🟢 Low`
- **Work Type**: `Requirement` · `Design` · `Development` · `Configuration` ·
  `Data Migration` · `Testing` · `Documentation`
- `Related User Tickets` relates to `collection://e73aded7-efef-4426-b312-0dc4d0e6047a`
- Write quirks that silently fail if ignored: `Task ID` is `auto_increment_id` and
  read-only; dates split into `date:<Name>:start` / `:end` / `:is_datetime`;
  `Assignee` is an array of user IDs; checkboxes use `__YES__` / `__NO__`
- Tools are the Notion MCP `fetch`, `query-data-sources`, and `update-page`
  (`command: update_properties`). **Match them by name suffix — the server prefix is
  a per-install UUID and must never be hardcoded into a skill.**
- Resolve the current user by calling `fetch` with the literal id `self`
- Never set a task to `Done` on code evidence alone. Tasks whose Acceptance Criteria
  require a human step — a real-printer test, a tester's Pass/Fail record — close
  only when that human has certified them.

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
  (for example Loan), create its own Module and Workspace. Child-table and technical
  DocTypes with no standalone Desk route are exempt; document the reason in the change.
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

### Leave Notifications

- `Leave Approval Notification` emails an open Leave Application to its leave approver;
  `Leave Status Notification` emails Approved, Rejected, or Cancelled results to the employee.
- Both templates are code-managed in `fixtures/email_template.json` and store
  their Jinja/HTML content in `response_html` with `use_html` enabled.
- Do not fixture the complete HR Settings Single DocType. Select both templates
  in HR Settings per site so unrelated environment-specific HR configuration is not overwritten.

### Thai Payroll

- Payroll config is code-managed and idempotent in `connect_diagnostics_core/setup/payroll.py`,
  applied on `after_install` / `after_migrate` through `ensure_configuration()`. The payroll
  DocTypes are HRMS's (Salary Component / Structure / Structure Assignment / Income Tax Slab /
  Payroll Period / Salary Slip); `erpnext_thailand` covers only creditor withholding (ภงด3/53),
  **not** employee personal income tax.
- Employee payroll fields live in the **Thai Payroll** section of `setup/employee.py`
  `CUSTOM_FIELDS`: `national_id` (13-digit citizen ID; doubles as the personal tax ID for
  ภงด1/ภงด1ก — Employee otherwise stores only `passport_number`), `social_security_id`,
  `social_security_eligible`, and `provident_fund_rate` (Percent, per-employee, **no default** —
  real rates differ, e.g. 3% / 7.5%). No property setter makes any of the four required.
- `setup/payroll.py` seeds, **create-only-if-absent** so a later manual edit survives: 14 Salary
  Components (8 earnings / 6 deductions), the `Thailand Personal Income Tax` Income Tax Slab, a
  current-year Payroll Period, and the `Connect Diagnostics Monthly` Salary Structure. The
  company-scoped records (slab, period, structure) are skipped fail-open when no default Company
  resolves; Salary Components are company-agnostic.
- Formulas run in the HRMS component eval context (`hrms/payroll/utils.get_component_eval_context`),
  which exposes `base` (from the Structure Assignment), Employee fields, and the `min` / `max`
  globals. Social Security = `min(base, 17500) * 0.05` — the company caps the contribution base at
  17,500 (875/month), above the statutory 15,000 / 750. Provident Fund =
  `base * (provident_fund_rate or 0) / 100`. Withholding Tax uses `variable_based_on_taxable_salary`
  so HRMS computes PIT from the slab.
- The slab folds the personal allowance (60,000) and the capped 50% expense deduction (max 100,000)
  into `standard_tax_exemption_amount = 160000`; per-person deductions (spouse, children, insurance,
  SSO/PF paid) flow through Employee Tax Exemption Declarations, enabled by `allow_tax_exemption`.
  The `Employee Welfare Fund` component is seeded **disabled** until it becomes mandatory
  (1 Oct 2026, 0.25%).
- Not yet built — do not assume present: per-employee Salary Structure Assignment (base pay),
  historical Salary Slip seeding for mid-year go-live YTD (SSO / income / tax accumulate only from
  submitted slips; HRMS opening fields cover tax only, and only for mid-period joiners), and the
  Thai year-end ภงด1 / ภงด1ก and annual Social Security reports (absent from HRMS and
  `erpnext_thailand` — must be built in-app).

### Payment Request Approval

- The code-managed Frappe Workflow `Payment Request Approval` applies only to
  `Payment Request.payment_request_type = "Outward"`. Inward requests use the
  standard submit path. Payment Entry Receive and Internal Transfer behavior is
  unchanged.
- `Company.low_value_payment_approval_limit` is expressed in company currency.
  Blank or zero sends every Outward request to the primary approver. With a
  positive limit, amounts below the limit use the low-value approver; amounts equal
  to or above it use the primary approver. The limit is snapshotted when approval
  is requested, so later Company changes do not reroute a pending request.
- `Payment Request.base_grand_total` is the requested amount in company currency.
  It equals `grand_total` for company-currency requests and otherwise uses the
  reference document's `conversion_rate`.
- After 24 calendar hours, the secondary executive is added as an approver. The
  original primary remains eligible; low-value requests also remain eligible for
  the accounting approver. The first approval or rejection completes the shared
  Workflow Action. Self-approval is disabled; creator, deadline, base amount, and
  limit snapshot are protected and revalidated server-side.
- Every submitted `Payment Entry.payment_type = "Pay"` must allocate its complete
  amount to one or more submitted, approved Outward Payment Requests whose company,
  party, and reference match. Requests are locked in sorted order and allocation is
  aggregated per request, allowing partial payments and multiple requests without
  concurrent overpayment. Pay entries without such references are rejected.
- The workflow, custom roles, profiles, fields, Custom DocPerm records, submit gate,
  and scheduler are managed in `connect_diagnostics_core/setup/payment_approval.py`
  and `connect_diagnostics_core/api/erpnext/payment_approval.py`. The scheduler
  checks escalation deadlines every five minutes.
- Setup and migration append the approved payment profile when a User already uses
  Role Profiles. For a User with no Role Profiles they add only the profile's roles
  directly so existing direct roles are not erased. Missing or disabled approver
  Users do not block a fresh installation; later migrations retry the assignment.
  Arirat receives primary plus low-value access, Sopha receives low-value access,
  and Sasin receives the secondary direct role until his later Role Profile migration.
- Workflow Actions work without email, but email delivery requires a configured
  Default Outgoing Email Account on each site.

### Customer Onboarding and Master Data

- A Customer's document name is its required manual `Customer Code`; do not restore
  the Customer naming series. The code can be corrected until the Customer has its
  first Quotation, Sales Order, Sales Invoice, or Delivery Note, after which a rename
  would rewrite documents that have already gone out.
- **There is no Customer onboarding workflow.** Sales saves a Customer and can raise
  an order against it in the same breath. The previous queue — Customer Request →
  duplicate verification by IT-UB → accounting activation, with the Customer
  `disabled` throughout — cost more than it caught and is retired along with the
  `Customer Duplicate Verifier` role. Do not reintroduce an activation state.
- Master data is required where it is used, not before a sale can start:
  `sales_invoice.validate_tax_invoice_readiness` blocks **submitting** a Sales Invoice
  until tax readiness passes — one active primary Billing Address whose Thai address,
  tax ID, and branch code match Customer. Nothing blocks the order.
- Readiness is **calculated, never stored**. `customer.build_readiness_values` is the
  single place that decides what a Customer is missing; the invoice gate and the
  Customer form both read it live through `get_customer_readiness`. The four readiness
  Select fields, their summary, `customer_onboarding_state`, `correction_reason`, and
  the no-delivery controls were dropped with the workflow, together with the Address
  and Contact hooks that rewrote them on every save.
- `Print Configuration Template` is shared print policy: a `Documents` table with one
  row per registered document, and a `Copies` table of named page sets. It holds no
  per-customer scalars. Every Customer linked to it follows those rows **live** —
  editing a Template changes what its Customers print immediately, with no fetch step.
- Customer `Document / Print Configuration` links one Template and carries only its
  own values: Customer Print Name, Quotation signatory type and Delivery Terms,
  and the source Purchase Order copy settings. Its `Documents` and `Copies` tables are
  overrides: no row means inherit the Template for that document; a row wins wholesale.
- `connect_diagnostics_core/setup/print_documents.py` is the single source of truth for
  which documents exist (Quotation, Tax Invoice, Abbreviated Tax Invoice, Receipt),
  their named copies, whether language is selectable, and whether Batch / Serial
  applies. Doctype rows, sidebar controls, and the print context all derive from it —
  adding a document type is a change there and nowhere else. The retired `invoice` and
  `delivery_note` configurations must not be reintroduced; no print format consumed them.
- Values resolve in four stages, later winning: registry defaults, Template rows,
  Customer scalars and override rows, then request-only `flags.print_settings`. A blank
  Customer text value inherits rather than blanking the resolved value. The resolver
  also reports the source of each value, which the Print sidebar shows under each
  control alongside a Reset to default action.
- The Print sidebar loads only the active format's controls and sends them as
  request-only `settings` overrides. Overrides affect preview, print, and PDF for that
  request only; they never save Customer or the source document. Missing fields during
  a code-before-migration rollout fall back to registry defaults.
- Sales Invoice prints the named copies Original, Customer Copy, Accounting Copy, and
  Sales Copy, plus a Batch / Serial visibility option. All four default to one page set
  each. Sales Invoice is Thai-only: the registry fixes its language and any row value
  is ignored. Named copies are available to every document, not only Sales Invoice.
- Sales Order is a registered print document like the others: its date is the per-document
  `show_date`, resolved live from the Customer and overridable per print request on
  `/app/print/Sales Order/<name>`. The retired `Customer.print_date` flag and the Sales
  Order format's direct read of it must not be reintroduced.
- The combined Sales Invoice format resolves Batch and Serial values from both
  direct item fields and `Serial and Batch Bundle`, renders one traceability
  line per record without ellipsis, then paginates whole item blocks before
  rendering. Each page repeats the invoice summary and resets the current-page /
  total-pages value within each selected copy set; only the final overall page
  omits the page break after it.
- Purchase Order keeps supplier and order header data in separate boxes, adds
  the company's Ship To address and supplier Contact, shows ETA from the
  standard `schedule_date` field plus Incoterm and Currency, and uses Item Code,
  Description, QTY, UOM, Unit Price, and Amount columns without warehouse or
  item-level discount columns.
- Quotation carries its own signatory: `Quotation.sales_representative_employee` is the
  Employee who issues that offer, defaulted from the logged-in user. It prints in the
  contact block on every form and signs the document when the signatory is a Sales
  Representative. Do not resolve the signatory from the Customer Sales Team — Quotation
  has no `sales_team` table, and the retired `Sales Person.employee` chain picked an
  arbitrary first row.
- The caption under the signature line is a fixed literal per signatory type, held in
  `setup/quotation.py` as `SIGNATORY_CAPTIONS`; it is never `Employee.designation`. A
  Managing Director quotation prints an **empty** name by design so the director signs
  and writes the name by hand, and therefore resolves no Employee at all. The retired
  `Company.quotation_authorized_signatory_employee` and its Quotation override must not
  be reintroduced.
- `override_quotation_validity_text` and `quotation_custom_validity_text` live on
  Quotation, not Customer: the wording describes one offer. Customer keeps only
  `quotation_signatory_type` and `quotation_delivery_terms`, copied as defaults to new
  Quotations. `print_documents.QUOTATION_CUSTOMER_FIELDS` is what Customer stores;
  `QUOTATION_EXTRA_FIELDS` is what the sidebar may override for one request.
- The single Quotation format renders Thai, English, or Thai / English and configured
  original/copy pages. `show_date` off and a custom validity text are ordinary
  configuration, not separate formats.
- `Customer Credit Request` is the only route to payment terms and a credit limit,
  for **every** Customer including `GOV. HOSPITAL`, and is approved by the Customer
  Credit Approver. It does not depend on a channel field. Customers start on whatever
  terms they are created with; `Customer.validate` still blocks anyone without the
  Customer Accounting Reviewer role from editing terms or limits directly.
- Customer, Item, and Supplier keep their current document names and codes. Do not
  add conversion flags or automatically rename these masters. The DKSH reference codes
  `dksh_item_code`, `supplier_product_code`, `mat_group_code`, `mat_group4_code`, and
  `material_type_code` live on the standalone `DKSH Item` DocType (autonamed by
  `dksh_item_code`) with an **optional** `item` link — blank means a DKSH stand-alone
  product with no CD Item. They are optional reference data only, with no workflow and no
  roles of their own, and must not control Item lifecycle or transaction eligibility. The
  link surfaces on the Item form's Connections via `override_doctype_dashboards`
  (`api/erpnext/item.py`). `DKSH Item` and every other DKSH reference master live in the
  `Connect Diagnostics DKSH` module (see the *DKSH module* section below), not in Core. The
  earlier design that grouped these as five Custom Fields on an Item DKSH tab, plus the Item
  list view and the stock-showing `get_item_with_stock` link query that searched them, were
  removed; do not reintroduce them.
- Sales Order uses the standard `item_code` grid and otherwise standard ERPNext
  behavior for every Company. Do not force a selling Price List, Skip Delivery Note,
  external order status, or Company-specific Item link query. The sales document
  requirement gate below is the one deliberate exception and is driven by Customer
  data, not by Company.

### Customer Sales Document Requirements

- A Customer states what it needs before a sale proceeds, in the *Sales Document
  Requirements* section of its Document / Print Configuration tab. These are process
  gates, not print settings: they say what must exist, while the print configuration
  says how the resulting documents print.
- `quotation_required` rejects a Sales Order with no `Sales Order Item.prevdoc_docname`,
  the standard ERPNext link to the Quotation a line was mapped from.
  `source_purchase_order_copy_required` rejects a Sales Invoice whose
  `source_purchase_orders` table has no row naming either a `purchase_order` or a
  `purchase_order_file`.
- `use_customer_po` was renamed to `source_purchase_order_copy_required`. It never held
  the Customer's own purchase order — it asks whether the Customer wants a copy of the
  Purchase Order **we** placed with our supplier — and the old name collided with the
  standard `Sales Order.po_no` ("Customer's Purchase Order"). Its default also flipped
  from 1 to 0; only a handful of Customers actually ask for the copy. Do not reintroduce
  the old name.
- `connect_diagnostics_core/api/erpnext/sales_requirements.py` owns the rules and the
  `validate` hook for both DocTypes. Every evaluator accepts a `Document` or a plain
  mapping so one form and a whole report page share the same logic; the whitelisted
  `get_transaction_requirements` takes the form's document rather than a name, so an
  unsaved order shows the requirement while it can still be met.
- A holder of the `Sales Requirement Override` role proceeds by writing
  `requirement_override_reason`, which stays on the document as the audit trail. The
  role alone does not bypass the gate, and the reason is cleared once the gap closes.
- The source Purchase Order copy is **concatenated as extra PDF pages, never rendered
  inside the tax invoice format**. Nesting fails for two reasons: the `Purchase Order`
  format's CSS sets `@page`, `html, body` and `.print-format` globally and would rewrite
  the invoice's page geometry, and its template calls `register_print`, which would log a
  Purchase Order print to a supplier every time a Customer's invoice printed. The join
  therefore happens in the `download_pdf` override using `pypdf`, which frappe already
  depends on. The `source_purchase_orders` table carries one row per Purchase Order, each
  appended in table order `copies` times (a blank row count falls back to
  `Customer.purchase_order_copy_count`). This covers the PDF channel only — the Print
  button hands HTML to the browser, so the Sales Invoice form offers one print button per
  source row.
- Rendering the Purchase Order deliberately sets `frappe.flags.ignore_print_permissions`.
  The copy is a page the Customer is meant to receive, so anyone allowed to print the
  invoice may produce it; requiring Purchase Order print rights would stop sales staff
  from downloading their own invoices. Like the print audit, the join is fail-open: a
  failure is logged with context and the invoice PDF is returned unchanged.
- `setup/print_configuration_template.py` also creates three document policy Templates —
  `Tax Invoice Only`, `Tax Invoice and Receipt`, `Tax Invoice and Abbreviated Receipt` —
  named after what they print rather than after a Customer Group, because more than one
  group follows each. They are initial contents only: an existing Template is never
  overwritten, since a Template is user data once created.
- The retired mapping doctypes (`DKSH Item Mapping`, `Partner Item Mapping`), workflow,
  roles, Sales Order fields, and dedicated selling Price List must not be recreated. The
  new `DKSH Item` reference master is a distinct, allowed DocType, not one of those.
  Retirement migrations may delete only those explicitly retired records and fields; they
  must not rename or delete Customer, Item, Supplier, Asset, or historical transactions.
- The retired DKSH APIs and hooks are explicitly exempt from the usual one-release
  deprecation period because this domain was removed before go-live. Do not restore
  compatibility stubs for them.

### Regulatory module

- `Connect Diagnostics Regulatory` (in `modules.txt`, folder
  `connect_diagnostics_core/connect_diagnostics_regulatory/`) owns medical-device
  regulatory source-of-truth masters. Product Registration has the FDA registration
  number and effective Registered Product rows; Item retains only classification and
  read-only current coverage derived by `api/erpnext/regulatory.py`. Never duplicate
  FDA numbers, NEWCODE, expiry, or regulatory documents onto Item.
- Renewal and variation history belongs in `Medical Device Registration Action`; a
  replacement registration must link its predecessor/successor instead of overwriting
  the historic record. A verified Certificate is the initial activation requirement.
  Do not infer Thai FDA classifications, document requirements, or legal stock policy.
- `setup/regulatory.py` owns the Regulatory Viewer/Operator/Approver roles,
  permissions, and the Product Registration workflow. `setup/workspace.py` maintains
  the independent Regulatory Workspace. Registered Product and Expiry Alert Rule are
  child tables and intentionally have no Desk route.
- `api/erpnext/regulatory_transactions.py` is the only transaction-policy boundary.
  It resolves regulatory coverage by the transaction date, keeps PO/SO non-blocking,
  and snapshots resolved master facts on each submitted row. Never derive a historical
  transaction from the Item's current fields. A Regulatory Override must be an approved,
  document-bound record; it bypasses a gate but is retained in the row snapshot.
- `api/erpnext/regulatory_alerts.py` owns daily expiry processing and weekly digests.
  It de-duplicates alerts by registration/document and threshold through the immutable
  Alert Log; recipient roles/users come from the alert rule, never Item rows. Regulatory
  Script Reports use the read-only `regulatory_reporting.py` helpers. Standard Frappe Data
  Import is enabled for masters; use the preflight API before writing a production import.

### DKSH module

- `Connect Diagnostics DKSH` (in `modules.txt`, folder
  `connect_diagnostics_core/connect_diagnostics_dksh/`) is the single home for the DKSH
  domain: the DKSH reference masters and the deferred DKSH daily sales import / analysis.
  It is registered in `setup/print_format.py::APP_MODULES` so any future DKSH Print Format
  is not purged. `DKSH Item` lives here (moved from Core by
  `patches/v1_0/move_dksh_item_to_dksh_module.py`, which repoints `DocType.module` and
  reloads from the new folder — records are untouched).
- **DKSH reference master convention.** Each one is a standalone DocType autonamed by its
  DKSH code (`autoname: field:<code>`), carrying an **optional** `Link` to the CD master it
  references (blank = a DKSH stand-alone record). It is reference data only — no workflow,
  no roles, no control over the CD master's lifecycle or transaction eligibility — and may
  offer a Convert-to-CD action. Two shared behaviours live in
  `connect_diagnostics_dksh/reference.py`, so every master is built the same way:
  `validate_reference(doc, *, code_fields, link_field, master_doctype)` trims the codes and
  rejects a second reference pointing at the same CD master; `inject_connection(data, *,
  reference_doctype, link_field, group_label)` is the generic `override_doctype_dashboards`
  helper that surfaces the master under the CD form's Connections. `DKSH Item` and
  `api/erpnext/item.py::get_item_dashboard_data` both delegate here.
- `DKSH Customer` is the reference master for customers that carry a 9-digit DKSH code
  differing from their CD Customer Code. It follows the convention above (autoname
  `field:dksh_customer_code`, optional `customer` link, surfaced under the Customer form's
  Connections via `api/erpnext/customer.py::get_customer_dashboard_data`) and additionally
  stores DKSH's own `customer_name` plus a contact/tax block (`tax_id`, `branch_code`,
  address fields, `phone`, `email_id`) for the Convert flow.
- **Convert to CD Customer.** When a `DKSH Customer` has no `customer`, the form
  (`public/js/custom/dksh_customer/doctype.js`) offers **Convert to CD Customer**, which
  opens a **prefilled New Customer form** (name, tax id, branch code, and the read-only
  provenance field `source_dksh_customer` from `setup/customer.py`); the user types the CD
  Customer Code (the document name) and saves. Customer `after_insert`
  (`link_source_dksh_customer`) then links the DKSH Customer back under a row lock — only
  when it is still unclaimed, so it is idempotent — and, when the DKSH Customer carries an
  address and the new Customer has none, creates a primary Billing Address from it (with the
  matching `tax_id`/`branch_code`) so the tax-invoice readiness gate can pass. That address
  creation is fail-open: a failure is logged and never aborts the Customer. Phone→Contact
  creation is a deferred follow-up. When `customer` is already set the form offers **Go to
  Customer** instead.

### Custom Fields

- Custom fields are code-managed: define them in `connect_diagnostics_core/setup/<doctype>.py`
  (`CUSTOM_FIELDS` / `PROPERTY_SETTERS`), applied idempotently on `after_install` and
  `after_migrate` — do not create fields ad hoc via desk or console
- Print lives in its own module. App-owned Print Formats, `Print Configuration Template`,
  the two configuration child tables, and `Print Log` all belong to
  `Connect Diagnostics Print` under `connect_diagnostics_core/connect_diagnostics_print/`.
- Print Formats are app-owned and editable through Desk (`standard = "No"`): `after_sync` and
  `after_migrate` remove every
  `Print Format` whose module is not one of the app modules (`Connect Diagnostics Core`,
  `Connect Diagnostics Stock`, `Connect Diagnostics Accounting`, or `Connect Diagnostics
  Print`) or an ERPNext Thailand module (`Thai Tax`, `Thai Billing`, `Thai Deposit`, or
  `Petty Cash`). Retired formats are removed explicitly; `Sales Invoice Print` is retired and
  Sales Invoice defaults to `Tax Invoice Delivery Note and Invoice`. `Withholding Tax Cert` is
  owned by ERPNext Thailand; the app-owned Thai WHT certificate is the separately named
  `Withholding Tax Cert CD`, so the two coexist and neither overwrites the other. Do not add a
  Print Format fixture that restores records from other modules.
- The `css` field is appended verbatim; only `html` is rendered through Jinja. A `{{ ... }}`
  left in `css` is emitted literally and silently breaks whatever it built, so asset paths in
  `css` must be relative (`/assets/...`), never built with `frappe.utils.get_url()`.
- Dates in print formats come from the shared `format_date` Jinja method, which renders
  DD-MM-YYYY in the **Buddhist era**. The `+ 543` conversion lives only in
  `connect_diagnostics_core/utils/date.py`; a template must never convert the era itself.
- Print Format Jinja must be ordered as comment, derived variables, pagination, then HTML.
  Use a namespaced root class, scope CSS beneath that root, keep CSS out of the HTML field,
  and prefer semantic `header`, `section`, `table`, and `footer` elements. Use physical
  dimensions in `mm`; app-owned Print Formats must not use a background image, except formats
  that overlay an official government form scan — `Withholding Tax Cert CD` positions its fields
  over the Revenue Department form image from `erpnext_thailand`, so the background-image and
  semantic-sectioning rules do not apply to it. `Shipment Box
  Label` is a 180 × 100 mm landscape Shipment format that uses `cd_logo_v2.jpg`, splits sender
  and recipient details, and shows the recipient Customer's Territory only when present.
- When modifying an app-owned Print Format JSON, update its `modified` timestamp to the current
  time. Frappe imports a standard record only when the source is newer, so an unchanged timestamp
  leaves the deployed format stale after `bench migrate`. The Sales Invoice format also has an
  explicit `sync_sales_invoice_print_format` migration so sites that already ran an earlier
  configuration migration receive the current HTML/CSS.
- Use the registered `format_money(amount, blank_zero=False)` Jinja helper for plain numeric
  amounts. Keep `print_currency` where a template intentionally renders a currency-aware value;
  do not define local money-formatting macros in Print Formats.
- **Naming is important** — no prefix; the fieldname must describe the data it holds
  (e.g., `print_date`, `product_group`, `dksh_item_code`). Do not add `cd_`, `custom_`,
  or any other namespace prefix
- Renaming or removing an existing field requires a data-migration patch in
  `connect_diagnostics_core/patches/` (see `remove_cd_prefix_from_custom_fields.py`)
- To reference a custom field in code, declare the `# ty: ignore` with the source
  `setup/*.py` file

### Print Audit Log

- Every real print and every PDF download is recorded as a `Print Log` row. Rows are
  insert-only: no role has write or delete permission, the DocType is `in_create`, and
  there is no auto-purge — retention is a legal concern, not housekeeping.
- The two channels are hooked differently because Frappe exposes them differently.
  PDF goes through `/api/method/frappe.utils.print_format.download_pdf`, so
  `override_whitelisted_methods` wraps it and the client cannot skip it; the wrapper must
  keep the original signature **and** `allow_guest=True`. The Print button loads the
  `/printview` route instead and cannot be overridden, so it is detected server-side from
  `frappe.form_dict.trigger_print` while the template renders.
- Coverage is every app-owned Print Format. The four configuration-driven formats record
  themselves through the print context; the rest call `{{ register_print(doc) }}`. That call
  must sit **outside** any leading `{# ... #}` comment, or it is silently swallowed.
- Previews are deliberately not recorded, and neither are emailed PDFs.
- **Two deliberate deviations from the general rules, both required by the feature.** A print
  render is a GET that Frappe does not commit, so the insert calls `frappe.db.commit()` inside
  a read request; enqueuing was rejected because an audit trail must not disappear when
  workers are down. And logging is fail-open: failures go to `frappe.log_error` with full
  context and never block printing. Do not "fix" either without changing this rule first.

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
