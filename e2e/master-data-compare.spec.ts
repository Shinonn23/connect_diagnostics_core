import { expect, test } from '@playwright/test';

import { loadDatasets } from '../scripts/datasets';
import { compareAllDatasets } from '../scripts/compare';
import { loadLocalEnv } from '../scripts/env';
import { FrappeClient, loginToFrappe } from '../scripts/frappe';
import { loadSheetData, normalizeRemoteSourceUrl } from '../scripts/import-files';

loadLocalEnv();

const datasets = loadDatasets();
const hasCredentials =
  Boolean(process.env.ERP_USERNAME) && Boolean(process.env.ERP_PASSWORD);

/** ตรวจสอบว่า master import files ทั้งหมดอ่านได้และมี columns ถูกต้อง */
test('master files are readable', async () => {
  for (const dataset of datasets) {
    const sheet = await loadSheetData(dataset);
    expect(sheet.headers.length, `${dataset.file} should expose columns`).toBeGreaterThan(0);
  }
});

/** เปรียบเทียบ master import files กับข้อมูล ERPNext แบบ real-time และรายงานความแตกต่าง */
test.describe('live comparison', () => {
  test.skip(
    !hasCredentials,
    'Set ERP_USERNAME and ERP_PASSWORD in .env or .env.example to run the live comparison.',
  );

  /** ล็อกอิน ERPNext และตรวจสอบว่าข้อมูลตรงกับ master import files ทั้งหมด */
  test('live ERPNext data matches master import files', async ({ page, baseURL }) => {
    if (!baseURL) {
      throw new Error('Playwright baseURL is missing.');
    }

    await loginToFrappe(
      page,
      process.env.ERP_USERNAME!,
      process.env.ERP_PASSWORD!,
    );

    const client = new FrappeClient(page.context().request, baseURL);
    const summary = await compareAllDatasets(client, datasets);

    await test.info().attach('master-data-summary', {
      path: `${summary.outputDir}\\summary.json`,
      contentType: 'application/json',
    });

    const failingReports = summary.reports.filter((report) =>
      [
        report.errors.length,
        report.unresolvedHeaders.length,
        report.missingRecords.length,
        report.extraRecords.length,
        report.duplicateLiveRecords.length,
        report.fieldMismatches.length,
        report.childTableMismatches.length,
      ].some((count) => count > 0),
    );

    expect(
      failingReports,
      `Mismatch report written to ${summary.outputDir}`,
    ).toEqual([]);
  });
});

/** ตรวจสอบว่า Google Sheets edit URLs ถูกแปลงเป็น CSV และ XLSX export URLs ถูกต้อง */
test('Google Sheets edit URL is converted to an export URL', async () => {
  const csvUrl = normalizeRemoteSourceUrl(
    'https://docs.google.com/spreadsheets/d/abc123/edit#gid=456',
    {
      file: 'Example Sheet',
      format: 'csv',
    },
  );

  expect(csvUrl).toBe(
    'https://docs.google.com/spreadsheets/d/abc123/export?format=csv&gid=456',
  );

  const xlsxUrl = normalizeRemoteSourceUrl(
    'https://docs.google.com/spreadsheets/d/abc123/edit#gid=456',
    {
      file: 'Example Workbook',
      format: 'xlsx',
    },
  );

  expect(xlsxUrl).toBe(
    'https://docs.google.com/spreadsheets/d/abc123/export?format=xlsx',
  );
});
