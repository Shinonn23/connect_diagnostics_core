import { test, expect } from '@playwright/test';
import { getDocList, getCount, checkRequiredFields } from '../lib/frappe-api';

const BASE = process.env.BASE_URL || 'https://dev.connectdiagnostics.nomeaparadigm.com';

/** ตรวจสอบข้อมูล Company: มีอยู่, required fields, และเข้าถึง UI ได้ */
test.describe('02 - Company', () => {
  /** ตรวจสอบว่ามี Company อย่างน้อย 1 รายการ */
  test('should have at least 1 company', async ({ request }) => {
    const count = await getCount(request, 'Company');
    console.log(`  Companies: ${count}`);
    expect(count).toBeGreaterThanOrEqual(1);
  });

  /** ตรวจสอบว่า Company ทุกรายการมี required fields ครบ */
  test('each company should have required fields', async ({ request }) => {
    const companies = await getDocList(request, 'Company', [
      'name', 'company_name', 'default_currency', 'country',
    ]);
    for (const c of companies) {
      const missing = checkRequiredFields(c, ['company_name', 'default_currency', 'country']);
      expect(missing, `Company "${c.name}" missing: ${JSON.stringify(missing)}`).toHaveLength(0);
    }
  });

  /** ตรวจสอบว่าหน้า Company list โหลดได้โดยไม่มี permission error */
  test('company list page loads in UI', async ({ page }) => {
    await page.goto(`${BASE}/app/company`);
    await page.waitForLoadState('load');
    await expect(page.locator('body')).not.toContainText('Not Permitted');
  });
});

/** ตรวจสอบข้อมูล Customer: มีอยู่, required fields, และเข้าถึง UI ได้ */
test.describe('02 - Customer', () => {
  /** ตรวจสอบว่ามี Customer อย่างน้อย 1 รายการ */
  test('should have at least 1 customer', async ({ request }) => {
    const count = await getCount(request, 'Customer');
    console.log(`  Customers: ${count}`);
    expect(count).toBeGreaterThanOrEqual(1);
  });

  /** ตรวจสอบว่า Customer ทุกรายการมี required fields ครบ, ยอมให้ขาดได้ไม่เกิน 10 รายการ */
  test('each customer should have required fields', async ({ request }) => {
    const customers = await getDocList(request, 'Customer', [
      'name', 'customer_name', 'customer_type', 'customer_group', 'territory',
    ]);
    const issues: string[] = [];
    for (const c of customers) {
      const missing = checkRequiredFields(c, ['customer_name', 'customer_type', 'customer_group', 'territory']);
      if (missing.length > 0) {
        issues.push(`"${c.name}" missing: ${missing.map(m => m.field).join(', ')}`);
      }
    }
    if (issues.length > 0) {
      console.log(`  Customers with missing fields (${issues.length}):`);
      for (const issue of issues) console.log(`    - ${issue}`);
    }
    expect(issues.length, `${issues.length} customers have missing required fields`).toBeLessThanOrEqual(10);
  });

  /** ตรวจสอบว่าหน้า Customer list โหลดได้โดยไม่มี permission error */
  test('customer list page loads in UI', async ({ page }) => {
    await page.goto(`${BASE}/app/customer`);
    await page.waitForLoadState('load');
    await expect(page.locator('body')).not.toContainText('Not Permitted');
  });
});

/** ตรวจสอบข้อมูล Supplier: มีอยู่, required fields, และเข้าถึง UI ได้ */
test.describe('02 - Supplier', () => {
  /** ตรวจสอบว่ามี Supplier อย่างน้อย 1 รายการ */
  test('should have at least 1 supplier', async ({ request }) => {
    const count = await getCount(request, 'Supplier');
    console.log(`  Suppliers: ${count}`);
    expect(count).toBeGreaterThanOrEqual(1);
  });

  /** ตรวจสอบว่า Supplier ทุกรายการมี required fields ครบ */
  test('each supplier should have required fields', async ({ request }) => {
    const suppliers = await getDocList(request, 'Supplier', [
      'name', 'supplier_name', 'supplier_group',
    ]);
    for (const s of suppliers) {
      const missing = checkRequiredFields(s, ['supplier_name', 'supplier_group']);
      expect(missing, `Supplier "${s.name}" missing: ${JSON.stringify(missing)}`).toHaveLength(0);
    }
  });

  /** ตรวจสอบว่าหน้า Supplier list โหลดได้โดยไม่มี permission error */
  test('supplier list page loads in UI', async ({ page }) => {
    await page.goto(`${BASE}/app/supplier`);
    await page.waitForLoadState('load');
    await expect(page.locator('body')).not.toContainText('Not Permitted');
  });
});

