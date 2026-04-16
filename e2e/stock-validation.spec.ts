import { test, expect } from './validate.fixture';
import { getSheet } from '../lib/excel-reader';
import { SHEET_CONFIGS, SheetConfig } from '../lib/column-map';
import { validateSheet, printResult, printSummary, ValidationResult } from '../lib/validator';

const STOCK_SHEETS = ['Items', 'Warehouses', 'UOMs', 'Brands', 'Item_Groups'];
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
  if (config.compositeKey) {
    apiFields.push('item_code', 'price_list');
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

/** ตรวจสอบข้อมูล stock-related master data จาก Google Sheets เทียบกับ ERPNext API */
test.describe('CD-ERPNext Stock Data Validation', () => {

  /** ตรวจสอบว่าข้อมูล sheet Items ตรงกับ Item records ใน ERPNext */
  test('01 - Items (778 records)', async ({ client, sheetData }, testInfo) => {
    const r = await runValidation(client, sheetData, testInfo, 'Items');
    expect(r.missingInApi, 'Missing records in API').toHaveLength(0);
    expect(r.fieldMismatches, 'Field mismatches').toHaveLength(0);
  });

  /** ตรวจสอบว่าข้อมูล sheet Warehouses ตรงกับ Warehouse records ใน ERPNext */
  test('02 - Warehouses (52 records)', async ({ client, sheetData }, testInfo) => {
    const r = await runValidation(client, sheetData, testInfo, 'Warehouses');
    expect(r.missingInApi, 'Missing records in API').toHaveLength(0);
    expect(r.fieldMismatches, 'Field mismatches').toHaveLength(0);
  });

  /** ตรวจสอบว่าข้อมูล sheet UOMs ตรงกับ UOM records ใน ERPNext */
  test('03 - UOMs (250 records)', async ({ client, sheetData }, testInfo) => {
    const r = await runValidation(client, sheetData, testInfo, 'UOMs');
    expect(r.missingInApi, 'Missing records in API').toHaveLength(0);
    expect(r.fieldMismatches, 'Field mismatches').toHaveLength(0);
  });

  /** ตรวจสอบว่าข้อมูล sheet Brands ตรงกับ Brand records ใน ERPNext */
  test('04 - Brands (51 records)', async ({ client, sheetData }, testInfo) => {
    const r = await runValidation(client, sheetData, testInfo, 'Brands');
    expect(r.missingInApi, 'Missing records in API').toHaveLength(0);
    expect(r.fieldMismatches, 'Field mismatches').toHaveLength(0);
  });

  /** ตรวจสอบว่าข้อมูล sheet Item Groups ตรงกับ Item Group records ใน ERPNext */
  test('05 - Item Groups (15 records)', async ({ client, sheetData }, testInfo) => {
    const r = await runValidation(client, sheetData, testInfo, 'Item_Groups');
    expect(r.missingInApi, 'Missing records in API').toHaveLength(0);
    expect(r.fieldMismatches, 'Field mismatches').toHaveLength(0);
  });

});
