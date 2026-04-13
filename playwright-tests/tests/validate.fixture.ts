import { test as base, expect } from '@playwright/test';
import { FrappeClient } from '../helpers/frappe-client';
import { loadExcel, ExcelData } from '../helpers/excel-reader';

const BASE_URL = process.env.BASE_URL || 'https://dev.connectdiagnostics.nomeaparadigm.com';
const ADMIN_USER = process.env.ERP_USERNAME || 'Administrator';
const ADMIN_PASS = process.env.ERP_PASSWORD || '';

export type ValidateFixtures = {
  client: FrappeClient;
  excelData: ExcelData;
};

export const test = base.extend<ValidateFixtures>({
  client: async ({}, use) => {
    const client = new FrappeClient(BASE_URL);
    await client.login(ADMIN_USER, ADMIN_PASS);
    await use(client);
    await client.dispose();
  },
  excelData: async ({}, use) => {
    const data = loadExcel();
    await use(data);
  },
});

export { expect };
