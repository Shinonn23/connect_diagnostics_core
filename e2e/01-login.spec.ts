import { test, expect } from '@playwright/test';
import { getDocList } from '../lib/frappe-api';

const BASE = process.env.BASE_URL || 'https://dev.connectdiagnostics.nomeaparadigm.com';

/** ตรวจสอบ session ที่ login แล้ว, การเข้าถึง module, และ ERP modules ที่ติดตั้ง */
test.describe('01 - Login & Navigation', () => {

  /** ยืนยันว่า user ล็อกอินแล้วและ desktop โหลดสำเร็จ */
  test('should be logged in and see desktop', async ({ page }) => {
    await page.goto(`${BASE}/app`);
    await expect(page).toHaveURL(/\/app/);
    await expect(page.locator('.navbar')).toBeVisible();
  });

  /** ตรวจสอบว่าเข้าถึง Setup module ได้โดยไม่มี permission error */
  test('should access Setup module', async ({ page }) => {
    await page.goto(`${BASE}/app/setup`);
    await page.waitForLoadState('load');
    await expect(page.locator('body')).not.toContainText('Not Permitted');
  });

  /** ตรวจสอบว่าเข้าถึง Selling module ได้โดยไม่มี permission error */
  test('should access Selling module', async ({ page }) => {
    await page.goto(`${BASE}/app/selling`);
    await page.waitForLoadState('load');
    await expect(page.locator('body')).not.toContainText('Not Permitted');
  });

  /** ตรวจสอบว่าเข้าถึง Buying module ได้โดยไม่มี permission error */
  test('should access Buying module', async ({ page }) => {
    await page.goto(`${BASE}/app/buying`);
    await page.waitForLoadState('load');
    await expect(page.locator('body')).not.toContainText('Not Permitted');
  });

  /** ตรวจสอบว่าเข้าถึง Stock module ได้โดยไม่มี permission error */
  test('should access Stock module', async ({ page }) => {
    await page.goto(`${BASE}/app/stock`);
    await page.waitForLoadState('load');
    await expect(page.locator('body')).not.toContainText('Not Permitted');
  });

  /** ตรวจสอบว่าเข้าถึง Accounting module ได้โดยไม่มี permission error */
  test('should access Accounting module', async ({ page }) => {
    await page.goto(`${BASE}/app/accounts`);
    await page.waitForLoadState('load');
    await expect(page.locator('body')).not.toContainText('Not Permitted');
  });

  /** ตรวจสอบว่าเข้าถึง HR module ได้โดยไม่มี permission error */
  test('should access HR module', async ({ page }) => {
    await page.goto(`${BASE}/app/hr`);
    await page.waitForLoadState('load');
    await expect(page.locator('body')).not.toContainText('Not Permitted');
  });

  /** ตรวจสอบว่า ERP modules ทั้งหมดถูกติดตั้งแล้วผ่าน API */
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
