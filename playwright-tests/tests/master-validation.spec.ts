import { test, expect } from './validate.fixture';
import { getSheet } from '../helpers/excel-reader';
import { SHEET_CONFIGS, SheetConfig } from '../helpers/column-map';
import { validateSheet, printResult, printSummary, ValidationResult } from '../helpers/validator';

const allResults: ValidationResult[] = [];

test.afterAll(() => {
  printSummary(allResults);
});

function getConfig(sheetName: string): SheetConfig {
  const cfg = SHEET_CONFIGS.find((c) => c.sheetName === sheetName);
  if (!cfg) throw new Error(`No config for sheet: ${sheetName}`);
  return cfg;
}

async function runValidation(
  client: any,
  excelData: any,
  testInfo: any,
  sheetName: string,
) {
  const config = getConfig(sheetName);
  const excelRows = getSheet(excelData, config.sheetName);

  const apiFields = ['name', ...new Set(config.fields.map((f) => f.api))];
  if (config.keyApi !== 'name' && !apiFields.includes(config.keyApi)) {
    apiFields.push(config.keyApi);
  }

  const apiRecords = await client.getDocList(config.doctype, apiFields, config.filters || {}, 0);

  const result = validateSheet(excelRows, apiRecords, config);
  allResults.push(result);
  printResult(result);

  await testInfo.attach(`${config.doctype}-validation.json`, {
    body: JSON.stringify(result, null, 2),
    contentType: 'application/json',
  });

  return result;
}

test.describe('CD-ERPNext Master Data Validation (18 Sheets)', () => {

  test('01 - Companies (3 records)', async ({ client, excelData }, testInfo) => {
    const r = await runValidation(client, excelData, testInfo, 'Companies');
    expect(r.missingInApi, 'Missing records in API').toHaveLength(0);
    expect(r.fieldMismatches, 'Field mismatches').toHaveLength(0);
  });

  test('02 - Customers (1,239 records)', async ({ client, excelData }, testInfo) => {
    const r = await runValidation(client, excelData, testInfo, 'Customers');
    expect(r.missingInApi, 'Missing records in API').toHaveLength(0);
    expect(r.fieldMismatches, 'Field mismatches').toHaveLength(0);
  });

  test('03 - Suppliers (624 records)', async ({ client, excelData }, testInfo) => {
    const r = await runValidation(client, excelData, testInfo, 'Suppliers');
    expect(r.missingInApi, 'Missing records in API').toHaveLength(0);
    expect(r.fieldMismatches, 'Field mismatches').toHaveLength(0);
  });

  test('04 - Items (778 records)', async ({ client, excelData }, testInfo) => {
    const r = await runValidation(client, excelData, testInfo, 'Items');
    expect(r.missingInApi, 'Missing records in API').toHaveLength(0);
    expect(r.fieldMismatches, 'Field mismatches').toHaveLength(0);
  });

  test('05 - Employees (45 records)', async ({ client, excelData }, testInfo) => {
    const r = await runValidation(client, excelData, testInfo, 'Employees');
    expect(r.missingInApi, 'Missing records in API').toHaveLength(0);
    expect(r.fieldMismatches, 'Field mismatches').toHaveLength(0);
  });

  test('06 - Warehouses (52 records)', async ({ client, excelData }, testInfo) => {
    const r = await runValidation(client, excelData, testInfo, 'Warehouses');
    expect(r.missingInApi, 'Missing records in API').toHaveLength(0);
    expect(r.fieldMismatches, 'Field mismatches').toHaveLength(0);
  });

  test('07 - Item Groups (15 records)', async ({ client, excelData }, testInfo) => {
    const r = await runValidation(client, excelData, testInfo, 'Item_Groups');
    expect(r.missingInApi, 'Missing records in API').toHaveLength(0);
    expect(r.fieldMismatches, 'Field mismatches').toHaveLength(0);
  });

  test('08 - Customer Groups (11 records)', async ({ client, excelData }, testInfo) => {
    const r = await runValidation(client, excelData, testInfo, 'Customer_Groups');
    expect(r.missingInApi, 'Missing records in API').toHaveLength(0);
    expect(r.fieldMismatches, 'Field mismatches').toHaveLength(0);
  });

  test('09 - Supplier Groups (3 records)', async ({ client, excelData }, testInfo) => {
    const r = await runValidation(client, excelData, testInfo, 'Supplier_Groups');
    expect(r.missingInApi, 'Missing records in API').toHaveLength(0);
    expect(r.fieldMismatches, 'Field mismatches').toHaveLength(0);
  });

  test('10 - Territories (12 records)', async ({ client, excelData }, testInfo) => {
    const r = await runValidation(client, excelData, testInfo, 'Territories');
    expect(r.missingInApi, 'Missing records in API').toHaveLength(0);
    expect(r.fieldMismatches, 'Field mismatches').toHaveLength(0);
  });

  test('11 - Departments (20 records)', async ({ client, excelData }, testInfo) => {
    const r = await runValidation(client, excelData, testInfo, 'Departments');
    expect(r.missingInApi, 'Missing records in API').toHaveLength(0);
    expect(r.fieldMismatches, 'Field mismatches').toHaveLength(0);
  });

  test('12 - UOMs (250 records)', async ({ client, excelData }, testInfo) => {
    const r = await runValidation(client, excelData, testInfo, 'UOMs');
    expect(r.missingInApi, 'Missing records in API').toHaveLength(0);
    expect(r.fieldMismatches, 'Field mismatches').toHaveLength(0);
  });

  test('13 - Currencies (31 records)', async ({ client, excelData }, testInfo) => {
    const r = await runValidation(client, excelData, testInfo, 'Currencies');
    expect(r.missingInApi, 'Missing records in API').toHaveLength(0);
    expect(r.fieldMismatches, 'Field mismatches').toHaveLength(0);
  });

  test('14 - Brands (51 records)', async ({ client, excelData }, testInfo) => {
    const r = await runValidation(client, excelData, testInfo, 'Brands');
    expect(r.missingInApi, 'Missing records in API').toHaveLength(0);
    expect(r.fieldMismatches, 'Field mismatches').toHaveLength(0);
  });

  test('15 - Accounts (219 records)', async ({ client, excelData }, testInfo) => {
    const r = await runValidation(client, excelData, testInfo, 'Accounts New');
    expect(r.missingInApi, 'Missing records in API').toHaveLength(0);
    expect(r.fieldMismatches, 'Field mismatches').toHaveLength(0);
  });

  test('16 - Tax Withholding Categories (10 records)', async ({ client, excelData }, testInfo) => {
    const r = await runValidation(client, excelData, testInfo, 'Tax_Withholding_Categories');
    expect(r.missingInApi, 'Missing records in API').toHaveLength(0);
    expect(r.fieldMismatches, 'Field mismatches').toHaveLength(0);
  });

  test('17 - Item Tax Templates (2 records)', async ({ client, excelData }, testInfo) => {
    const r = await runValidation(client, excelData, testInfo, 'Item_Tax_Templates');
    expect(r.missingInApi, 'Missing records in API').toHaveLength(0);
    expect(r.fieldMismatches, 'Field mismatches').toHaveLength(0);
  });

});
