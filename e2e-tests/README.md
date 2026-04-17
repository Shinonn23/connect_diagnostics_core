# E2E Test Suite — Connect Diagnostics ERPNext

Playwright E2E test suite — functional testing and Google Sheets master data validation.

**Target:** `https://dev.connectdiagnostics.nomeaparadigm.com`

## Quick Start

```bash
npm install
npx playwright install chromium
cp .env.example .env
# Edit .env — set ERP_PASSWORD
```

### Google Sheets Auth (ต้องทำครั้งเดียว)

```bash
gcloud auth application-default login \
  --scopes="https://www.googleapis.com/auth/cloud-platform,https://www.googleapis.com/auth/spreadsheets.readonly" \
  --client-id-file=<path-to-desktop-oauth-client.json>
```

## NPM Scripts

**Functional Tests (52 tests) — ไม่ต้องมี Google Auth**

```bash
npm test                  # Run all functional tests
npm run test:headed       # Run with visible browser
npm run test:login        # 01 - Login & Navigation only
npm run test:master       # 02 - Master Data only
npm run test:accounting   # 03 - Accounting & Stock only
npm run test:hr           # 04 - HR & Payroll only
npm run test:custom       # 05 - Custom Apps + Data Integrity only
```

**Google Sheets Validation (22 tests) — ต้องมี Google Auth**

```bash
npm run test:validate         # All validation tests (17 + 5)
npm run test:excel            # 17 master sheets only
npm run test:stock-validate   # 5 stock sheets only
```

## Project Structure

```
e2e-tests/
├── e2e/                          # Playwright test specs
│   ├── auth.setup.ts
│   ├── 01-login.spec.ts          # 8 tests
│   ├── 02-master-data.spec.ts    # 20 tests
│   ├── 03-accounting-stock.spec.ts # 6 tests
│   ├── 04-hr-payroll.spec.ts     # 6 tests
│   ├── 05-custom-apps.spec.ts    # 12 tests
│   ├── master-validation.spec.ts # 17 tests (Google Sheets vs API)
│   ├── stock-validation.spec.ts  # 5 tests (Google Sheets vs API)
│   └── validate.fixture.ts
├── lib/                          # Data processing modules
│   ├── sheets-reader.ts          # Google Sheets API reader (ADC / Service Account)
│   ├── frappe-api.ts             # API helper (for functional tests)
│   ├── frappe-client.ts          # Standalone API client
│   ├── validator.ts              # Sheet vs API validation engine
│   ├── column-map.ts             # Sheet field mappings + aliases
│   └── comparator.ts             # Server vs Server comparison
├── scripts/                      # Standalone scripts
│   ├── gsheets-reader.js         # Google Sheets reader
│   └── run-master-test.js        # Data comparison runner
├── docs/
│   └── DOCUMENTATION.md          # Full documentation
├── playwright.config.ts
├── tsconfig.json
└── .env.example
```

## Test Results

| Type | Tests | Need Google Auth? |
|------|-------|-------------------|
| Functional | 52 | No |
| Sheets Validation | 22 | Yes (ADC) |
| Data Compare | 3 | Yes |
| **Total** | **77** | |

## Environment

```env
BASE_URL=https://dev.connectdiagnostics.nomeaparadigm.com
ERP_USERNAME=Administrator
ERP_PASSWORD=<set in .env>
GOOGLE_SHEET_ID=1P40NXIF72wm4YVLfqN0l3-W3GXLt2GVraVLY9bKZXFQ
```

## Documentation

- **[docs/DOCUMENTATION.md](docs/DOCUMENTATION.md)** — Complete project documentation
