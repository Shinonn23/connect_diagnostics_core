import { test as base, expect } from '@playwright/test';
import { FrappeClient } from '../lib/frappe-client';
import { loadGoogleSheets, SheetData } from '../lib/excel-reader';

const BASE_URL = process.env.BASE_URL || 'https://dev.connectdiagnostics.nomeaparadigm.com';
const ADMIN_USER = process.env.ERP_USERNAME || 'Administrator';
const ADMIN_PASS = process.env.ERP_PASSWORD || '';

let _cachedSheetData: SheetData | null = null;

export type ValidateFixtures = {
  client: FrappeClient;
  sheetData: SheetData;
};

export const test = base.extend<ValidateFixtures>({
  /** สร้าง FrappeClient instance login เข้าระบบ และคืน context ให้ test ใช้งาน จากนั้น dispose เมื่อเสร็จ */
  client: async ({}, use) => {
    const client = new FrappeClient(BASE_URL);
    await client.login(ADMIN_USER, ADMIN_PASS);
    await use(client);
    await client.dispose();
  },
  /** โหลด Master Data จาก Google Sheets API ครั้งเดียว (cache) แล้วคืน SheetData object ให้ test ทั้งหมดใช้ร่วมกัน */
  sheetData: async ({}, use) => {
    if (!_cachedSheetData) {
      _cachedSheetData = await loadGoogleSheets();
    }
    await use(_cachedSheetData);
  },
});

export { expect };