/** ตรวจสอบข้อมูล Item: มีอยู่, required fields, และเข้าถึง UI ได้ */
test.describe('02 - Item', () => {
  /** ตรวจสอบว่ามี Item อย่างน้อย 1 รายการ */
  test('should have at least 1 item', async ({ request }) => {
    const count = await getCount(request, 'Item');
    console.log(`  Items: ${count}`);
    expect(count).toBeGreaterThanOrEqual(1);
  });

  /** ตรวจสอบว่า Item ทุกรายการมี required fields ครบ */
  test('each item should have required fields', async ({ request }) => {
    const items = await getDocList(request, 'Item', ['name', 'item_name', 'item_group', 'stock_uom']);
    for (const item of items) {
      const missing = checkRequiredFields(item, ['item_name', 'item_group', 'stock_uom']);
      expect(missing, `Item "${item.name}" missing: ${JSON.stringify(missing)}`).toHaveLength(0);
    }
  });

  /** ตรวจสอบว่าหน้า Item list โหลดได้โดยไม่มี permission error */
  test('item list page loads in UI', async ({ page }) => {
    await page.goto(`${BASE}/app/item`);
    await page.waitForLoadState('load');
    await expect(page.locator('body')).not.toContainText('Not Permitted');
  });
});

/** ตรวจสอบข้อมูล Employee: มีอยู่, required fields, และเข้าถึง UI ได้ */
test.describe('02 - Employee', () => {
  /** ตรวจสอบว่ามี Employee อย่างน้อย 1 รายการ */
  test('should have at least 1 employee', async ({ request }) => {
    const count = await getCount(request, 'Employee');
    console.log(`  Employees: ${count}`);
    expect(count).toBeGreaterThanOrEqual(1);
  });

  /** ตรวจสอบว่า Employee ทุกรายการมี required fields ครบ */
  test('each employee should have required fields', async ({ request }) => {
    const employees = await getDocList(request, 'Employee', [
      'name', 'employee_name', 'company', 'status', 'gender', 'date_of_birth', 'date_of_joining',
    ]);
    for (const emp of employees) {
      const missing = checkRequiredFields(emp, ['employee_name', 'company', 'status', 'gender', 'date_of_birth', 'date_of_joining']);
      expect(missing, `Employee "${emp.name}" missing: ${JSON.stringify(missing)}`).toHaveLength(0);
    }
  });

  /** ตรวจสอบว่าหน้า Employee list โหลดได้โดยไม่มี permission error */
  test('employee list page loads in UI', async ({ page }) => {
    await page.goto(`${BASE}/app/employee`);
    await page.waitForLoadState('load');
    await expect(page.locator('body')).not.toContainText('Not Permitted');
  });
});

/** ตรวจสอบข้อมูล Warehouse: มีอยู่และ required fields */
test.describe('02 - Warehouse', () => {
  /** ตรวจสอบว่ามี Warehouse อย่างน้อย 1 รายการ */
  test('should have at least 1 warehouse', async ({ request }) => {
    const count = await getCount(request, 'Warehouse');
    console.log(`  Warehouses: ${count}`);
    expect(count).toBeGreaterThanOrEqual(1);
  });

  /** ตรวจสอบว่า Warehouse ทุกรายการมี warehouse_name และ company */
  test('each warehouse should have company set', async ({ request }) => {
    const warehouses = await getDocList(request, 'Warehouse', ['name', 'warehouse_name', 'company']);
    for (const w of warehouses) {
      const missing = checkRequiredFields(w, ['warehouse_name', 'company']);
      expect(missing, `Warehouse "${w.name}" missing: ${JSON.stringify(missing)}`).toHaveLength(0);
    }
  });
});

/** ตรวจสอบ Chart of Accounts: จำนวน account และโครงสร้าง root account */
test.describe('02 - Chart of Accounts', () => {
  /** ตรวจสอบว่ามี account จำนวนเพียงพอ */
  test('should have accounts setup', async ({ request }) => {
    const count = await getCount(request, 'Account');
    console.log(`  Accounts: ${count}`);
    expect(count).toBeGreaterThan(10);
  });

  /** ตรวจสอบว่ามี root account ครบทั้ง 4 ประเภท (Asset, Liability, Income, Expense) */
  test('root accounts should exist', async ({ request }) => {
    const roots = await getDocList(request, 'Account', ['name', 'root_type'], {
      is_group: 1, parent_account: ['is', 'not set'],
    });
    const rootTypes = roots.map((r: any) => r.root_type);
    expect(rootTypes).toContain('Asset');
    expect(rootTypes).toContain('Liability');
    expect(rootTypes).toContain('Income');
    expect(rootTypes).toContain('Expense');
  });
});

/** ตรวจสอบ classification groups: item groups, customer groups, territories, และ supplier groups */
test.describe('02 - Groups & Territory', () => {
  /** ตรวจสอบว่ามี Item Group อย่างน้อย 1 รายการ */
  test('should have item groups', async ({ request }) => {
    const count = await getCount(request, 'Item Group');
    expect(count).toBeGreaterThanOrEqual(1);
  });
  /** ตรวจสอบว่ามี Customer Group อย่างน้อย 1 รายการ */
  test('should have customer groups', async ({ request }) => {
    const count = await getCount(request, 'Customer Group');
    expect(count).toBeGreaterThanOrEqual(1);
  });
  /** ตรวจสอบว่ามี Territory อย่างน้อย 1 รายการ */
  test('should have territories', async ({ request }) => {
    const count = await getCount(request, 'Territory');
    expect(count).toBeGreaterThanOrEqual(1);
  });
  /** ตรวจสอบว่ามี Supplier Group อย่างน้อย 1 รายการ */
  test('should have supplier groups', async ({ request }) => {
    const count = await getCount(request, 'Supplier Group');
    expect(count).toBeGreaterThanOrEqual(1);
  });
});
