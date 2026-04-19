Create a pull request following project conventions. Run these steps in order.

## Step 1: Pre-flight checks

Before creating the PR, verify:

1. **Pre-commit passes**: `pre-commit run --all-files` — fix if it fails
2. **All changes committed**: `git status` must show clean working tree
3. **Branch is pushed**: `git push -u origin HEAD` if not already pushed
4. **CI status**: `gh pr checks` or check GitHub Actions — must be passing

If any check fails, stop and fix before proceeding.

## Step 2: Gather context

Collect information for the PR body:

```bash
# All commits on this branch vs base
git log developments..HEAD --oneline

# Full diff summary
git diff developments...HEAD --stat

# Detailed changes
git diff developments...HEAD
```

## Step 3: Branch scope check

Verify all changed files are within the scope defined by the current branch name. Infer scope from the branch prefix:

- `feature/X` — changes should relate to feature X
- `fix/X` — changes should fix the specific issue X
- `hotfix/X` — changes should be limited to the critical fix X
- `config/X` — changes should be configuration only
- `refactor/X` — changes should be refactoring in area X
- `test/X` — changes should be test files only

If changes span beyond the scope implied by the branch name, warn the user.

## Step 4: PR title

Use conventional commit format (same as commit messages):

```
feat: add product registration validation
fix: correct Thai year calculation in autoname
refactor: simplify employment type format check
test: add employee autoname workflow tests
chore: update CI to run on developments branch
```

Keep under 70 characters.

## Step 5: PR body

Use this template:

```
## Summary

- <1-3 bullet points describing what changed and why>

## Changes

<If more than 3 commits, list the significant ones>
- `api/<system>/<file>.py` — <what changed>
- `hooks.py` — <what changed>
- `tests/<file>.py` — <what changed>

## Test plan

- [ ] <Specific manual test or verification step>
- [ ] `bench --site test_site run-tests --app connect_diagnostics_core --test <test_name>`
- [ ] <UI verification if applicable>

## Screenshots (if UI changes)

<Attach screenshots of before/after for any visual changes>
```

## Step 6: Review checklist

Before creating the PR, verify:

- [ ] All changes stay within branch scope
- [ ] No auto-generated files modified (DocType JSONs, type blocks, `__init__.py`)
- [ ] Type hints on all function signatures
- [ ] Tests cover new functionality
- [ ] No security vulnerabilities (SQL injection, XSS, permission bypass)
- [ ] Copyright header present on all Python files
- [ ] Follows Frappe naming and module conventions

## Step 7: Create the PR

**Target branch must be `developments`.** This is the only allowed base branch for PRs.

```bash
gh pr create --base developments --title "<title>" --body "<body>"
```

If the user requests a different target branch, **refuse and explain** that all PRs must go through `developments` first. No exceptions.

## Step 8: Post-creation

- Share the PR URL
- Verify CI is triggered: `gh pr checks`
- Remind the user: CI must pass before merge

## Do NOT

- Target any branch other than `developments` — all PRs must go to `developments` first
- Force push to shared branches (`production`, `user-acceptance-testing`, `developments`)
- Create PRs with failing CI
- Include sensitive files (.env, credentials, secrets)
- Merge without CI passing
