import { test, expect } from './validate.fixture';
import { getSheet } from '../lib/excel-reader';
import { SHEET_CONFIGS, SheetConfig } from '../lib/column-map';
import { validateSheet, printResult, printSummary, ValidationResult } from '../lib/validator';

const allResults: ValidationResult[] = [];

/** พิมพ์สรุปผล validation ทั้งหมดหลังรัน test ครบทุก sheet */
test.afterAll(() => {
  printSummary(allResults);
});

/** ค้นหา SheetConfig จาก sheet name ที่กำหนด คืน error ถ้าไม่พบ */
function getConfig(sheetName: string): SheetConfig {
  const cfg = SHEET_CONFIGS.find((c) => c.sheetName === sheetName);
  if (!cfg) throw new Error(`No config for sheet: ${sheetName}`);
  return cfg;
}

/** รัน validation เปรียบเทียบ Google Sheet rows กับ API records สำหรับ sheet ที่กำหนด และ attach ผลลัพธ์เป็น JSON */
async function runValidation(
  client: any,
  sheetData: any,
  testInfo: any,
  sheetName: string,
) {
  const config = getConfig(sheetName);
  const sheetRows = getSheet(sheetData, config.sheetName);

  const apiFields = ['name', ...new Set(config.fields.map((f) => f.api))];
  if (config.keyApi !== 'name' && !apiFields.includes(config.keyApi)) {
    apiFields.push(config.keyApi);
  }

  const apiRecords = await client.getDocList(config.doctype, apiFields, config.filters || {}, 0);

  const result = validateSheet(sheetRows, apiRecords, config);
  allResults.push(result);
  printResult(result);

  await testInfo.attach(`${config.doctype}-validation.json`, {
    body: JSON.stringify(result, null, 2),
    contentType: 'application/json',
  });

  return result;
}

