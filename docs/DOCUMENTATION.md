# E2E Test Suite Documentation

## Overview

Playwright E2E test suite for Connect Diagnostics ERPNext (`dev.connectdiagnostics.nomeaparadigm.com`).

## Project Structure

```
connect_diagnostics_core/                    ← repo (Python Frappe app + E2E tests)
│
├── connect_diagnostics_core/                ← Python app code (เดิม)
├── typings/                                 ← Python type stubs (เดิม)
├── pyproject.toml                           ← Python project (เดิม)
│
├── e2e/                                     ← Playwright test specs
│   ├── auth.setup.ts                        ← Login → สร้าง auth.json
│   ├── 01-login.spec.ts                     ← 8 tests: session, modules, navigation
│   ├── 02-master-data.spec.ts               ← 20 tests: Company, Customer, Supplier, Item, Employee...
│   ├── 03-accounting-stock.spec.ts          ← Accounting Settings + Stock (transaction tests ลบแล้ว, TODO Phase 3)
│   ├── 04-hr-payroll.spec.ts                ← HR Setup + Leave Types (Payroll/Attendance ลบแล้ว, TODO Phase 3)
│   ├── 05-custom-apps.spec.ts               ← 12 tests: Thailand tax, custom apps, data integrity
│   ├── master-validation.spec.ts            ← 17 tests: Google Sheets master data vs API
│   ├── stock-validation.spec.ts             ← 5 tests: Google Sheets stock data vs API
│   ├── master-data-compare.spec.ts          ← 3 tests: Dataset comparison
│   └── validate.fixture.ts                  ← Custom Playwright fixture (Google Sheets + FrappeClient)
│
├── lib/                                     ← Data processing modules
│   ├── frappe-api.ts                        ← API helper (Playwright request context)
│   ├── frappe-client.ts                     ← Standalone API client
│   ├── validator.ts                         ← Sheet vs API field-by-field validation engine
│   ├── column-map.ts                        ← Sheet → field mapping (17 sheets)
│   ├── excel-reader.ts                      ← อ่าน Google Sheets API (Service Account / ADC)
│   └── comparator.ts                        ← Server vs Server comparison
│
├── scripts/                                 ← Standalone scripts
│   ├── gsheets-reader.js                    ← Google Sheets reader (standalone, ใช้ googleapis + ADC)
│   ├── export-api-vs-excel.js               ← Export API vs data → .xlsx
│   ├── export-detailed-report.js            ← Export detailed validation report → .xlsx
│   ├── export-results.js                    ← Export validation results
│   ├── check-final.js                       ← COA + Item Prices deep check
│   ├── run-master-test.js                   ← Data comparison runner
│   ├── compare.ts                           ← Core comparison engine
│   ├── datasets.ts                          ← Dataset config loader
│   ├── frappe.ts                            ← FrappeClient with retry/cache
│   ├── import-files.ts                      ← Excel/CSV/Google Sheets loader
│   └── env.ts                               ← .env loader
│
├── docs/
│   └── DOCUMENTATION.md                     ← ไฟล์นี้
│
├── package.json                             ← npm dependencies + scripts
├── package-lock.json
├── playwright.config.ts                     ← 4 test projects
├── tsconfig.json
├── .env.example                             ← Template (ไม่มี password)
├── .gitignore                               ← เพิ่ม auth.json, .env, *.xlsx, data/
└── README.md                                ← E2E section ต่อท้ายเดิม
```

## Running Tests

```bash
npm test                  # Functional tests (login, master data, accounting, HR, custom apps)
npm run test:validate     # Google Sheets validation (master + stock sheets vs API)
npm run test:compare      # Data comparison (dataset configs)
npm run test:report       # Open HTML report
```

### Prerequisites

**Google Sheets Auth (ต้องทำครั้งเดียว):**
```bash
# ติดตั้ง gcloud CLI แล้วรัน
gcloud auth application-default login --scopes="https://www.googleapis.com/auth/cloud-platform,https://www.googleapis.com/auth/spreadsheets.readonly" --client-id-file=<path-to-desktop-oauth-client.json>
```

See `README.md` for full command list.

## Modules

