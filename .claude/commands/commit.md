Prepare and create a commit following project conventions. Run these steps in order:

## Step 1: Pre-commit gate

Run `pre-commit run --all-files` first. If it fails, stop and fix the issues before continuing.

## Step 2: Branch scope check

Verify all changed files are within the scope defined by the current branch name. Infer scope from the branch prefix:

- `feature/X` — changes should relate to feature X
- `fix/X` — changes should fix the specific issue X
- `hotfix/X` — changes should be limited to the critical fix X
- `config/X` — changes should be configuration only
- `refactor/X` — changes should be refactoring in area X
- `test/X` — changes should be test files only

If changes span beyond the scope implied by the branch name, warn the user and suggest creating a separate branch.

## Step 3: Commit message format

Use conventional commits:

```
feat: add product registration validation
fix: correct Thai year calculation in autoname
refactor: simplify employment type format check
test: add tests for employee autoname workflow
chore: update CI to run on developments branch
```

One short sentence focused on the **why**, not the what.

## Step 4: Branch naming (for new branches)

Prefix with type and descriptive scope:

```
feature/employee-autoname-thai-year
fix/duplicate-registration-validation
hotfix/ci-broken-lint
refactor/api-module-organization
config/ai
```

## Step 5: Pre-commit review checklist

Before finalizing the commit, verify:

- [ ] All changes stay within branch scope
- [ ] No auto-generated files modified (DocType JSONs, type blocks, `__init__.py`)
- [ ] Type hints on all function signatures
- [ ] Tests cover new functionality
- [ ] No security vulnerabilities (SQL injection, XSS, permission bypass)
- [ ] Copyright header present on all Python files
- [ ] Follows Frappe naming and module conventions

## Step 6: Create the commit

1. Run `git status` to see all changed/untracked files
2. Stage only relevant files — be specific, avoid `git add -A`
3. Create the commit with the conventional commit message
4. Run `git status` after to verify success

## PR Rules (when creating PRs)

- Include summary, test plan, and screenshots for UI changes
- No force push to shared branches (`production`, `user-acceptance-testing`, `developments`)
- CI must pass before merge

## Do NOT

- Use `--no-verify` or `--no-gpg-sign` flags unless explicitly asked
- Amend existing commits without explicit request
- Force push to shared branches
- Commit sensitive files (.env, credentials, secrets)