/** ตรวจสอบ master data ทั้ง 17 sheets จาก Google Sheets เทียบกับข้อมูล ERPNext API แบบ real-time */
test.describe('CD-ERPNext Master Data Validation (18 Sheets)', () => {

  /** ตรวจสอบว่าข้อมูล sheet Companies ตรงกับ Company records ใน ERPNext */
  test('01 - Companies (3 records)', async ({ client, sheetData }, testInfo) => {
    const r = await runValidation(client, sheetData, testInfo, 'Companies');
    expect(r.missingInApi, 'Missing records in API').toHaveLength(0);
    expect(r.fieldMismatches, 'Field mismatches').toHaveLength(0);
  });

  /** ตรวจสอบว่าข้อมูล sheet Customers ตรงกับ Customer records ใน ERPNext */
  test('02 - Customers (1,239 records)', async ({ client, sheetData }, testInfo) => {
    const r = await runValidation(client, sheetData, testInfo, 'Customers');
    expect(r.missingInApi, 'Missing records in API').toHaveLength(0);
    expect(r.fieldMismatches, 'Field mismatches').toHaveLength(0);
  });

  /** ตรวจสอบว่าข้อมูล sheet Suppliers ตรงกับ Supplier records ใน ERPNext */
  test('03 - Suppliers (624 records)', async ({ client, sheetData }, testInfo) => {
    const r = await runValidation(client, sheetData, testInfo, 'Suppliers');
    expect(r.missingInApi, 'Missing records in API').toHaveLength(0);
    expect(r.fieldMismatches, 'Field mismatches').toHaveLength(0);
  });

  /** ตรวจสอบว่าข้อมูล sheet Items ตรงกับ Item records ใน ERPNext */
  test('04 - Items (778 records)', async ({ client, sheetData }, testInfo) => {
    const r = await runValidation(client, sheetData, testInfo, 'Items');
    expect(r.missingInApi, 'Missing records in API').toHaveLength(0);
    expect(r.fieldMismatches, 'Field mismatches').toHaveLength(0);
  });

  /** ตรวจสอบว่าข้อมูล sheet Employees ตรงกับ Employee records ใน ERPNext */
  test('05 - Employees (45 records)', async ({ client, sheetData }, testInfo) => {
    const r = await runValidation(client, sheetData, testInfo, 'Employees');
    expect(r.missingInApi, 'Missing records in API').toHaveLength(0);
    expect(r.fieldMismatches, 'Field mismatches').toHaveLength(0);
  });

  /** ตรวจสอบว่าข้อมูล sheet Warehouses ตรงกับ Warehouse records ใน ERPNext */
  test('06 - Warehouses (52 records)', async ({ client, sheetData }, testInfo) => {
    const r = await runValidation(client, sheetData, testInfo, 'Warehouses');
    expect(r.missingInApi, 'Missing records in API').toHaveLength(0);
    expect(r.fieldMismatches, 'Field mismatches').toHaveLength(0);
  });

  /** ตรวจสอบว่าข้อมูล sheet Item Groups ตรงกับ Item Group records ใน ERPNext */
  test('07 - Item Groups (15 records)', async ({ client, sheetData }, testInfo) => {
    const r = await runValidation(client, sheetData, testInfo, 'Item_Groups');
    expect(r.missingInApi, 'Missing records in API').toHaveLength(0);
    expect(r.fieldMismatches, 'Field mismatches').toHaveLength(0);
  });

  /** ตรวจสอบว่าข้อมูล sheet Customer Groups ตรงกับ Customer Group records ใน ERPNext */
  test('08 - Customer Groups (11 records)', async ({ client, sheetData }, testInfo) => {
    const r = await runValidation(client, sheetData, testInfo, 'Customer_Groups');
    expect(r.missingInApi, 'Missing records in API').toHaveLength(0);
    expect(r.fieldMismatches, 'Field mismatches').toHaveLength(0);
  });

  /** ตรวจสอบว่าข้อมูล sheet Supplier Groups ตรงกับ Supplier Group records ใน ERPNext */
  test('09 - Supplier Groups (3 records)', async ({ client, sheetData }, testInfo) => {
    const r = await runValidation(client, sheetData, testInfo, 'Supplier_Groups');
    expect(r.missingInApi, 'Missing records in API').toHaveLength(0);
    expect(r.fieldMismatches, 'Field mismatches').toHaveLength(0);
  });

  /** ตรวจสอบว่าข้อมูล sheet Territories ตรงกับ Territory records ใน ERPNext */
  test('10 - Territories (12 records)', async ({ client, sheetData }, testInfo) => {
    const r = await runValidation(client, sheetData, testInfo, 'Territories');
    expect(r.missingInApi, 'Missing records in API').toHaveLength(0);
    expect(r.fieldMismatches, 'Field mismatches').toHaveLength(0);
  });

  /** ตรวจสอบว่าข้อมูล sheet Departments ตรงกับ Department records ใน ERPNext */
  test('11 - Departments (20 records)', async ({ client, sheetData }, testInfo) => {
    const r = await runValidation(client, sheetData, testInfo, 'Departments');
    expect(r.missingInApi, 'Missing records in API').toHaveLength(0);
    expect(r.fieldMismatches, 'Field mismatches').toHaveLength(0);
  });

  /** ตรวจสอบว่าข้อมูล sheet UOMs ตรงกับ UOM records ใน ERPNext */
  test('12 - UOMs (250 records)', async ({ client, sheetData }, testInfo) => {
    const r = await runValidation(client, sheetData, testInfo, 'UOMs');
    expect(r.missingInApi, 'Missing records in API').toHaveLength(0);
    expect(r.fieldMismatches, 'Field mismatches').toHaveLength(0);
  });

  /** ตรวจสอบว่าข้อมูล sheet Currencies ตรงกับ Currency records ใน ERPNext */
  test('13 - Currencies (31 records)', async ({ client, sheetData }, testInfo) => {
    const r = await runValidation(client, sheetData, testInfo, 'Currencies');
    expect(r.missingInApi, 'Missing records in API').toHaveLength(0);
    expect(r.fieldMismatches, 'Field mismatches').toHaveLength(0);
  });

  /** ตรวจสอบว่าข้อมูล sheet Brands ตรงกับ Brand records ใน ERPNext */
  test('14 - Brands (51 records)', async ({ client, sheetData }, testInfo) => {
    const r = await runValidation(client, sheetData, testInfo, 'Brands');
    expect(r.missingInApi, 'Missing records in API').toHaveLength(0);
    expect(r.fieldMismatches, 'Field mismatches').toHaveLength(0);
  });

  /** ตรวจสอบว่าข้อมูล sheet Accounts ตรงกับ Account records ใน ERPNext */
  test('15 - Accounts (219 records)', async ({ client, sheetData }, testInfo) => {
    const r = await runValidation(client, sheetData, testInfo, 'Accounts New');
    expect(r.missingInApi, 'Missing records in API').toHaveLength(0);
    expect(r.fieldMismatches, 'Field mismatches').toHaveLength(0);
  });

  /** ตรวจสอบว่าข้อมูล sheet Tax Withholding Categories ตรงกับ records ใน ERPNext */
  test('16 - Tax Withholding Categories (10 records)', async ({ client, sheetData }, testInfo) => {
    const r = await runValidation(client, sheetData, testInfo, 'Tax_Withholding_Categories');
    expect(r.missingInApi, 'Missing records in API').toHaveLength(0);
    expect(r.fieldMismatches, 'Field mismatches').toHaveLength(0);
  });

  /** ตรวจสอบว่าข้อมูล sheet Item Tax Templates ตรงกับ records ใน ERPNext */
  test('17 - Item Tax Templates (2 records)', async ({ client, sheetData }, testInfo) => {
    const r = await runValidation(client, sheetData, testInfo, 'Item_Tax_Templates');
    expect(r.missingInApi, 'Missing records in API').toHaveLength(0);
    expect(r.fieldMismatches, 'Field mismatches').toHaveLength(0);
  });

});
