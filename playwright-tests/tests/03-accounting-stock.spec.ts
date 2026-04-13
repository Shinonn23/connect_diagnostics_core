import { test, expect } from '@playwright/test';
import { getDocList, getCount, checkRequiredFields } from '../helpers/frappe-api';

const BASE = process.env.BASE_URL || 'https://dev.connectdiagnostics.nomeaparadigm.com';

test.describe('03 - Accounting Settings', () => {
  test('fiscal year should exist', async ({ request }) => {
    const count = await getCount(request, 'Fiscal Year');
    console.log(`  Fiscal Years: ${count}`);
    expect(count).toBeGreaterThanOrEqual(1);
  });

  test('current fiscal year should be active', async ({ request }) => {
    const fy = await getDocList(request, 'Fiscal Year', ['name', 'year_start_date', 'year_end_date', 'disabled'], { disabled: 0 });
    expect(fy.length).toBeGreaterThanOrEqual(1);
    console.log(`  Active FY: ${fy.map((f: any) => f.name).join(', ')}`);
  });

  test('cost center should exist', async ({ request }) => {
    const count = await getCount(request, 'Cost Center');
    console.log(`  Cost Centers: ${count}`);
    expect(count).toBeGreaterThanOrEqual(1);
  });

  test('enabled currencies exist', async ({ request }) => {
    const currencies = await getDocList(request, 'Currency', ['name', 'enabled'], { enabled: 1 });
    console.log(`  Enabled Currencies: ${currencies.length}`);
    expect(currencies.length).toBeGreaterThanOrEqual(1);
  });
});

test.describe('03 - Sales Order', () => {
  test('should validate sales orders data', async ({ request }) => {
    const count = await getCount(request, 'Sales Order');
    console.log(`  Sales Orders: ${count}`);
    if (count > 0) {
      const orders = await getDocList(request, 'Sales Order', ['name', 'customer', 'transaction_date', 'company', 'grand_total', 'status']);
      for (const so of orders) {
        const missing = checkRequiredFields(so, ['customer', 'transaction_date', 'company']);
        expect(missing, `SO "${so.name}" missing: ${JSON.stringify(missing)}`).toHaveLength(0);
      }
    }
    expect(count).toBeGreaterThanOrEqual(0);
  });

  test('sales order list page loads', async ({ page }) => {
    await page.goto(`${BASE}/app/sales-order`);
    await page.waitForLoadState('load');
    await expect(page.locator('body')).not.toContainText('Not Permitted');
  });
});

test.describe('03 - Sales Invoice', () => {
  test('should validate sales invoices data', async ({ request }) => {
    const count = await getCount(request, 'Sales Invoice');
    console.log(`  Sales Invoices: ${count}`);
    if (count > 0) {
      const invoices = await getDocList(request, 'Sales Invoice', ['name', 'customer', 'posting_date', 'company', 'grand_total', 'status']);
      for (const inv of invoices) {
        const missing = checkRequiredFields(inv, ['customer', 'posting_date', 'company']);
        expect(missing, `SI "${inv.name}" missing: ${JSON.stringify(missing)}`).toHaveLength(0);
      }
    }
    expect(count).toBeGreaterThanOrEqual(0);
  });

  test('sales invoice list page loads', async ({ page }) => {
    await page.goto(`${BASE}/app/sales-invoice`);
    await page.waitForLoadState('load');
    await expect(page.locator('body')).not.toContainText('Not Permitted');
  });
});

test.describe('03 - Purchase Order', () => {
  test('should validate purchase orders data', async ({ request }) => {
    const count = await getCount(request, 'Purchase Order');
    console.log(`  Purchase Orders: ${count}`);
    if (count > 0) {
      const orders = await getDocList(request, 'Purchase Order', ['name', 'supplier', 'transaction_date', 'company', 'grand_total', 'status']);
      for (const po of orders) {
        const missing = checkRequiredFields(po, ['supplier', 'transaction_date', 'company']);
        expect(missing, `PO "${po.name}" missing: ${JSON.stringify(missing)}`).toHaveLength(0);
      }
    }
    expect(count).toBeGreaterThanOrEqual(0);
  });

  test('purchase order list page loads', async ({ page }) => {
    await page.goto(`${BASE}/app/purchase-order`);
    await page.waitForLoadState('load');
    await expect(page.locator('body')).not.toContainText('Not Permitted');
  });
});

