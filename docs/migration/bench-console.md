# Bench console

Use the development Bench at `/home/erp/frappe` and the development site
`deverp.connectdiagnostics.net` for server-side checks. Run commands from the Bench root:

```bash
cd /home/erp/frappe
bench --site deverp.connectdiagnostics.net console
```

For a repeatable script, keep the script in the repository and execute it from the console:

```python
exec(open("/absolute/path/to/script.py").read(), globals())
```

Use the site-scoped Frappe APIs and database transaction controls in the script. Do not put
site-specific values in module-level state, hardcode credentials, or make schema changes from
the console. Schema and custom-field changes belong in the app's code-managed setup modules and
patches, then run through the normal migration workflow.