| Module | Purpose |
|--------|---------|
| `lib/frappe-api.ts` | API helper using Playwright request context |
| `lib/frappe-client.ts` | Standalone API client (login, fetch docs) |
| `lib/validator.ts` | Sheet vs API field-by-field validation engine |
| `lib/column-map.ts` | Sheet-to-field mapping configs (17 sheets) |
| `lib/excel-reader.ts` | อ่าน Google Sheets API (Service Account / ADC) |
| `lib/comparator.ts` | Server vs server comparison |
| `scripts/gsheets-reader.js` | Standalone Google Sheets reader |

## Test Projects

| Project | What it runs | Needs Google Sheets? |
|---------|-------------|---------------------|
| `setup` | Login → auth.json | No |
| `chromium` | 01-05 functional tests | No |
| `validate` | Google Sheets validation (master + stock) | Yes (ADC) |
| `data-compare` | Dataset comparison | Yes |

## Test Counts สรุป

### Functional Tests (project: `chromium`)

| Spec | Tests | ตรวจสอบ |
|------|-------|---------|
| `01-login.spec.ts` | 8 | Session, module access, navigation, installed apps |
| `02-master-data.spec.ts` | 20 | Company, Customer, Supplier, Item, Employee, Item Group, Territory, Warehouses |
| `03-accounting-stock.spec.ts` | 6 | Fiscal Year, Cost Center, Currency, UOM, Stock Ledger |
| `04-hr-payroll.spec.ts` | 6 | Department, Designation, Employment Type, Leave Types |
| `05-custom-apps.spec.ts` | 12 | Thailand tax, custom apps, data integrity, GL balance |
| **รวม** | **52** | |

### Google Sheets Validation Tests (project: `validate`)

| Spec | Tests | ตรวจสอบ |
|------|-------|---------|
| `master-validation.spec.ts` | 17 | Google Sheets vs API (Companies, Items, Customers, Suppliers, Employees, Accounts, Warehouses, UOM, etc.) |
| `stock-validation.spec.ts` | 5 | Google Sheets vs API (Items stock, UOMs, Warehouses, etc.) |
| **รวม** | **22** | |

### Data Compare Tests (project: `data-compare`)

| Spec | Tests | ตรวจสอบ |
|------|-------|---------|
| `master-data-compare.spec.ts` | 3 | Import files validation, comparison, Google Sheets URL handling |
| **รวม** | **3** | |

### สรุปทั้งหมด

| ประเภท | Tests | ต้องมี Google Auth? |
|---------|-------|-------------------|
| Functional | 52 | ไม่ |
| Sheets Validation | 22 | ใช่ (ADC) |
| Data Compare | 3 | ใช่ |
| **รวม** | **77** | |

## Google Sheets Integration (Phase 2 — Done)

### สิ่งที่ทำแล้ว
- ดึง Master Data จาก **Google Sheets** ผ่าน Google Sheets API
- ใช้ **Application Default Credentials (ADC)** ผ่าน `gcloud auth application-default login`
- รองรับ **Service Account key** ผ่าน `GOOGLE_APPLICATION_CREDENTIALS` env var
- `lib/excel-reader.ts` อ่านจาก Google Sheets โดยตรง (ไม่ต้องใช้ไฟล์ Excel ในเครื่อง)

### Auth Methods

| วิธี | ใช้เมื่อไหร่ |
|------|-------------|
| ADC (`gcloud auth application-default login`) | Local dev (เครื่องส่วนตัว) |
| Service Account JSON key (`GOOGLE_APPLICATION_CREDENTIALS`) | CI/CD pipeline |

### Flow ปัจจุบัน

```
Google Sheet → lib/excel-reader.ts (loadGoogleSheets) → SheetData
  → validate.fixture.ts → test specs → validator.ts → compare with ERPNext API
```

### Tests ที่จะเปิดใน Phase 3

| กลุ่ม | Tests | เงื่อนไข |
|-------|-------|----------|
| Stock Entry | validation + page load | รอข้อมูลจาก CD |
| Transaction | SO, SI, PO, PI, Payment, Journal, Quotation, DN, PR | CD พร้อม test transaction |
| HR/Payroll | Leave Allocation, Attendance, Salary, Expense | CD พร้อม test payroll |

## Environment

```env
BASE_URL=https://dev.connectdiagnostics.nomeaparadigm.com
ERP_USERNAME=Administrator
ERP_PASSWORD=<set in .env>
GOOGLE_SHEET_ID=1P40NXIF72wm4YVLfqN0l3-W3GXLt2GVraVLY9bKZXFQ
# GOOGLE_APPLICATION_CREDENTIALS=path/to/service-account-key.json  (optional, for CI/CD)
```
