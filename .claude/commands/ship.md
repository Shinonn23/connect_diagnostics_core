End-to-end quality gate, commit, and PR in one command. Run all steps in order — stop if any step fails.

## Step 1: Fix style (quality gate)

Detect changed files:

```bash
git diff --name-only HEAD
git diff --name-only --cached
git ls-files --others --exclude-standard
```

Only process `.py`, `.js`, and `.ts` files. Skip auto-generated files (DocType JSONs, `__init__.py`, files with auto-gen markers).

For each file, apply fixes:

### Python files

- **Copyright header** — ensure starts with:

    ```python
    # Copyright (c) 2026, Siwat Sroisuwan and contributors
    # For license information, please see license.txt
    ```

    Skip if already present or if Frappe-generated doctype controller.

- **Type annotations** — all function signatures must have parameter + return types
- **Import order** — stdlib → third-party → frappe → local modules. Remove unused and wildcard imports.
- **Method guards** — hook functions guard on method name
- **Typed `doc.get()`** — `value: str = cast(str, doc.get("field") or "")`
- **`cast()` for `frappe.get_doc()`** — narrow to specific DocType
- **`# ty: ignore`** for custom field attribute access — always with source file
- **Error handling** — use `frappe.throw()`, not `raise`

### JavaScript files

- Tabs for indentation
- Use `frappe.call()` for server calls
- Use Frappe globals from `.eslintrc`

### Run formatters

```bash
ruff check --fix <files>
ruff format <files>
```

## Step 2: Validate conventions

For each changed file, verify all convention checks from `/check`:

### Python checks

| Check                | Pass if                                               |
| -------------------- | ----------------------------------------------------- |
| Copyright header     | Present on all non-generated files                    |
| Type hints           | All function signatures have parameter + return types |
| Import order         | stdlib → third-party → frappe → local                 |
| Wildcard imports     | None found                                            |
| Auto-generated block | Not modified                                          |
| DocType JSON         | Not modified                                          |
| `__init__.py`        | Not modified                                          |
| SQL injection        | All queries parameterized                             |
| Permissions          | All `@frappe.whitelist()` have permission checks      |
| Error handling       | Uses `frappe.throw()`                                 |
| Hook signatures      | `(doc: Document, method: str) -> None`                |

```bash
ruff check <files>
ruff format --check <files>
```

**If any check fails that cannot be auto-fixed → STOP and report to user. User must fix before proceeding.**

## Step 3: Pre-commit gate

```bash
pre-commit run --all-files
```

If it fails, attempt to fix. If unfixable → **STOP and report**.

## Step 4: Branch scope check

Verify all changed files are within the scope defined by the current branch name. Infer scope from the branch prefix:

- `feature/X` — changes should relate to feature X
- `fix/X` — changes should fix the specific issue X
- `hotfix/X` — changes should be limited to the critical fix X
- `config/X` — changes should be configuration only
- `refactor/X` — changes should be refactoring in area X
- `test/X` — changes should be test files only

If changes span beyond the scope implied by the branch name, **STOP** and warn the user.

## Step 5: Commit

1. Run `git status` to see all changed/untracked files
2. Draft a conventional commit message:
    ```
    feat: add product registration validation
    fix: correct Thai year calculation in autoname
    refactor: simplify employment type format check
    test: add tests for employee autoname workflow
    chore: update CI to run on developments branch
    ```
3. **Present the message to user for approval before committing**
4. Stage only relevant files — be specific, avoid `git add -A`
5. Create the commit
6. Run `git status` after to verify

### Pre-commit review checklist

Before finalizing, verify:

- [ ] All changes stay within branch scope
- [ ] No auto-generated files modified
- [ ] Type hints on all function signatures
- [ ] Tests cover new functionality
- [ ] No security vulnerabilities
- [ ] Copyright header present on all Python files

## Step 6: Create pull request

1. **Push**: `git push -u origin HEAD` if not already pushed
2. **Check CI**: verify CI is passing
3. **Gather context**:
    ```bash
    git log developments..HEAD --oneline
    git diff developments...HEAD --stat
    git diff developments...HEAD
    ```
4. **Draft PR title** (conventional commit format, under 70 chars)
5. **Draft PR body** using this template:

    ```
    ## Summary

    - <1-3 bullet points>

    ## Changes

    - `api/<system>/<file>.py` — <what changed>
    - `tests/<file>.py` — <what changed>

    ## Test plan

    - [ ] <manual test>
    - [ ] `bench --site test_site run-tests --app connect_diagnostics_core --test <test_name>`
    ```

6. **Present title + body to user for approval**
7. Create: `gh pr create --base developments --title "<title>" --body "<body>"`
8. Share PR URL and verify CI triggers

### PR rules

- **Target branch must be `developments`** — no exceptions
- CI must pass before merge
- No force push to shared branches

## Do NOT

- Use `--no-verify` or `--no-gpg-sign` flags
- Amend commits without explicit request
- Force push to shared branches
- Commit sensitive files
- Target any branch other than `developments`
- Skip any step — all steps must pass in order
