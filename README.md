# Connect Diagnostics Core

Custom ERPNext app for [Connect Diagnostics](https://connectdiagnostics.com) — extends Frappe/ERPNext with company-specific business logic, workflows, and processes for the healthcare diagnostics industry.

Built on the [Frappe Framework](https://frappeframework.com) with [ERPNext](https://erpnext.com), [ERPNext Thailand](https://github.com/aakvatech-labs/erpnext_thailand), and [HRMS](https://github.com/frappe/hrms) as required dependencies.

## What It Does

| Area                 | Customizations                                                                                 |
| -------------------- | ---------------------------------------------------------------------------------------------- |
| **Stock & Products** | Product registration with Thai FDA tracking, regulation classes, shipping/storage conditions   |
| **HR & Employees**   | Employee autoname with Thai Buddhist year format, employment type validation                   |
| **CRM**              | Customer and contact extensions                                                                |
| **Custom Fields**    | Extended standard DocTypes (Item, Item Barcode, Item Default) via `cd_` prefixed custom fields |

## Installation

```bash
cd $PATH_TO_YOUR_BENCH
bench get-app $URL_OF_THIS_REPO --branch develop
bench install-app connect_diagnostics_core
```

**Required apps** (installed automatically):

- `erpnext`
- `erpnext_thailand`
- `hrms`
- `helpdesk`

## Contributing

See [CONTRIBUTING.md](./CONTRIBUTING.md) for the full guide covering:

- Code style and conventions
- Branch and PR rules
- AI-assisted development workflow (Claude Code commands and pipeline)

Quick setup:

```bash
cd apps/connect_diagnostics_core
pre-commit install
```

## CI

GitHub Actions workflows:

- **CI** — installs the app and runs unit tests on every push to `developments`
- **Linters** — runs [Frappe Semgrep Rules](https://github.com/frappe/semgrep-rules) and [pip-audit](https://pypi.org/project/pip-audit/) on every pull request

## License

[bsl-1.0](./license.txt)
