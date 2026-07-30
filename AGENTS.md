# Connect Diagnostics Core — Project Rules

Custom ERPNext app for Connect Diagnostics. Codex loads this file as persistent
project guidance. It is the contract for how we work: behavioral/engineering rules plus
**how we branch, version, and ship**. Workflow narrative:
[`.github/WORKFLOW.md`](.github/WORKFLOW.md).

> For procedural guides, invoke the repository skills:
> `$ship-pr` `$dispatch-test` `$test-result` `$promote-uat` `$promote-prod`
> `$commit` `$pr` `$review` `$security-audit` and `$erpnext-docs`.

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
  `$promote-uat --bypass-test "<reason>"`; a bypass is not certification and must
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
| `$ship-pr`                                       | from a work branch → ready-to-merge PR into `developments`; dispatch testing only after DEV deployment      |
| `$dispatch-test <PR#>`                           | bind a manual-test task to the exact deployed environment and commit                                          |
| `$test-result <PR#\|issue#> pass\|fail [reason]` | record revision-bound results; map failures and create post-PROD holds                                         |
| `$promote-uat [--bypass-test "<reason>"]`        | gate tests; record matching PR and source-issue bypass audit markers                                           |
| `$promote-prod`                                  | map UAT batches; enforce holds, approvals, audits, and remediation-only releases                            |

## Board #6 reference (for skills using `gh project`)

- Owner `Shinonn23`, project number `6`, id `PVT_kwHOB1tcMM4BLM7I`
- **Status** field `PVTSSF_lAHOB1tcMM4BLM7Izg62NJg`: TODO `f75ad846` · DEV Ready `61e4505c` · Dev In progress `47fc9ee4` · Dev review `df73e18b` · Test In progress `18955566` · Test Review `6c769416` · UAT Deploy `98236657` · PROD Deploy `dba9dd7f` · Hold `232c6587`
- **Test Status** field `PVTSSF_lAHOB1tcMM4BLM7IzhWdi_0`: Not Tested `9d66b7d0` · Testing `2556afad` · Passed `97d946bc` · Failed `15087b1c`
- **Tested By** field `PVTF_lAHOB1tcMM4BLM7IzhWdjBE` (text)
- Set a value: `gh project item-edit --id <ITEM_ID> --field-id <FIELD_ID> --project-id PVT_kwHOB1tcMM4BLM7I --single-select-option-id <OPT_ID>` (text fields use `--text`).
- An issue's board **item id** comes from `gh project item-list 6 --owner Shinonn23 --format json --limit 1000`.

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
- A final Codex review (`codex review --uncommitted` or `$review`) has no unresolved issues
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
5. **Cross-reference usage** — use `rg` for the function/class name across all apps to find indirect callers (JS form scripts, Jinja templates, background jobs, scheduled tasks)

If not found after all five steps: **stop and ask**. Do not assume it doesn't exist.

### Codebase Knowledge Cache

- **Before starting any non-trivial task**, check `.codex/knowledge/` for existing notes on the relevant topic; read them before re-exploring the codebase
- **After completing any non-trivial task**, update the relevant knowledge note directly
  - Knowledge files: `.codex/knowledge/<topic>.md` — lowercase, hyphen-separated names (e.g., `employee-autoname.md`, `customer-hooks.md`)
  - Contents: key files, functions/hooks used, patterns, non-obvious constraints
- Update the file if new findings extend or contradict prior notes
- `.codex/knowledge/` is an internal AI working directory — do not commit it (add to `.gitignore`)

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
- **DocTypes**: never hand-edit JSON files — use Frappe desk
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
  the Customer naming series. Customer Code cannot be changed after activation.
- `Customer Onboarding` keeps new Customers disabled from Customer Request through
  duplicate verification and accounting/credit review. The accounting reviewer
  activates a ready Customer directly; there is no external-system setup state.
  Active is the sole transaction-eligible state. Workflow Actions provide internal
  role notifications; the Customer workflow does not send email.
- A reviewer must save `Correction Reason` before selecting Return for correction.
  The reason remains visible to Sales and is cleared when the Customer is sent for
  duplicate verification again, so a later return requires a newly documented reason.
- Activation requires tax-invoice readiness plus delivery readiness (or a documented
  no-delivery reason). Tax readiness requires one active primary Billing Address
  whose Thai address, tax ID, and branch code match Customer; delivery readiness
  requires one active preferred Shipping Address and one primary Contact with a
  name and mobile/phone. These readiness fields are informational for documents,
  but are an Active gate.
