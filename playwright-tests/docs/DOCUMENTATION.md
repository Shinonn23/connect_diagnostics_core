# CD-ERPNext Playwright — Complete Project Documentation

> เอกสารระเอียดครอบคลุมทุกส่วนของโปรเจค
> อธิบายโครงสร้าง หลักการ โค้ด และ flow การทำงานของทุกไฟล์

---

## สารบัญ

1. [ภาพรวมโปรเจค](#1-ภาพรวมโปรเจค)
2. [โครงสร้างโฟลเดอร์](#2-โครงสร้างโฟลเดอร์)
3. [Configuration Files](#3-configuration-files)
4. [Helpers — Core Modules](#4-helpers--core-modules)
5. [Tests — Functional Tests](#5-tests--functional-tests)
6. [Tests — Excel Validation](#6-tests--excel-validation)
7. [Scripts — Standalone Scripts](#7-scripts--standalone-scripts)
8. [Data Compare Engine (src/)](#8-data-compare-engine-src)
9. [ปัญหาที่พบและแก้ไข](#9-ปัญหาที่พบและแก้ไข)
10. [คำสั่งรันทั้งหมด](#10-คำสั่งรันทั้งหมด)

---

## 1. ภาพรวมโปรเจค

### วัตถุประสงค์
ทดสอบระบบ ERPNext ของ **Connect Diagnostics (CD)** บริษัทจำหน่ายอุปกรณ์การแพทย์ ด้วย Playwright automation 3 รูปแบบ:

```
┌─────────────────────────────────────────────────────────┐
│                    Excel Master Data                      │
│            (CD-ERPNext Master Data v.3.xlsx)             │
│                    ↓ ใช้เป็นตัวตั้ง                         │
├─────────────┬───────────────────┬─────────────────────────┤
│ Functional  │  Excel Validation │  Export Scripts          │
│ Tests       │  (API vs Excel)   │  (ส่งออก .xlsx)         │
│ 82 tests    │  22 tests         │  console → .xlsx        │
│ npm test    │  test:validate    │  node scripts/...       │
│ ไม่ต้องมี    │  ต้องมี Excel      │  ต้องมี Excel            │
│ Excel       │  data/ or Desktop│  data/ or Desktop       │
└─────────────┴───────────────────┴─────────────────────────┘
                          ↕
              ┌──────────────────────┐
              │  Dev API Server      │
              │  https://dev...com   │
              │  (ERPNext 15.103.3)  │
              └──────────────────────┘
```

### Tech Stack
- **Playwright 1.59** — browser automation + API testing
- **TypeScript** — functional tests + helpers
- **Node.js (plain JS)** — standalone scripts (ไม่ต้อง compile)
- **xlsx (SheetJS)** — อ่าน/เขียน Excel files
- **ERPNext 15.103.3 + MariaDB** — target system

---

## 2. โครงสร้างโฟลเดอร์

```
playwirghterp/
│
├── .env                              ← URL + password (gitignored)
├── .env.example                      ← template (commit, ไม่มีพาสเวิร์ด)
├── .gitignore                        ← กำหนดไฟล์ที่ไม่ commit
├── playwright.config.ts              ← กำหนด 4 projects
├── package.json                      ← dependencies + npm scripts
├── tsconfig.json                     ← TypeScript config
│
├── data/                             ← Excel Master Data (gitignored)
│   └── CD-ERPNext Master Data v.3*.xlsx
│
├── helpers/                          ← Shared TypeScript modules
│   ├── frappe-api.ts                 ← API helper (ใช้ Playwright request context)
│   ├── frappe-client.ts              ← Standalone API client (login เองได้)
│   ├── validator.ts                  ← Excel vs API validation engine (370 บรรทัด)
│   ├── column-map.ts                 ← Sheet → field mapping configs (255 บรรทัด)
│   ├── excel-reader.ts               ← อ่าน Excel จาก data/ หรือ Desktop
│   └── comparator.ts                 ← Server vs Server comparison (186 บรรทัด)
│
├── tests/                            ← Playwright test files
│   ├── auth.setup.ts                 ← Login → สร้าง auth.json
│   │
│   │ ── Functional (project: chromium) ─────────────────────
│   ├── 01-login.spec.ts              ← 8 tests
│   ├── 02-master-data.spec.ts        ← 20 tests
│   ├── 03-accounting-stock.spec.ts   ← 16 tests
│   ├── 04-hr-payroll.spec.ts         ← 14 tests
│   ├── 05-custom-apps.spec.ts        ← 12 tests
│   │
│   │ ── Excel Validation (project: validate) ───────────────
│   ├── validate.fixture.ts           ← Custom fixture
│   ├── master-validation.spec.ts     ← 15 tests
│   ├── stock-validation.spec.ts      ← 5 tests
│   │
│   │ ── Data Compare (project: data-compare) ───────────────
│   └── master-data-compare.spec.ts   ← 3 tests
│
├── scripts/                          ← Standalone Node.js scripts
│   ├── export-api-vs-excel.js       ← Export Dev API vs Excel → .xlsx
│   ├── check-final.js                ← COA + Item Prices deep analysis
│   ├── export-results.js             ← Export (version เก่า)
│   ├── export-sql-vs-excel.js        ← Export SQL dump vs Excel → .xlsx
│   ├── compare-sql-api.js            ← เทียบ 3 sources (console)
│   ├── check-employees.js            ← Debug: employee matching
│   ├── check-missing-1.js            ← Debug: find missing records
│   ├── sql-vs-excel.js               ← SQL vs Excel (console)
│   └── run-master-test.js            ← Data comparison runner
│
├── src/                              ← Data Compare Engine
│   ├── lib/compare.ts                ← Core comparison engine
│   ├── lib/frappe.ts                 ← FrappeClient with retry/cache
│   ├── lib/import-files.ts           ← Excel/CSV/Google Sheets loader
│   ├── lib/env.ts                    ← .env loader
│   └── config/datasets.ts            ← Dataset config loader
│
├── docs/                             ← Documentation
│   ├── PROJECT-FLOW.md               ← Flow + architecture + analysis
│   └── TEST-FLOW.md                  ← Detailed test flow
│
├── master-data.datasets.*.json       ← Dataset configs
└── auth.json                         ← Browser session (gitignored)
```

---

## 3. Configuration Files

### 3.1 `playwright.config.ts` — แบ่ง tests เป็น 4 projects

```typescript
projects: [
  { name: 'setup',       testMatch: /.*\.setup\.ts/ },           // auth.setup.ts
  { name: 'chromium',     testMatch: /\d{2}-.*\.spec\.ts/ },     // 01-05*.spec.ts
  { name: 'validate',     testMatch: /(master|stock)-validation/ },// master/stock-validation
  { name: 'data-compare', testMatch: /master-data-compare/ },     // master-data-compare
]
```

**หลักการ:**
- **setup** → รันก่อน chromium (dependencies: ['setup'])
- **chromium** → functional tests ใช้ browser + auth.json
- **validate** → login เอง (FrappeClient), ไม่ใช้ browser
- **data-compare** → login เอง, ใช้ src/ engine

### 3.2 `.env` / `.env.example`

```env
BASE_URL=https://dev.connectdiagnostics.nomeaparadigm.com
ERP_USERNAME=Administrator
ERP_PASSWORD=          # ใส่ password จริงใน .env (gitignored)
EXCEL_DIR=             # optional: override Excel search path
```

### 3.3 `package.json` — npm scripts

```json
{
  "scripts": {
    "test": "npx playwright test --project=chromium",
    "test:validate": "npx playwright test --project=validate",
    "test:compare": "npx playwright test --project=data-compare",
    ...
  }
}
```

---

## 4. Helpers — Core Modules

### 4.1 `helpers/excel-reader.ts` — อ่าน Excel

**หน้าที่:** หาและอ่านไฟล์ Excel Master Data

**Search order:**
1. `process.env.EXCEL_DIR` (ถ้าตั้งไว้)
2. `./data/` folder ในโปรเจค
3. `~/Desktop/` (fallback)

**หลักการทำงาน:**
```
loadExcel()
  → findExcelFile()
    → หาไฟล์ที่ขึ้นต้นด้วย "CD-ERPNext" + มี "v.3" + ลงท้าย ".xlsx"
    → หาตามลำดับ: EXCEL_DIR → data/ → Desktop
    → ถ้าไม่เจอ → throw Error
  → xlsx.readFile(filePath, { cellDates: true })
  → แปลงทุก sheet เป็น JSON array → เก็บใน Map<sheetName, rows[]>
  → return { sheets, filePath }
```

**exported functions:**
- `loadExcel(filePath?)` → อ่านทุก sheet
- `getSheet(data, sheetName)` → ดึง rows ของ sheet นั้น

### 4.2 `helpers/frappe-api.ts` — API Helper (Functional Tests)

**หน้าที่:** เรียก ERPNext API โดยใช้ Playwright's `APIRequestContext` (แชร์ session กับ browser)

**exported functions:**

```typescript
getDocList(request, doctype, fields, filters, limit)
  // GET /api/method/frappe.client.get_list?doctype=...&fields=...
  // return: array of records

getDoc(request, doctype, name)
  // GET /api/resource/{doctype}/{name}
  // return: single document

getCount(request, doctype, filters)
  // GET /api/method/frappe.client.get_count?doctype=...&filters=...
  // return: number

getInstalledApps(request)
  // ลอง Installed Application doctype ก่อน
  // ถ้าไม่ได้ → fallback เป็น Module Def
  // return: array

checkRequiredFields(doc, fields)
  // ตรวจว่า field ใน document ไม่เป็น null/undefined/''/0
  // return: array of { field, value }
```

**ใช้กับ:** Functional tests 01-05 (project: chromium)

### 4.3 `helpers/frappe-client.ts` — Standalone API Client

**หน้าที่:** เรียก ERPNext API แบบ standalone (login เอง, ไม่ต้องใช้ browser)

```typescript
class FrappeClient {
  constructor(baseUrl)

  async login(username, password)
    // สร้าง request context ใหม่
    // POST /api/method/login → เก็บ session cookie
    // return this (chainable)

  async getDocList(doctype, fields, filters, limit)
    // เหมือน frappe-api.ts แต่ใช้ context ตัวเอง

  async getCount(doctype, filters)
  async getDoc(doctype, name)
  async dispose()    // ปิด context
}
```

**ใช้กับ:** validate project, data-compare project, export scripts

**ความต่างกับ frappe-api.ts:**
| | frappe-api.ts | frappe-client.ts |
|---|---|---|
| ใช้กับ | Functional tests | Validation/Compare |
| request context | รับจาก parameter | สร้างเอง |
| login | ใช้ auth.json (browser) | POST /api/method/login |
| dependencies | Playwright test runner | Playwright request module |

### 4.4 `helpers/column-map.ts` — Sheet Config Definitions

**หน้าที่:** กำหนด mapping ระหว่าง Excel headers ↔ API fields สำหรับ 18 sheets

#### 4.4.1 `FieldMapping` interface

```typescript
interface FieldMapping {
  excel: string | string[];        // Excel column header(s)
  api: string;                      // API field name
  ignoreCase?: boolean;             // เทียบแบบไม่สน case
  fuzzyMatch?: 'strip-cd' | ...;   // ลบ suffix ก่อนเทียบ
  booleanField?: boolean;           // แปลงเป็น boolean ก่อนเทียบ
  countryAlias?: boolean;           // ใช้ country alias lookup
  firstNameOnly?: boolean;          // เทียบแค่ชื่อแรก
  skipWhen?: (apiRec) => boolean;   // ข้าม field นี้ถ้าเงื่อนไขเป็นจริง
}
```

**skipWhen ตัวอย่าง:**
```typescript
{ excel: 'Has Batch No', api: 'has_batch_no', booleanField: true,
  skipWhen: (rec) => !rec.is_stock_item }
// → ข้าม check นี้สำหรับ Product Bundle (is_stock_item=0)
```

#### 4.4.2 `SheetConfig` interface

```typescript
interface SheetConfig {
  sheetName: string;               // Excel sheet name
  doctype: string;                  // ERPNext DocType
  label: string;                    // Display name
  keyExcel: string | string[];     // Excel key column(s)
  keyApi: string;                   // API key field
  keyIgnoreCase?: boolean;          // key matching case-insensitive
  keyFuzzyMatch?: ...;              // key matching with strip
  fields: FieldMapping[];           // field mappings
  compositeKey?: (row) => string;   // composite key builder
  filters?: Record<string, any>;    // API filters (เช่น company filter)
  keyExtractor?: (val) => string;   // transform key ก่อน matching
}
```

#### 4.4.3 18 Sheet Configs

| Sheet Name | DocType | Excel Key | API Key | Notes |
|------------|---------|-----------|---------|-------|
| Companies | Company | Company | company_name | case-insensitive |
| Customers | Customer | ID, Customer Name | name | multi-key fallback |
| Suppliers | Supplier | CD ID, Supplier Name | name | country alias |
| Items | Item | ID, CD Item Code | name | skipWhen for Product Bundle |
| Employees | Employee | EmployeeID | name | firstNameOnly match |
| Warehouses | Warehouse | Warehouse Name | warehouse_name | |
| Item_Groups | Item Group | Item Group Name | name | |
| Customer_Groups | Customer Group | Customer Group Name | name | |
| Supplier_Groups | Supplier Group | Supplier Group | name | |
| Territories | Territory | Territory | name | |
| Departments | Department | Department Name | name | strip-cd suffix |
| UOMs | UOM | new name, old name | name | case-insensitive |
| Currencies | Currency | currency_code | name | |
| Brands | Brand | Brand | name | no fields (key only) |
| Accounts New | Account | Account Number, Account Name | name | keyExtractor: split ' - ' |
| Item_Prices | Item Price | Item Code | item_code | compositeKey: code\|price_list |
| Tax_Withholding_Categories | Tax Withholding Category | Category Name | name | |
| Item_Tax_Templates | Item Tax Template | Title | title | strip-tax-suffix |

#### 4.4.4 การเทียบค่า (Comparison Logic)

```
fuzzyMatch modes:
  'strip-cd'           → "D02 - CD" → "D02" (ลบ " - CD" suffix)
  'strip-tax-suffix'   → "VAT 7% - CD" → "VAT 7%" (ลบ suffix + trailing numbers)
  'strip-company-suffix' → "All Departments - CD" → "All Departments"

booleanField:
  Excel: "1", "yes", "true", "✓", "checked" → true
  Excel: "0", "no", "false", "✗", "unchecked" → false
  → เทียบ boolean ทั้งสองฝั่ง

countryAlias:
  'South Korea' == 'Korea, Republic of' → true (lookup table)

firstNameOnly:
  Excel: "Sirasit" vs API: "Sirasit Sangsri-in" → true

skipWhen:
  เมื่อ callback return true → ข้าม field นั้น (ไม่ check)
```

### 4.5 `helpers/validator.ts` — Validation Engine

**หน้าที่:** เปรียบเทียบ Excel rows vs API records field-by-field

#### Flow หลัก (`validateSheet` function)

```
Input: excelRows[], apiRecords[], SheetConfig
                ↓
┌──────────────────────────────────────┐
│  1. สร้าง apiMap (key → record)       │
│     → getApiKey() แปลง key           │
│     → keyExtractor, fuzzyMatch       │
└──────────────┬───────────────────────┘
               ↓
┌──────────────────────────────────────┐
│  2. วนลูปทุก Excel row                │
│     ├── filter แถวว่าง (allNonKeyEmpty)│
│     ├── หา apiRec จาก apiMap          │
│     │   └── fallback case-insensitive │
│     ├── ถ้าไม่เจอ → missingInApi      │
│     └── ถ้าเจอ → เทียบทุก field:       │
│         ├── skipWhen → ข้าม           │
│         ├── normalize values          │
│         ├── compareValues():          │
│         │   ├── boolean comparison    │
│         │   ├── countryAlias lookup   │
│         │   ├── fuzzyMatch strip      │
│         │   ├── firstNameOnly         │
│         │   └── exact comparison      │
│         └── ต่าง → fieldMismatches     │
└──────────────┬───────────────────────┘
               ↓
┌──────────────────────────────────────┐
│  3. หา extraInApi                    │
│     → API records ที่ไม่มีใน Excel      │
└──────────────┬───────────────────────┘
               ↓
Output: ValidationResult
  { sheetName, doctype, label,
    excelCount, apiCount, matched,
    missingInApi[], extraInApi[],
    fieldMismatches[], passed }
```

#### Helper functions

```typescript
normalize(val)
  // null/undefined/'' → ''
  // number → String(number)
  // string → trim() + replace multi-spaces

toBool(val)
  // '1','yes','true','✓','checked' → true
  // '0','no','false','✗','unchecked' → false
  // else → null (can't determine)

stripCdSuffix(val)     // "xxx - CD" → "xxx"
stripCompanySuffix(val) // "xxx - yyy - CD" → "xxx - yyy"
stripTaxSuffix(val)    // "xxx - CD 123" → "xxx"
floatToString(val)     // "1.0" → "1"

getExcelValue(row, excelCol)
  // ถ้าเป็น array → ลองทีละ column, เอาค่าแรกที่ไม่ว่าง
  // ถ้าเป็น string → row[excelCol]

getExcelKey(row, config) → string
getApiKey(rec, config) → string
  // แปลง key ตาม config: keyExtractor, fuzzyMatch, ignoreCase
```

#### Print functions

```typescript
printResult(r: ValidationResult)
  // พิมพ์ผล validation ของ 1 sheet
  // ✅/❌ icon + matched count + missing/extra/mismatches detail

printSummary(results: ValidationResult[])
  // พิมพ์สรุปทุก sheets
  // passed/failed counts + total records + failed sheet list
```

### 4.6 `helpers/comparator.ts` — Server vs Server Comparison

**หน้าที่:** เปรียบเทียบ records จาก 2 servers (master vs dev)

**หลักการ:** เหมือน validator แต่ง่ายกว่า — เทียบแบบ exact match ไม่มี fuzzy logic

```
compareRecords(masterRecords, devRecords, config)
  → สร้าง masterMap, devMap by key
  → masterOnly = มีใน master ไม่มีใน dev
  → devOnly = มีใน dev ไม่มีใน master
  → fieldMismatches = normalize(val1) !== normalize(val2)
  → return CompareResult { passed, masterOnly, devOnly, fieldMismatches }
```

---

## 5. Tests — Functional Tests

### 5.1 `auth.setup.ts` — Authentication Setup

**Flow:**
```
1. เปิด browser → ไปที่ /app
2. กรอก email + password (จาก .env)
3. กดปุ่ม Login
4. รอ URL เปลี่ยนเป็น /app
5. บันทึก storageState → auth.json
   { cookies: [...], origins: [...] }
```

**สำคัญ:** auth.json ถูกใช้โดย project chromium เท่านั้น (validate/data-compare login เอง)

### 5.2 `01-login.spec.ts` — Login & Navigation (8 tests)

```
├── should be logged in and see desktop          // UI: เห็น workspace
├── should access Setup module (/app/setup)       // UI: navigate สำเร็จ
├── should access Selling module                  // UI: navigate สำเร็จ
├── should access Buying module                   // UI: navigate สำเร็จ
├── should access Stock module                    // UI: navigate สำเร็จ
├── should access Accounting module               // UI: navigate สำเร็จ
├── should access HR module                       // UI: navigate สำเร็จ
└── should verify installed apps via API           // API: ดึง modules + ตรวจ 41 modules
```

### 5.3 `02-master-data.spec.ts` — Master Data (20 tests)

**Pattern สำหรับแต่ละ DocType:**
```
API Tests (3 tests per DocType):
  1. should have at least 1 record
     → getCount() > 0

  2. each record should have required fields
     → getDocList() → checkRequiredFields(doc, ['name', ...])
     → ถ้ามี missing fields → log warning (soft fail)

  3. [DocType] list page loads in UI
     → page.goto('/app/[doctype-path]')
     → expect no "Not Permitted" error
```

**DocTypes ที่ตรวจ:** Company (3), Customer (1239), Supplier (624), Item (778), Employee (44), Warehouse (297), Chart of Accounts (660), Groups (4 types)

### 5.4 `03-accounting-stock.spec.ts` — Accounting & Stock (16 tests)

```
Settings:
  Fiscal Year exists + active (2026)
  Cost Center exists (6)
  Enabled Currencies exists (32)

Transaction pages (SO, SI, PO, PI):
  API: validate required fields (ถ้ามี records)
  UI: list page loads

Stock:
  UOM count (254)
  Stock Entry validation + UI + Stock Ledger Report

Payment/Journal:
  Payment Entry validation (ถ้ามี)
  Journal Entry: debit = credit (ถ้ามี)

Other pages:
  Quotation, Delivery Note, Purchase Receipt → UI loads
```

### 5.5 `04-hr-payroll.spec.ts` — HR & Payroll (14 tests)

```
HR Setup:     Department (21), Designation (31), Employment Type (1)
Leave:        Leave Type (5), Leave Allocation, Leave Application page
Attendance:   records + validation + UI page
Payroll:      Salary Component (4), Salary Structure, Payroll Entry, Salary Slip page
Expense:      Expense Claim page, Employee Advance page
```

### 5.6 `05-custom-apps.spec.ts` — Custom Apps + Data Integrity (12 tests)

```
ERPNext Thailand:
  Sales Tax Templates (3), Purchase Tax Templates (3)
  Addresses (50 total, 40 Thai)
  Tax Withholding Categories (10)
  Currency THB enabled

Connect Diagnostics Core:
  App installed (Module Def check)
  Custom DocTypes listed (Rename Tool V2, Sub Department Assignment)
  Data in each custom doctype
  Module page loads in UI

Data Integrity:
  Customer → Territory cross-reference (ทุก customer มี valid territory)
  Item → Item Group cross-reference
  Employee → Company cross-reference
  GL Entry balance (debit = credit)
```

---

## 6. Tests — Excel Validation

### 6.1 `validate.fixture.ts` — Custom Playwright Fixture

**หน้าที่:** สร้าง FrappeClient + Excel data ให้ test ใช้

```typescript
export const test = base.extend<ValidateFixtures>({
  client: async ({}, use) => {
    const client = new FrappeClient(BASE_URL);
    await client.login(ADMIN_USER, ADMIN_PASS);  // login เอง
    await use(client);                            // ให้ test ใช้
    await client.dispose();                       // ปิด context
  },
  excelData: async ({}, use) => {
    const data = loadExcel();                     // อ่าน Excel
    await use(data);                              // ให้ test ใช้
  },
});
```

### 6.2 `master-validation.spec.ts` — 15 Master Sheets

**Pattern:**
```typescript
test('04 - Items (778 records)', async ({ client, excelData }, testInfo) => {
  const r = await runValidation(client, excelData, testInfo, 'Items');
  expect(r.missingInApi).toHaveLength(0);      // ทุก Excel row มีใน API
  expect(r.fieldMismatches).toHaveLength(0);    // ทุก field ตรง
});
```

**`runValidation()` function flow:**
```
1. getConfig('Items') → SheetConfig
2. getSheet(excelData, 'Items') → Excel rows
3. client.getDocList('Item', fields, filters, 0) → API records
4. validateSheet(excelRows, apiRecords, config) → ValidationResult
5. attach JSON result to test
6. return result → expect assertions
```

**15 sheets:** Companies, Customers, Suppliers, Items, Employees, Warehouses, Item Groups, Customer Groups, Supplier Groups, Territories, Departments, UOMs, Currencies, Brands, Accounts, Tax Withholding Categories, Item Tax Templates

### 6.3 `stock-validation.spec.ts` — 5 Stock Sheets

เหมือน master-validation แต่เทียบ 5 sheets: Items, Warehouses, UOMs, Brands, Item Groups

---

## 7. Scripts — Standalone Scripts

### หลักการร่วม
- เขียนด้วย **plain JavaScript** (ไม่ต้อง compile)
- ใช้ `https` module ติดต่อ API โดยตรง (ไม่ใช้ Playwright)
- ใช้ `xlsx` อ่าน/เขียน Excel
- Login ด้วย Administrator → เก็บ sid cookie → ใช้ต่อทุก API call

### 7.1 `scripts/export-api-vs-excel.js` — **ใช้หลัก (ส่งทีม)**

**หน้าที่:** เปรียบเทียบ Dev API vs Excel → export เป็น `.xlsx` ส่งทีม

**Flow:**
```
1. Login API → ได้ sid cookie
2. findExcelDir() → หา Excel จาก data/ หรือ Desktop
3. อ่าน Excel (xlsx.readFile)
4. วนลูป 5 DocTypes:

   Items (778):
     API: getDocList('Item', [name, item_name, brand, is_stock_item])
     Excel: sheet 'Items' column 'ID', 'Brand'
     เทียบ: Excel Brand ไม่ว่าง + API brand ว่าง → issue

   Accounts (219):
     API: getDocList('Account', [...], {company: 'Connect Diagnostics'})
     Excel: sheet 'Accounts New'
     เทียบ: account_type แบ่งเป็น EMPTY / MISMATCH / NAMING

   Customers (1239):
     API: getDocList('Customer', [...])
     Excel: sheet 'Customers'
     เทียบ: customer_group ว่าง → issue

   Employees (45):
     API: getDocList('Employee', [...])
     Excel: sheet 'Employees'
     เทียบ: filter empty rows, check missing

   Suppliers (624):
     API: getDocList('Supplier', [...])
     Excel: sheet 'Suppliers'
     เทียบ: check missing

5. เขียนผลเป็น Excel:
   - Sheet "Items - Brand Missing" (39 rows)
   - Sheet "Accounts - Issues" (90 rows with Category column)
   - Sheet "Customers - No Group" (7 rows)
   - Sheet "Summary" (5 rows)
6. บันทึกเป็น "CD-ERPNext Validation Results.xlsx"
```

**Accounts category logic:**
```javascript
if (apiType === '')
  → EMPTY        // API ไม่มีค่า แต่ Excel มี
else if (apiType.includes(excelType) || excelType.includes(apiType))
  → NAMING       // ต่างกันแต่เป็น naming convention (เช่น "Expense" vs "Expense Account")
else
  → MISMATCH     // ต่างกันจริงๆ (เช่น "Accrued Expenses" vs "Payable")
```

**Run:** `node scripts/export-api-vs-excel.js`
**Output:** `CD-ERPNext Validation Results.xlsx` ใน data/ folder

### 7.2 `scripts/check-final.js` — COA + Item Prices Deep Analysis

**หน้าที่:** วิเคราะห์เชิงลึก 2 ส่วนที่ซับซ้อนกว่า sheet อื่น

**Part 1 — Item Prices:**
```
1. API: getDocList('Item Price', [all fields]) → 965 records
2. Excel: sheet 'Item_Prices' → 614 records
3. สร้าง composite key: item_code|price_list
4. แบ่งเป็น:
   - matched (450) — มีทั้ง Excel + API
   - new (515) — มีแค่ API
5. new แบ่งตาม Price List:
   - Standard Buying: 513 items (rate=0, auto-created)
   - Standard Selling: 2 items
6. Rate comparison (matched items):
   - rateMatch (73) — rate ตรง
   - rateDiff (377) — rate ต่าง (Excel=0, API has value)
```

**Part 2 — COA Full Check:**
```
1. API: getDocList('Account', [...], {company: 'CD'}) → 220 accounts
2. Excel: sheet 'Accounts New' → 219 accounts
3. ตรวจ 7 ด้าน:
   1) Missing in API (0)
   2) Extra in API (1 — "VAT - CD")
   3) account_type: empty=4, naming=79, mismatch=7
   4) Root type validation
   5) is_group validation
   6) Disabled accounts
   7) Account Tree Summary (5 root accounts)
```

**Run:** `node scripts/check-final.js`
**Output:** Console only (ไม่ export Excel)

### 7.3 `scripts/export-sql-vs-excel.js` — SQL Dump vs Excel

**หน้าที่:** อ่าน SQL dump file → parse INSERT statements → เทียบกับ Excel

**SQL Parser:**
```
parseSqlTable(sqlPath, tableName)
  → readline ทีละบรรทัด
  → หา CREATE TABLE → extract column names
  → หา INSERT INTO → parse VALUES
  → splitRecords(")...(") → แยกแต่ละ record
  → parseFields("val1","val2",...) → parse field values
  → return { columns, rows }
```

**Escape handling:**
```
\\' → escaped quote (skip next char)
''  → literal quote
\\n → escaped newline
```

**Run:** `node scripts/export-sql-vs-excel.js`
**Output:** `CD-ERPNext SQL vs Excel Comparison.xlsx`

### 7.4 `scripts/compare-sql-api.js` — 3-way Comparison

**หน้าที่:** เปรียบเทียบ SQL dump vs Dev API vs Excel แบบ side-by-side

**Flow:**
```
1. Login API
2. Parse SQL tables (Items, Accounts, Customers, Employees, Suppliers)
3. Query Dev API (5 DocTypes)
4. เปรียบเทียบ SQL vs API:
   - Items: brand null ทั้งสองฝั่ง → same
   - Accounts: SQL ว่าง 88, API มีค่า → API added after import
   - Customers: extra 1 in API (SHOP-01)
   - Employees: extra 1 in API (6902002 Thanawit)
   - Suppliers: extra 1 in API
```

**Run:** `node scripts/compare-sql-api.js`

### 7.5 `scripts/check-employees.js` — Employee Debug

**หน้าที่:** debug หา employee ที่ขาดใน SQL dump vs API vs Excel

**Run:** `node scripts/check-employees.js`

### 7.6 `scripts/check-missing-1.js` — Find Missing Records

**หน้าที่:** หาทุก "1" record ที่ขาดใน SQL dump แต่มีใน API

**ผลลัพธ์ที่เคยพบ:**
- Items: 700000143 (DUMMY EDI)
- Customers: SHOP-01
- Employees: 6902002 (Thanawit Sae-khoo)
- Suppliers: SUPP-112002196

**Run:** `node scripts/check-missing-1.js`

### 7.7 `scripts/export-results.js` — Export (Version เก่า)

เหมือน export-api-vs-excel.js แต่เทียบหลาย field มากกว่า (customer_name, territory, supplier group ฯลฯ) — ใช้เมื่อต้องการ detailed comparison

### 7.8 `scripts/sql-vs-excel.js` — SQL vs Excel (Console)

เหมือน export-sql-vs-excel.js แต่พิมพ์ console อย่างเดียว (ไม่ export Excel)

### 7.9 `scripts/run-master-test.js` — Data Comparison Runner

**หน้าที่:** รัน Data Compare Engine (`src/`)

**Run:**
```bash
npm run test:master:v3    # Master workbook comparison
npm run test:stock        # Stock data comparison
```

---

## 8. Data Compare Engine (src/)

### โครงสร้าง

```
src/
├── lib/
│   ├── compare.ts       ← Core comparison (1,241 บรทัด)
│   ├── frappe.ts        ← FrappeClient with retry/cache
│   ├── import-files.ts  ← Load data from Excel/CSV/Google Sheets
│   └── env.ts           ← .env loader (fallback to .env.example)
└── config/
    └── datasets.ts      ← Dataset config loader
```

### หลักการ
- เปรียบเทียบข้อมูลจากหลายแหล่ง (Excel, CSV, Google Sheets, API)
- ใช้ dataset config JSON (`master-data.datasets.*.json`)
- รันผ่าน Playwright test (`data-compare` project)

---

## 9. ปัญหาที่พบและแก้ไข

| ปัญหา | วิธงแก้ |
|-------|--------|
| `waitForLoadState('networkidle')` timeout | เปลี่ยนเป็น `'load'` |
| `Installed Application` API คืนค่าว่าง | ใช้ `Module Def` แทน |
| Excel path hardcoded `C:\Users\MARU\Desktop` | เปลี่ยนเป็น search order: data/ → Desktop |
| Employee C690301 "หาย" | แก้ validator filter empty rows |
| Product Bundle has_batch_no mismatch | เพิ่ม `skipWhen` ใน column-map |
| Account type "Expense" vs "Expense Account" | แยก NAMING category (ไม่ใช่บัค) |
| SQL parser fail on apostrophe | แก้ escape handling (`\'` → skip next char) |

---

## 10. คำสั่งรันทั้งหมด

### ทุกวัน (ไม่ต้องมี Excel)
```bash
npm test                        # 82 functional tests (~1 min)
npm run test:report             # เปิด HTML report
```

### เมื่อต้องเทียบ Excel vs API
```bash
npm run test:validate           # 22 validation tests
node scripts/export-api-vs-excel.js   # Export issues → .xlsx
```

### เมื่อมี SQL backup ใหม่
```bash
node scripts/export-sql-vs-excel.js   # SQL dump vs Excel → .xlsx
node scripts/compare-sql-api.js       # 3-way comparison
```

### Debug / Verify
```bash
node scripts/check-final.js           # COA + Item Prices deep check
node scripts/check-employees.js       # Employee matching debug
node scripts/check-missing-1.js       # Find missing records
node scripts/sql-vs-excel.js          # SQL vs Excel console
```

### Data Compare Engine
```bash
npm run test:compare                  # Import archive vs API
npm run test:master:v3               # Master workbook comparison
npm run test:stock                   # Stock data comparison
```
