import { test, expect } from './validate.fixture';
import { getSheet } from '../helpers/excel-reader';
import { SHEET_CONFIGS, SheetConfig } from '../helpers/column-map';
import { validateSheet, printResult, printSummary, ValidationResult } from '../helpers/validator';

const STOCK_SHEETS = ['Items', 'Warehouses', 'UOMs', 'Brands', 'Item_Groups'];
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
  if (config.compositeKey) {
    apiFields.push('item_code', 'price_list');
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

test.describe('CD-ERPNext Stock Data Validation', () => {

  test('01 - Items (778 records)', async ({ client, excelData }, testInfo) => {
    const r = await runValidation(client, excelData, testInfo, 'Items');
    expect(r.missingInApi, 'Missing records in API').toHaveLength(0);
    expect(r.fieldMismatches, 'Field mismatches').toHaveLength(0);
  });

  test('02 - Warehouses (52 records)', async ({ client, excelData }, testInfo) => {
    const r = await runValidation(client, excelData, testInfo, 'Warehouses');
    expect(r.missingInApi, 'Missing records in API').toHaveLength(0);
    expect(r.fieldMismatches, 'Field mismatches').toHaveLength(0);
  });

  test('03 - UOMs (250 records)', async ({ client, excelData }, testInfo) => {
    const r = await runValidation(client, excelData, testInfo, 'UOMs');
    expect(r.missingInApi, 'Missing records in API').toHaveLength(0);
    expect(r.fieldMismatches, 'Field mismatches').toHaveLength(0);
  });

  test('04 - Brands (51 records)', async ({ client, excelData }, testInfo) => {
    const r = await runValidation(client, excelData, testInfo, 'Brands');
    expect(r.missingInApi, 'Missing records in API').toHaveLength(0);
    expect(r.fieldMismatches, 'Field mismatches').toHaveLength(0);
  });

  test('05 - Item Groups (15 records)', async ({ client, excelData }, testInfo) => {
    const r = await runValidation(client, excelData, testInfo, 'Item_Groups');
    expect(r.missingInApi, 'Missing records in API').toHaveLength(0);
    expect(r.fieldMismatches, 'Field mismatches').toHaveLength(0);
  });

});
