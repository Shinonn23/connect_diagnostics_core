Fix the code in the specified file(s) to match project conventions. Ask the user which file(s) to fix, or fix all modified files if none specified.

## Step 1: Identify files to fix

If the user specified a file, use that. Otherwise, detect modified files:

```bash
git diff --name-only HEAD
git diff --name-only --cached
git ls-files --others --exclude-standard
```

Only process `.py`, `.js`, and `.ts` files. Skip auto-generated files (DocType JSONs, `__init__.py`, files with auto-gen markers).

## Step 2: Fix Python files

For each `.py` file, apply these fixes in order:

### Copyright header

Ensure the file starts with:

```python
# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt
```

Skip if the file already has it, or if it is a Frappe-generated doctype controller (contains `# begin: auto-generated types`).

### Type annotations

All function signatures must have type hints:

```python
# BAD (vibecoded)
def validate(doc, method):
    pass

# GOOD (project convention)
def validate(doc: Document, method: str) -> None:
    pass
```

For hook functions: `(doc: Document, method: str) -> None`
For whitelisted APIs: include parameter types and return type

### Import order

Fix to: stdlib → third-party → frappe → local modules

```python
import re
from typing import Any, cast

import frappe
from frappe.model.document import Document
from frappe import _

from connect_diagnostics_core.api.erpnext.employment_type import validate_employment_type_format
```

- Remove unused imports
- Remove wildcard imports (`from frappe import *`)
- Do NOT modify the auto-generated types block

### Method guards

Hook functions should guard on method:

```python
def validate(doc: Document, method: str) -> None:
    if method != "validate":
        return
    # validation logic
```

### doc.get() with cast()

Replace bare `doc.get()` with typed casts:

```python
# BAD
value = doc.get("field_name")

# GOOD
value: str = cast(str, doc.get("field_name") or "")
```

### Maximize type coverage

Add `cast()` for `frappe.get_doc()` calls to narrow to the specific DocType:

```python
# BAD
doc = frappe.get_doc("Product Registration", name)

# GOOD
doc = cast(ProductRegistration, frappe.get_doc("Product Registration", name))
```

For direct attribute access to custom fields (not in type stubs), add `# ty: ignore` with source:

```python
# BAD
doc.custom_field = value

# GOOD
doc.custom_field = value  # ty: ignore[unresolved-attribute] - runtime-injected attribute (cd_stock/custom/item.json)
```

- Custom field definitions are in `connect_diagnostics_core/cd_stock/custom/*`
- Only use `# ty: ignore` when truly unavoidable — always specify the source file
- Check custom field JSON files to determine the correct source

### Error handling

Replace generic exceptions with `frappe.throw()`:

```python
# BAD
raise ValueError("Invalid format")

# GOOD
frappe.throw("Invalid format")
```

### DocType controllers

If the file is a doctype controller (`**/doctype/**/<name>.py`):

- Do NOT modify the auto-generated types block (between `# begin/end: auto-generated types`)
- Do NOT add imports inside the types block
- Keep the class minimal — let Frappe do the heavy lifting

## Step 3: Fix JavaScript files

For each `.js`/`.ts` file:

- Use tabs for indentation (not spaces)
- Use `frappe.call()` for server calls — no raw `fetch` or `$.ajax`
- Use Frappe globals already declared in `.eslintrc` (`cur_frm`, `frappe`, `locals`, etc.)
- Keep form scripts minimal — delegate logic to Python APIs

```javascript
// GOOD (project convention)
frappe.ui.form.on("DocType Name", {
	refresh(frm) {
		// logic
	},
	field_name(frm) {
		// field-specific logic
	},
});
```

## Step 4: Run formatters

After all fixes:

```bash
ruff check --fix <files>
ruff format <files>
```

## Step 5: Report changes

Summarize what was fixed per file:

- [x] Copyright header added
- [x] Type annotations added to N functions
- [x] Import order fixed
- [x] Method guard added to N hook functions
- [x] doc.get() calls typed with cast()
- [x] Error handling updated to frappe.throw()
- [x] ruff check/format applied

## Do NOT

- Modify `.json` files (DocType definitions)
- Modify `__init__.py` files
- Modify auto-generated type blocks
- Change business logic — only fix style and conventions
- Add new dependencies
- Refactor working code beyond style fixes

## Next step

- `/check` to validate conventions
- If passing → `/commit` or `/ship`
