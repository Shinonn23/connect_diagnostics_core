### Connect Diagnostics Core

Custom app for Connect Diagnostics to manage and implement company-specific business logic, workflows, and processes on ERPNext.

### Installation

You can install this app using the [bench](https://github.com/frappe/bench) CLI:

```bash
cd $PATH_TO_YOUR_BENCH
bench get-app $URL_OF_THIS_REPO --branch develop
bench install-app connect_diagnostics_core
```

### Contributing

This app uses `pre-commit` for code formatting and linting. Please [install pre-commit](https://pre-commit.com/#installation) and enable it for this repository:

```bash
cd apps/connect_diagnostics_core
pre-commit install
```

Pre-commit is configured to use the following tools for checking and formatting your code:

- ruff
- eslint
- prettier
- pyupgrade

### CI

This app can use GitHub Actions for CI. The following workflows are configured:

- CI: Installs this app and runs unit tests on every push to `develop` branch.
- Linters: Runs [Frappe Semgrep Rules](https://github.com/frappe/semgrep-rules) and [pip-audit](https://pypi.org/project/pip-audit/) on every pull request.

### E2E Testing (Playwright)

Automated E2E test suite — functional testing and Google Sheets master data validation.

```bash
cd e2e-tests
npm install
npx playwright install chromium
cp .env.example .env   # set ERP_PASSWORD
npx playwright test --project=validate --reporter=list
```

See **[e2e-tests/README.md](e2e-tests/)** for full documentation.

### License

bsl-1.0
