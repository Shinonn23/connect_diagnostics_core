---
name: frappe-bench-console
description: Run bounded server-side inspection or migration-support scripts through the approved Frappe Bench console without bypassing repository migration rules.
---

# Frappe Bench Console

Use the approved development Bench and site recorded in the repository/app policy.

Typical interactive entry:

```bash
cd /home/erp/frappe
bench --site deverp.connectdiagnostics.net console
```

For repeatable work, keep the script in the repository and execute it from the console:

```python
exec(open("/absolute/path/to/script.py").read(), globals())
```

Use site-scoped Frappe APIs and explicit database transaction controls. Never hardcode credentials or persist site-specific state in module globals.

The console is not a substitute for schema/configuration ownership:

- Third-party Custom Fields and Property Setters are changed through Customize Form and exported with Sync on Migrate.
- Data migrations belong in app patches and run through the normal migration workflow.
- Do not use ad hoc console writes to create permanent configuration that should be represented by code-managed app artifacts.