- Customer Onboarding State, Correction Reason, document-readiness fields, and
  no-delivery controls belong in the dedicated Customer Onboarding tab, not Details.
- Customer `Document / Print Preferences` uses fixed sections for Quotation,
  Tax Invoice, Delivery Note, Invoice, Abbreviated Tax Invoice, and Receipt.
  New Customers enable every document, show its date, use Thai, and default to
  one original plus zero copies. Disabling a document hides but retains its settings.
  A source Purchase Order copy is a separate attachment preference with one copy
  by default. The legacy global `print_date` remains editable until Print Formats
  consume the per-document settings.
- Customer Quotation defaults also store Form Preset, signatory type, validity
  mode, optional custom validity text, and required Delivery Terms when Use
  Quotation is enabled. Form 01 is the default: show the date, use the first Sales
  Team Sales Person, and express validity from Valid Till.
- The Quotation `Print Configuration` tab snapshots the selected Customer's print
  defaults whenever the Customer changes in Draft. Presets 01–04 fill date,
  signatory, and validity choices but do not lock them; later edits mark the preset
  Custom. Sales Representative
  signatories must link through Sales Person to Employee. Managing Director
  signatories use `Company.quotation_authorized_signatory_employee`. The single
  Quotation Print Format renders Thai, English, or Thai / English and produces the
  configured original and copy pages. Delivery Terms are a required editable
  snapshot on every Quotation and print in the delivery commitment line. Print
  configuration remains editable after submission, and Quotation change tracking
  provides the Version audit.
- Later `Customer Credit Request` is available to every active Customer and is
  approved by the Customer Credit Approver; it does not depend on a channel field.
  `GOV. HOSPITAL` credit is set by the accounting reviewer during onboarding;
  other Customers start on Cash terms.
- Customer, Item, and Supplier keep their current document names and codes. Do not
  add conversion flags or automatically rename these masters. `Item.dksh_item_code`
  and the DKSH reference fields `supplier_product_code`, `mat_group_code`,
  `mat_group4_code`, and `material_type_code` are grouped on the Item's DKSH tab.
  They are optional reference data only and must not control Item lifecycle or
  transaction eligibility.
- Sales Order uses the standard `item_code` grid and standard ERPNext behavior for
  every Company. Do not force a selling Price List, Skip Delivery Note, external
  order status, or Company-specific Item link query.
- The retired mapping doctypes, workflow, roles, Sales Order fields, and dedicated
  selling Price List must not be recreated. Retirement migrations may delete only
  those explicitly retired records and fields; they must not rename or delete
  Customer, Item, Supplier, Asset, or historical transactions.
- The retired DKSH APIs and hooks are explicitly exempt from the usual one-release
  deprecation period because this domain was removed before go-live. Do not restore
  compatibility stubs for them.

### Custom Fields

- Custom fields are code-managed: define them in `connect_diagnostics_core/setup/<doctype>.py`
  (`CUSTOM_FIELDS` / `PROPERTY_SETTERS`), applied idempotently on `after_install` and
  `after_migrate` — do not create fields ad hoc via desk or console
- Print Formats are app-owned only: `after_sync` and `after_migrate` remove every
  `Print Format` whose module is not one of the app modules (`Connect Diagnostics Core`,
  `Connect Diagnostics Stock`, or `Connect Diagnostics Accounting`) or an ERPNext Thailand
  module (`Thai Tax`, `Thai Billing`, `Thai Deposit`, or `Petty Cash`). Retired formats are
  removed explicitly; `Sales Invoice Print` is retired and Sales Invoice defaults to
  `Tax Invoice Delivery Note and Invoice`. `Withholding Tax Cert` is owned by ERPNext Thailand;
  do not add a duplicate app-owned Print Format. Do not add a Print Format fixture that restores
  records from other modules.
- Print Format Jinja must be ordered as comment, derived variables, pagination, then HTML.
  Use a namespaced root class, scope CSS beneath that root, keep CSS out of the HTML field,
  and prefer semantic `header`, `section`, `table`, and `footer` elements. Use physical
  dimensions in `mm`; app-owned Print Formats must not use a background image. `Shipment Box
  Label` is a 180 × 100 mm landscape Shipment format that uses `cd_logo_v2.jpg`, splits sender
  and recipient details, and shows the recipient Customer's Territory only when present.
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
