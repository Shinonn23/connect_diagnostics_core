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

Automated E2E test suite for Connect Diagnostics ERPNext — functional testing, Excel data validation, and export scripts.

**Target:** `https://dev.connectdiagnostics.nomeaparadigm.com`

#### Quick Start

```bash
npm install
npx playwright install chromium
cp .env.example .env
# Edit .env — set ERP_PASSWORD
```

#### เตรียม Excel Master Data (สำหรับ Excel Validation เท่านั้น)

```bash
mkdir data
# วางไฟล์ CD-ERPNext Master Data v.3*.xlsx ใน data/ folder
```

ถ้าไม่มี `data/` ระบบจะหา Excel ที่ Desktop อัตโนมัติ

#### NPM Scripts

**Functional Tests (82 tests) — ไม่ต้องมีไฟล์ Excel**

```bash
npm test                  # Run all functional tests
npm run test:headed       # Run with visible browser
npm run test:login        # 01 - Login & Navigation only
npm run test:master       # 02 - Master Data only
npm run test:accounting   # 03 - Accounting & Stock only
npm run test:hr           # 04 - HR & Payroll only
npm run test:custom       # 05 - Custom Apps + Data Integrity only
```

**Excel Validation (22 tests) — ต้องมี Excel file ใน data/ หรือ Desktop**

```bash
npm run test:validate         # All validation tests (15 + 5)
npm run test:excel            # 15 master sheets only
npm run test:stock-validate   # 5 stock sheets only
```

**Export Scripts — ส่งออกผลเป็น Excel**

```bash
node scripts/export-api-vs-excel.js    # Export Dev API vs Excel → .xlsx
node scripts/check-final.js            # COA + Item Prices deep analysis
```

#### Project Structure

```
├── e2e/                          # Playwright test specs
│   ├── auth.setup.ts
│   ├── 01-login.spec.ts          # 8 tests
│   ├── 02-master-data.spec.ts    # 20 tests
│   ├── 03-accounting-stock.spec.ts # 16 tests
│   ├── 04-hr-payroll.spec.ts     # 14 tests
│   ├── 05-custom-apps.spec.ts    # 12 tests
│   ├── master-validation.spec.ts # 15 tests
│   ├── stock-validation.spec.ts  # 5 tests
│   └── validate.fixture.ts
├── lib/                          # Data processing modules
│   ├── frappe-api.ts             # API helper (for functional tests)
│   ├── frappe-client.ts          # Standalone API client
│   ├── validator.ts              # Excel vs API validation engine
│   ├── column-map.ts             # Sheet field mappings
│   ├── excel-reader.ts           # Read Excel from data/ or Desktop
│   └── comparator.ts             # Server vs Server comparison
├── scripts/                      # Standalone scripts
│   ├── export-api-vs-excel.js    # Export Dev API vs Excel → .xlsx
│   ├── check-final.js            # COA + Item Prices deep check
│   └── ...
├── data/                         # Excel Master Data files (gitignored)
├── docs/
│   └── DOCUMENTATION.md          # Complete project documentation
├── playwright.config.ts
├── tsconfig.json
└── .env.example
```

#### Documentation

- **[docs/DOCUMENTATION.md](docs/DOCUMENTATION.md)** — Complete project documentation

### License

bsl-1.0
