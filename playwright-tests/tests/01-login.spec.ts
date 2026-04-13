import { test, expect } from '@playwright/test';
import { getDocList } from '../helpers/frappe-api';

const BASE = process.env.BASE_URL || 'https://dev.connectdiagnostics.nomeaparadigm.com';

test.describe('01 - Login & Navigation', () => {

  test('should be logged in and see desktop', async ({ page }) => {
    await page.goto(`${BASE}/app`);
    await expect(page).toHaveURL(/\/app/);
    await expect(page.locator('.navbar')).toBeVisible();
  });

  test('should access Setup module', async ({ page }) => {
    await page.goto(`${BASE}/app/setup`);
    await page.waitForLoadState('load');
    await expect(page.locator('body')).not.toContainText('Not Permitted');
  });

  test('should access Selling module', async ({ page }) => {
    await page.goto(`${BASE}/app/selling`);
    await page.waitForLoadState('load');
    await expect(page.locator('body')).not.toContainText('Not Permitted');
  });

  test('should access Buying module', async ({ page }) => {
    await page.goto(`${BASE}/app/buying`);
    await page.waitForLoadState('load');
    await expect(page.locator('body')).not.toContainText('Not Permitted');
  });

  test('should access Stock module', async ({ page }) => {
    await page.goto(`${BASE}/app/stock`);
    await page.waitForLoadState('load');
    await expect(page.locator('body')).not.toContainText('Not Permitted');
  });

  test('should access Accounting module', async ({ page }) => {
    await page.goto(`${BASE}/app/accounts`);
    await page.waitForLoadState('load');
    await expect(page.locator('body')).not.toContainText('Not Permitted');
  });

  test('should access HR module', async ({ page }) => {
    await page.goto(`${BASE}/app/hr`);
    await page.waitForLoadState('load');
    await expect(page.locator('body')).not.toContainText('Not Permitted');
  });

  test('should verify all 5 installed apps via API', async ({ request }) => {
    const modules = await getDocList(request, 'Module Def', ['name'], {}, 0);
    const moduleNames = modules.map((m: any) => m.name);
    console.log(`  Modules (${moduleNames.length}): ${moduleNames.filter((n: string) => !n.startsWith('_')).join(', ')}`);
    expect(moduleNames).toContain('Connect Diagnostics Core');
    expect(moduleNames).toContain('CD Stock');
    expect(moduleNames).toContain('Thai Tax');
    expect(moduleNames).toContain('HR');
    expect(moduleNames).toContain('Payroll');
    expect(moduleNames).toContain('Accounts');
    expect(moduleNames).toContain('Selling');
    expect(moduleNames).toContain('Buying');
    expect(moduleNames).toContain('Stock');
  });
});
