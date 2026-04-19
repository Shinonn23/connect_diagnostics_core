Create a new test file for a Frappe doctype or feature. Ask the user for these details before generating:

1. **What to test** — a doctype, API function, or workflow (e.g., "Employee autoname", "Product Registration validation")
2. **Test type** — unit or functional?

## Test Types

| Type           | Purpose                             | Scope        | Example                             |
| -------------- | ----------------------------------- | ------------ | ----------------------------------- |
| **Unit**       | Test a single function in isolation | One function | `validate_employment_type_format()` |
| **Functional** | Test a complete feature workflow    | One feature  | Employee autoname with Thai year    |

## Folder Structure

```
connect_diagnostics_core/
├── cd_stock/
│   └── doctype/
│       └── product_registration/
│           └── test_product_registration.py      # Unit tests
├── connect_diagnostics_core/
│   ├── doctype/
│   │   └── rename_tool_v2/
│   │       └── test_rename_tool_v2.py            # Unit tests
│   └── tests/                                    # Functional tests
│       ├── test_employee_autoname_format.py
│       └── test_utils.py                         # Shared test helpers
└── tests/                                        # Reserved for E2E (future)
```

### Rules

- **Unit tests** → `test_<doctype_name>.py` in the same directory as the source file (Frappe convention)
- **Functional tests** → `connect_diagnostics_core/tests/test_<feature>.py`
- **E2E tests** → `tests/` at app root (when implemented)

## Writing Unit Tests

```python
# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from frappe.tests.utils import FrappeTestCase
from unittest.mock import patch


class TestProductRegistration(FrappeTestCase):

    def test_valid_registration_creates_successfully(self):
        doc = frappe.get_doc({
            "doctype": "Product Registration",
            "registration_number": "TEST-001",
            "registration_type": "FDA",
        })
        doc.insert()
        self.assertEqual(doc.status, "Pending")

    def test_duplicate_registration_number_raises_error(self):
        frappe.get_doc({...}).insert()
        with self.assertRaises(frappe.ValidationError):
            frappe.get_doc({...}).insert()
```

### Patterns

- Always extend `FrappeTestCase`
- One test method per behavior — don't test multiple things in one method
- Use `setUp()` / `tearDown()` for shared test data
- Clean up created documents in `tearDown()` to avoid polluting test site
- Mock external calls (API, email, file system) with `unittest.mock.patch`

## Writing Functional Tests

```python
class TestEmployeeAutonameWorkflow(FrappeTestCase):

    def test_autoname_generates_thai_year_format(self):
        emp_type = frappe.get_doc({
            "doctype": "Employment Type",
            "name": "Test FT",
            "custom_format": "YYMM.###",
        }).insert()

        employee = frappe.get_doc({
            "doctype": "Employee",
            "employment_type": emp_type.name,
        }).insert()

        self.assertRegex(employee.name, r"\d{4}\.\d{3}")
```

### Patterns

- Test complete workflows, not just single functions
- Cover edge cases: empty inputs, boundary values, Thai-specific logic
- Use real Frappe documents (insert/delete) when possible, mock only external services

## Naming Convention

| Element | Convention                    | Good                                     | Bad             |
| ------- | ----------------------------- | ---------------------------------------- | --------------- |
| File    | `test_<what>.py` (snake_case) | `test_product_registration.py`           | `test1.py`      |
| Class   | `Test<Feature>` (PascalCase)  | `TestProductRegistration`                | `test_product`  |
| Method  | `test_<expected_behavior>`    | `test_validates_registration_uniqueness` | `test_it_works` |

## What Must Have Tests

- All hook handlers (validate, autoname, on_submit, etc.)
- All whitelisted API methods
- Custom validation logic
- Data transformation functions
- CSV/file processing logic
- Error handling paths

## What Can Skip Tests

- Frappe boilerplate (standard CRUD that Frappe handles)
- Simple field configurations
- Auto-generated code

## After generation

1. Run `ruff check` and `ruff format` on all created/modified files
2. Verify the test file is discoverable by Frappe's test runner
3. Provide the bench command to run just this test:

    ```bash
    # Specific test file
    bench --site test_site run-tests --app connect_diagnostics_core --test test_<name>

    # Specific test class
    bench --site test_site run-tests --app connect_diagnostics_core --test Test<Name>

    # All tests for the app
    bench --site test_site run-tests --app connect_diagnostics_core

    # With coverage
    bench --site test_site run-tests --app connect_diagnostics_core --coverage
    ```

## Do NOT

- Modify any `.json` files (DocType definitions are auto-generated by Frappe)
- Create tests that depend on specific site data
- Use `unittest.TestCase` instead of `FrappeTestCase`
- Add dependencies that don't exist in the project

## Next step

If tests pass → `/ship` to quality check + commit + create PR
