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
│   ├── 03-accounting-stock.spec.ts          ← Accounting Settings + Stock (transaction tests ลบแล้ว, TODO Phase 2)
│   ├── 04-hr-payroll.spec.ts                ← HR Setup + Leave Types (Payroll/Attendance ลบแล้ว, TODO Phase 2)
│   ├── 05-custom-apps.spec.ts               ← 12 tests: Thailand tax, custom apps, data integrity
│   ├── master-validation.spec.ts            ← 15 tests: Excel master sheets vs API
│   ├── stock-validation.spec.ts             ← 5 tests: Excel stock sheets vs API
│   ├── master-data-compare.spec.ts          ← 3 tests: Dataset comparison
│   └── validate.fixture.ts                  ← Custom Playwright fixture
│
├── lib/                                     ← Data processing modules
│   ├── frappe-api.ts                        ← API helper (Playwright request context)
│   ├── frappe-client.ts                     ← Standalone API client
│   ├── validator.ts                         ← Excel vs API validation engine
│   ├── column-map.ts                        ← Sheet → field mapping (18 sheets)
│   ├── excel-reader.ts                      ← อ่าน Excel (TODO Phase 2 → Google Sheets)
│   └── comparator.ts                        ← Server vs Server comparison
│
├── scripts/                                 ← Standalone scripts
│   ├── export-api-vs-excel.js               ← Export API vs Excel → .xlsx
│   ├── export-results.js                    ← Export validation results
│   ├── check-final.js                       ← COA + Item Prices deep check
│   ├── run-master-test.js                   ← Data comparison runner
│   ├── compare.ts                           ← Core comparison engine (1,241 lines)
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
├── master-data.datasets.json                ← Dataset config
├── master-data.datasets.stock.json
├── master-data.datasets.v3.json
├── .gitignore                               ← เพิ่ม auth.json, .env, *.xlsx, data/
└── README.md                                ← เพิ่ม E2E section ต่อท้ายเดิม
```

## Running Tests

```bash
npm test                  # Functional tests (login, master data, accounting, HR, custom apps)
npm run test:validate     # Excel validation (master + stock sheets vs API)
npm run test:compare      # Data comparison (dataset configs)
npm run test:report       # Open HTML report
```

See `README.md` for full command list.

## Modules

| Module | Purpose |
|--------|---------|
| `lib/frappe-api.ts` | API helper using Playwright request context |
| `lib/frappe-client.ts` | Standalone API client (login, fetch docs) |
| `lib/validator.ts` | Excel vs API field-by-field validation engine |
| `lib/column-map.ts` | Sheet-to-field mapping configs (18 sheets) |
| `lib/excel-reader.ts` | Read Excel from `data/` or Desktop |
| `lib/comparator.ts` | Server vs server comparison |

## Test Projects

| Project | What it runs | Needs Excel? |
|---------|-------------|-------------|
| `setup` | Login → auth.json | No |
| `chromium` | 01-05 functional tests | No |
| `validate` | Excel validation (master + stock) | Yes |
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

### Excel Validation Tests (project: `validate`)

| Spec | Tests | ตรวจสอบ |
|------|-------|---------|
| `master-validation.spec.ts` | 15 | Master data sheets vs API (Companies, Items, Customers, Suppliers, Employees, Accounts, Warehouses, UOM, etc.) |
| `stock-validation.spec.ts` | 5 | Stock sheets vs API (Items stock, UOMs, Warehouses, etc.) |
| **รวม** | **20** | |

### Data Compare Tests (project: `data-compare`)

| Spec | Tests | ตรวจสอบ |
|------|-------|---------|
| `master-data-compare.spec.ts` | 3 | Import files validation, comparison, Google Sheets URL handling |
| **รวม** | **3** | |

### สรุปทั้งหมด

| ประเภท | Tests | ต้องมี Excel? |
|---------|-------|-------------|
| Functional | 52 | ไม่ |
| Excel Validation | 20 | ใช่ |
| Data Compare | 3 | ใช่ |
| **รวม** | **75** | |

## Phase 2 Plan

### เป้าหมาย
- ดึง Master Data จาก **Google Sheets** แทน Excel file
- ดึง **Field Mapping config** จาก Google Sheet แทน hardcode ใน `column-map.ts`
- ใช้ GCP Service Account auth (รอทีมส่ง credentials)

### โครงสร้างใหม่

```
lib/
├── data-source.ts      ← NEW: interface DataSource { loadSheet(name): Row[] }
├── google-sheets.ts    ← NEW: Google Sheets API client (service account)
├── config-loader.ts    ← NEW: อ่าน field mapping จาก Google Sheet
├── frappe-api.ts       ← คงเดิม
├── frappe-client.ts    ← คงเดิม
├── validator.ts        ← แก้: รับ data จาก DataSource interface
├── column-map.ts       ← แก้: load จาก config แทน hardcode
├── excel-reader.ts     ← เก็บเป็น fallback
└── comparator.ts       ← คงเดิม
```

### Google Sheets ที่ต้องมี

| Sheet | ข้อมูล | ตอนนี้อยู่ที่ไหน |
|-------|--------|-----------------|
| Master Data sheets | Items, Customers, Suppliers, Employees, Accounts, Warehouses | Excel `CD-ERPNext Master Data v.3*.xlsx` |
| Field Mapping config | sheet → API field mapping (18 sheets) | `lib/column-map.ts` hardcode |

### Flow เปรียบเทียบ

```
Phase 1 (ตอนนี้):
  Excel file → excel-reader.ts → validator.ts → compare with API

Phase 2:
  Google Sheet → google-sheets.ts → download to temp → validator.ts → compare with API
  Google Sheet (config) → config-loader.ts → column-map (dynamic)
```

### GCP ที่ต้องเตรียม

1. สร้าง GCP Project → enable Google Sheets API + Google Drive API
2. สร้าง Service Account → download JSON key file
3. Share Google Sheet ให้ service account email
4. env: `GOOGLE_SHEET_ID=`, `GOOGLE_APPLICATION_CREDENTIALS=`

### ลำดับการทำงาน

1. รับ GCP service account จากทีม
2. สร้าง `lib/google-sheets.ts` (auth + read sheet)
3. สร้าง `lib/data-source.ts` (interface)
4. สร้าง `lib/config-loader.ts` (load mapping from sheet)
5. แก้ `lib/validator.ts` ให้รับ DataSource
6. แก้ `e2e/validate.fixture.ts` inject Google Sheets data source
7. เพิ่ม `googleapis` dependency
8. ทดสอบ: `npm run test:validate`
9. เก็บ `excel-reader.ts` เป็น fallback

### Tests ที่จะเปิดใน Phase 2

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
```
