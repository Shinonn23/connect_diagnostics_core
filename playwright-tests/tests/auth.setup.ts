import { test as setup, expect } from '@playwright/test';

const BASE = process.env.BASE_URL || 'https://dev.connectdiagnostics.nomeaparadigm.com';
const USER = process.env.ERP_USERNAME || 'Administrator';
const PASS = process.env.ERP_PASSWORD || '';

setup('authenticate', async ({ page }) => {
  await page.goto(`${BASE}/login`);
  await page.locator('#login_email').fill(USER);
  await page.locator('#login_password').fill(PASS);
  await page.locator('.btn-login').click();
  await page.waitForURL(/\/app/, { timeout: 15_000 });
  await expect(page).toHaveURL(/\/app/);
  await page.context().storageState({ path: './auth.json' });
});