test.describe('03 - Purchase Invoice', () => {
  test('should validate purchase invoices data', async ({ request }) => {
    const count = await getCount(request, 'Purchase Invoice');
    console.log(`  Purchase Invoices: ${count}`);
    if (count > 0) {
      const invoices = await getDocList(request, 'Purchase Invoice', ['name', 'supplier', 'posting_date', 'company', 'grand_total', 'status']);
      for (const inv of invoices) {
        const missing = checkRequiredFields(inv, ['supplier', 'posting_date', 'company']);
        expect(missing, `PI "${inv.name}" missing: ${JSON.stringify(missing)}`).toHaveLength(0);
      }
    }
    expect(count).toBeGreaterThanOrEqual(0);
  });

  test('purchase invoice list page loads', async ({ page }) => {
    await page.goto(`${BASE}/app/purchase-invoice`);
    await page.waitForLoadState('load');
    await expect(page.locator('body')).not.toContainText('Not Permitted');
  });
});

test.describe('03 - Stock', () => {
  test('should have UOM defined', async ({ request }) => {
    const count = await getCount(request, 'UOM');
    console.log(`  UOMs: ${count}`);
    expect(count).toBeGreaterThan(0);
  });

  test('should validate stock entries (if any)', async ({ request }) => {
    const count = await getCount(request, 'Stock Entry');
    console.log(`  Stock Entries: ${count}`);
    if (count > 0) {
      const entries = await getDocList(request, 'Stock Entry', ['name', 'stock_entry_type', 'posting_date', 'company', 'docstatus']);
      for (const se of entries) {
        const missing = checkRequiredFields(se, ['stock_entry_type', 'posting_date', 'company']);
        expect(missing, `SE "${se.name}" missing: ${JSON.stringify(missing)}`).toHaveLength(0);
      }
    }
    expect(count).toBeGreaterThanOrEqual(0);
  });

  test('stock entry list page loads', async ({ page }) => {
    await page.goto(`${BASE}/app/stock-entry`);
    await page.waitForLoadState('load');
    await expect(page.locator('body')).not.toContainText('Not Permitted');
  });

  test('stock ledger report loads', async ({ page }) => {
    await page.goto(`${BASE}/app/query-report/Stock Ledger`);
    await page.waitForLoadState('load');
    await expect(page.locator('body')).not.toContainText('Not Permitted');
  });
});

test.describe('03 - Payment & Journal Entries', () => {
  test('should validate payment entries (if any)', async ({ request }) => {
    const count = await getCount(request, 'Payment Entry');
    console.log(`  Payment Entries: ${count}`);
    if (count > 0) {
      const payments = await getDocList(request, 'Payment Entry', ['name', 'payment_type', 'posting_date', 'company', 'paid_amount']);
      for (const pe of payments) {
        const missing = checkRequiredFields(pe, ['payment_type', 'posting_date', 'company']);
        expect(missing, `PE "${pe.name}" missing: ${JSON.stringify(missing)}`).toHaveLength(0);
      }
    }
    expect(count).toBeGreaterThanOrEqual(0);
  });

  test('should validate journal entries (if any)', async ({ request }) => {
    const count = await getCount(request, 'Journal Entry');
    console.log(`  Journal Entries: ${count}`);
    if (count > 0) {
      const journals = await getDocList(request, 'Journal Entry', ['name', 'posting_date', 'company', 'total_debit', 'total_credit']);
      for (const je of journals) {
        const missing = checkRequiredFields(je, ['posting_date', 'company']);
        expect(missing, `JE "${je.name}" missing: ${JSON.stringify(missing)}`).toHaveLength(0);
        expect(je.total_debit).toEqual(je.total_credit);
      }
    }
    expect(count).toBeGreaterThanOrEqual(0);
  });
});

test.describe('03 - Quotation & Delivery', () => {
  test('quotation list page loads', async ({ page }) => {
    await page.goto(`${BASE}/app/quotation`);
    await page.waitForLoadState('load');
    await expect(page.locator('body')).not.toContainText('Not Permitted');
  });

  test('delivery note list page loads', async ({ page }) => {
    await page.goto(`${BASE}/app/delivery-note`);
    await page.waitForLoadState('load');
    await expect(page.locator('body')).not.toContainText('Not Permitted');
  });

  test('purchase receipt list page loads', async ({ page }) => {
    await page.goto(`${BASE}/app/purchase-receipt`);
    await page.waitForLoadState('load');
    await expect(page.locator('body')).not.toContainText('Not Permitted');
  });
});
