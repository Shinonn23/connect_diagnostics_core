Create a new Frappe bench custom CLI command. Ask the user for these details before generating:

1. **Command name** — kebab-case, used as `bench <command-name>` (e.g., `sync-products`, `rename-bulk`)
2. **Description** — what the command does (one sentence)
3. **Complexity** — simple (single file) or complex (own module directory)?
4. **Options** — list of CLI options needed (name, type, required, help text). If none, generate a minimal command.

## Frappe Command Structure

Commands live in `connect_diagnostics_core/commands/` directory. Each command uses Click decorators.

### Simple command — single file

For small commands (1-2 functions), create a single file:

`connect_diagnostics_core/commands/<command_name>.py`:

```python
# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

import click


@click.command("<command-name>")
@click.option(
    "--option-name",
    required=True,
    help="Description of this option.",
)
def <command_name>(option_name: str):
    """One-line description shown in bench --help."""
    pass
```

### Complex command — module directory

For larger commands with multiple helpers, sub-functions, or logic that needs separation:

```
connect_diagnostics_core/commands/<command_name>/
├── __init__.py       # Contains @click.command entry point
├── helpers.py        # Helper functions
├── processor.py      # Core processing logic
└── ...
```

`connect_diagnostics_core/commands/<command_name>/__init__.py`:

```python
# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

import click

from .processor import process_data


@click.command("<command-name>")
@click.option(
    "--option-name",
    required=True,
    help="Description.",
)
def <command_name>(option_name: str):
    """One-line description shown in bench --help."""
    process_data(option_name)
```

### Step: Update top-level `__init__.py`

`connect_diagnostics_core/commands/__init__.py` must export all commands:

If it does NOT exist, create it:

```python
from .<command_name> import <command_name>

commands = [<command_name>]
```

If it already exists, append the import and add to `commands` list:

```python
from .existing_command import existing_command
from .<command_name> import <command_name>

commands = [existing_command, <command_name>]
```

Note: For complex commands (module directory), the import targets `commands/<command_name>/__init__.py` which contains the `@click.command` — the import syntax is the same either way.

### Important rules

- Use `@click.option()` for every CLI parameter — no bare arguments
- Always include `required=True/False` and `help=""` on every option
- Use Python type hints on the function parameters
- `@click.command()` name uses hyphens (kebab-case): `@click.command("my-command")`
- Python function name uses underscores (snake_case): `def my_command(...)`
- If the command needs Frappe context, use `with frappe.init_site():` and `frappe.connect()`

```python
import frappe

@click.command("my-command")
def my_command():
    """Description."""
    with frappe.init_site():
        frappe.connect()
        # logic here
        frappe.db.commit()
```

### After generation

1. Run `ruff check` and `ruff format` on all created/modified files
2. Summarize what was created and how to run the command
3. Show example usage: `bench <command-name> --option value`

### Do NOT

- Modify `hooks.py` — Frappe discovers commands from the `commands/` package automatically
- Add external dependencies — only use `click`, `frappe`, and Python stdlib
- Create files outside `connect_diagnostics_core/commands/`

## Next step

1. Manual test: `bench <command-name> --option value`
2. `/scaffold-test` to create test suite
3. If tests pass → `/ship` to commit + PR
