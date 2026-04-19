Run project convention checks on changed files. If no files specified, check all modified files.

## Step 1: Detect changed files

```bash
# Staged + unstaged + untracked
git diff --name-only HEAD
git diff --name-only --cached
git ls-files --others --exclude-standard
```

Filter to `.py`, `.js`, `.ts` only. Skip `__init__.py` and auto-generated files.

## Step 2: Ruff checks

```bash
ruff check <files>
ruff format --check <files>
```

Report any failures.

## Step 3: Convention checks

For each changed file, verify:

### Python files

| Check                | How                                                   | Fail if                                                   |
| -------------------- | ----------------------------------------------------- | --------------------------------------------------------- |
| Copyright header     | File starts with `# Copyright (c) 2026`               | Missing on non-generated files                            |
| Type hints           | All function signatures have parameter + return types | Any function missing types                                |
| Import order         | stdlib → third-party → frappe → local                 | Wrong order detected                                      |
| Wildcard imports     | No `from X import *`                                  | Any wildcard import found                                 |
| Auto-generated block | Not modified                                          | Lines between `# begin/end: auto-generated types` changed |
| DocType JSON         | Not modified                                          | Any `.json` in `doctype/` directory changed               |
| `__init__.py`        | Not modified                                          | Module-level `__init__.py` changed                        |
| SQL injection        | All `frappe.db.sql()` uses parameterized queries      | Any string formatting/concatenation in SQL                |
| Permissions          | Whitelisted methods check `frappe.has_permission()`   | Any `@frappe.whitelist()` without permission check        |
| Error handling       | Uses `frappe.throw()` not `raise`                     | Any `raise ValueError/Exception` found                    |
| Hook signatures      | `(doc: Document, method: str) -> None`                | Different signature pattern                               |

### JavaScript files

| Check          | How                                           | Fail if                                  |
| -------------- | --------------------------------------------- | ---------------------------------------- |
| Indentation    | Uses tabs, not spaces                         | Spaces detected for indentation          |
| Frappe globals | Uses `cur_frm`, `frappe`, etc. from .eslintrc | Raw `fetch`, `$.ajax`, or `window.` used |

## Step 4: Report

Output a summary per file:

```
<file_path>
  ✅ Copyright header
  ✅ Type hints (5/5 functions)
  ❌ Import order: `frappe` import before `typing`
  ✅ No wildcard imports
  ✅ No auto-generated file modifications
  ✅ Security checks pass
```

Then a final tally:

```
Total: 5 files checked
Passed: 3 files
Failed: 2 files (4 issues)
  - api/erpnext/employee.py: import order
  - tests/test_feature.py: missing copyright header, 2 functions without type hints
```

## Step 5: Offer to fix

If issues found, ask: "Fix these issues automatically? (Y/n)"

If yes, run `/fix-style` on the failing files.

## Do NOT

- Modify any files (unless user approved fix)
- Run `ruff check --fix` without approval
- Check files outside the project scope

## Next step

If all checks pass → `/commit` or `/ship`
