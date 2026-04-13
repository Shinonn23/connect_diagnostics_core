# CD-ERPNext Playwright Automated Test Suite

Automated testing suite for **Connect Diagnostics** ERPNext system. Covers functional testing, Excel data validation, and export scripts.

## What it does

| Test Type | Tests | What it checks |
|-----------|-------|----------------|
| **Functional Tests** (01-05) | 82 | Login, navigation, permissions, master data, accounting, stock, HR, payroll, custom apps, data integrity |
| **Excel Validation** | 22 | Compare Excel Master Data vs ERPNext API field-by-field (15 master + 5 stock sheets) |
| **Export Scripts** | — | Export issues as .xlsx file for the team |

**Target:** `https://dev.connectdiagnostics.nomeaparadigm.com`

## Quick Start

```bash
npm install
npx playwright install chromium
cp .env.example .env
# Edit .env — set ERP_PASSWORD
npm test                    # Run all functional tests (82 tests, ~1 min)
```

## NPM Scripts

### Functional Tests (82 tests) — ไม่ต้องมีไฟล์ Excel

```bash
npm test                  # Run all functional tests
npm run test:headed       # Run with visible browser
npm run test:login        # 01 - Login & Navigation only
npm run test:master       # 02 - Master Data only
npm run test:accounting   # 03 - Accounting & Stock only
npm run test:hr           # 04 - HR & Payroll only
npm run test:custom       # 05 - Custom Apps + Data Integrity only
```

### Excel Validation (22 tests) — ต้องมี Excel file ใน data/ หรือ Desktop

```bash
npm run test:validate         # All validation tests (15 + 5)
npm run test:excel            # 15 master sheets only
npm run test:stock-validate   # 5 stock sheets only
```

### Export Scripts — ส่งออกผลเป็น Excel

```bash
node scripts/export-api-vs-excel.js    # Export Dev API vs Excel → .xlsx (ส่งทีม)
node scripts/check-final.js            # COA + Item Prices deep analysis
```

### Reports

```bash
npm run test:report       # Open HTML report
```

## Current Issues (Dev API vs Excel)

| Sheet | Issues | Detail |
|-------|--------|--------|
| Items | 39 | brand=null |
| Accounts | 11 | account_type empty=4, mismatch=7 (naming=79 ปกติ ERPNext) |
| Customers | 7 | customer_group ว่าง |
| Employees | 0 | All matched |
| Suppliers | 0 | All matched |

## Environment Variables

Copy `.env.example` to `.env` and fill in:

```env
BASE_URL=https://dev.connectdiagnostics.nomeaparadigm.com
ERP_USERNAME=Administrator
ERP_PASSWORD=          # Set your password
EXCEL_DIR=             # Optional: override Excel search path
```

## Project Structure

```
├── helpers/                    # Shared modules
│   ├── frappe-api.ts           # API helper (for functional tests)
│   ├── frappe-client.ts        # Standalone API client (for validation)
│   ├── validator.ts            # Excel vs API validation engine
│   ├── column-map.ts           # Sheet field mappings (skipWhen for Product Bundles)
│   ├── excel-reader.ts         # Read Excel from data/ or Desktop
│   └── comparator.ts           # Server vs Server comparison
├── tests/
│   ├── auth.setup.ts           # Login + create auth.json
│   ├── 01-login.spec.ts        # 8 tests
│   ├── 02-master-data.spec.ts  # 20 tests
│   ├── 03-accounting-stock.spec.ts  # 16 tests
│   ├── 04-hr-payroll.spec.ts   # 14 tests
│   ├── 05-custom-apps.spec.ts  # 12 tests
│   ├── validate.fixture.ts     # Custom fixture for Excel validation
│   ├── master-validation.spec.ts  # 15 tests
│   └── stock-validation.spec.ts    # 5 tests
├── scripts/                    # Standalone scripts
│   ├── export-api-vs-excel.js # Export Dev API vs Excel → .xlsx
│   ├── check-final.js          # COA + Item Prices deep check
│   └── ...                     # Debug/SQL comparison scripts
├── data/                       # Excel Master Data files (gitignored)
├── src/                        # Data Compare Engine
└── docs/
    ├── PROJECT-FLOW.md         # Full project flow & architecture
    └── TEST-FLOW.md            # Detailed test flow
```

## Documentation

- **[docs/PROJECT-FLOW.md](docs/PROJECT-FLOW.md)** — Full architecture, flow, and analysis
- **[docs/TEST-FLOW.md](docs/TEST-FLOW.md)** — Detailed flow of all tests
