import { test, expect } from '@playwright/test';
import { getDocList, getCount, checkRequiredFields } from '../helpers/frappe-api';

const BASE = process.env.BASE_URL || 'https://dev.connectdiagnostics.nomeaparadigm.com';

test.describe('02 - Company', () => {
  test('should have at least 1 company', async ({ request }) => {
    const count = await getCount(request, 'Company');
    console.log(`  Companies: ${count}`);
    expect(count).toBeGreaterThanOrEqual(1);
  });

  test('each company should have required fields', async ({ request }) => {
    const companies = await getDocList(request, 'Company', [
      'name', 'company_name', 'default_currency', 'country',
    ]);
    for (const c of companies) {
      const missing = checkRequiredFields(c, ['company_name', 'default_currency', 'country']);
      expect(missing, `Company "${c.name}" missing: ${JSON.stringify(missing)}`).toHaveLength(0);
    }
  });

  test('company list page loads in UI', async ({ page }) => {
    await page.goto(`${BASE}/app/company`);
    await page.waitForLoadState('load');
    await expect(page.locator('body')).not.toContainText('Not Permitted');
  });
});

test.describe('02 - Customer', () => {
  test('should have at least 1 customer', async ({ request }) => {
    const count = await getCount(request, 'Customer');
    console.log(`  Customers: ${count}`);
    expect(count).toBeGreaterThanOrEqual(1);
  });

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

  test('customer list page loads in UI', async ({ page }) => {
    await page.goto(`${BASE}/app/customer`);
    await page.waitForLoadState('load');
    await expect(page.locator('body')).not.toContainText('Not Permitted');
  });
});

test.describe('02 - Supplier', () => {
  test('should have at least 1 supplier', async ({ request }) => {
    const count = await getCount(request, 'Supplier');
    console.log(`  Suppliers: ${count}`);
    expect(count).toBeGreaterThanOrEqual(1);
  });

  test('each supplier should have required fields', async ({ request }) => {
    const suppliers = await getDocList(request, 'Supplier', [
      'name', 'supplier_name', 'supplier_group',
    ]);
    for (const s of suppliers) {
      const missing = checkRequiredFields(s, ['supplier_name', 'supplier_group']);
      expect(missing, `Supplier "${s.name}" missing: ${JSON.stringify(missing)}`).toHaveLength(0);
    }
  });

  test('supplier list page loads in UI', async ({ page }) => {
    await page.goto(`${BASE}/app/supplier`);
    await page.waitForLoadState('load');
    await expect(page.locator('body')).not.toContainText('Not Permitted');
  });
});

test.describe('02 - Item', () => {
  test('should have at least 1 item', async ({ request }) => {
    const count = await getCount(request, 'Item');
    console.log(`  Items: ${count}`);
    expect(count).toBeGreaterThanOrEqual(1);
  });

  test('each item should have required fields', async ({ request }) => {
    const items = await getDocList(request, 'Item', ['name', 'item_name', 'item_group', 'stock_uom']);
    for (const item of items) {
      const missing = checkRequiredFields(item, ['item_name', 'item_group', 'stock_uom']);
      expect(missing, `Item "${item.name}" missing: ${JSON.stringify(missing)}`).toHaveLength(0);
    }
  });

  test('item list page loads in UI', async ({ page }) => {
    await page.goto(`${BASE}/app/item`);
    await page.waitForLoadState('load');
    await expect(page.locator('body')).not.toContainText('Not Permitted');
  });
});

test.describe('02 - Employee', () => {
  test('should have at least 1 employee', async ({ request }) => {
    const count = await getCount(request, 'Employee');
    console.log(`  Employees: ${count}`);
    expect(count).toBeGreaterThanOrEqual(1);
  });

  test('each employee should have required fields', async ({ request }) => {
    const employees = await getDocList(request, 'Employee', [
      'name', 'employee_name', 'company', 'status', 'gender', 'date_of_birth', 'date_of_joining',
    ]);
    for (const emp of employees) {
      const missing = checkRequiredFields(emp, ['employee_name', 'company', 'status', 'gender', 'date_of_birth', 'date_of_joining']);
      expect(missing, `Employee "${emp.name}" missing: ${JSON.stringify(missing)}`).toHaveLength(0);
    }
  });

  test('employee list page loads in UI', async ({ page }) => {
    await page.goto(`${BASE}/app/employee`);
    await page.waitForLoadState('load');
    await expect(page.locator('body')).not.toContainText('Not Permitted');
  });
});

test.describe('02 - Warehouse', () => {
  test('should have at least 1 warehouse', async ({ request }) => {
    const count = await getCount(request, 'Warehouse');
    console.log(`  Warehouses: ${count}`);
    expect(count).toBeGreaterThanOrEqual(1);
  });

  test('each warehouse should have company set', async ({ request }) => {
    const warehouses = await getDocList(request, 'Warehouse', ['name', 'warehouse_name', 'company']);
    for (const w of warehouses) {
      const missing = checkRequiredFields(w, ['warehouse_name', 'company']);
      expect(missing, `Warehouse "${w.name}" missing: ${JSON.stringify(missing)}`).toHaveLength(0);
    }
  });
});

test.describe('02 - Chart of Accounts', () => {
  test('should have accounts setup', async ({ request }) => {
    const count = await getCount(request, 'Account');
    console.log(`  Accounts: ${count}`);
    expect(count).toBeGreaterThan(10);
  });

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

test.describe('02 - Groups & Territory', () => {
  test('should have item groups', async ({ request }) => {
    const count = await getCount(request, 'Item Group');
    expect(count).toBeGreaterThanOrEqual(1);
  });
  test('should have customer groups', async ({ request }) => {
    const count = await getCount(request, 'Customer Group');
    expect(count).toBeGreaterThanOrEqual(1);
  });
  test('should have territories', async ({ request }) => {
    const count = await getCount(request, 'Territory');
    expect(count).toBeGreaterThanOrEqual(1);
  });
  test('should have supplier groups', async ({ request }) => {
    const count = await getCount(request, 'Supplier Group');
    expect(count).toBeGreaterThanOrEqual(1);
  });
});
