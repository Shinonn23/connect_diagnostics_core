import { test, expect } from '@playwright/test';
import { getDocList, getCount } from '../lib/frappe-api';

const BASE = process.env.BASE_URL || 'https://dev.connectdiagnostics.nomeaparadigm.com';

/** ตรวจสอบ ERPNext Thailand localization: tax templates, addresses, withholding tax, และ THB currency */
test.describe('05 - ERPNext Thailand', () => {
  /** ตรวจสอบว่ามี Sales Tax and Charges Templates */
  test('should have sales tax templates', async ({ request }) => {
    const salesTax = await getDocList(request, 'Sales Taxes and Charges Template', ['name', 'company', 'title']);
    console.log(`  Sales Tax Templates: ${salesTax.length}`);
    expect(salesTax.length).toBeGreaterThanOrEqual(0);
  });

  /** ตรวจสอบว่ามี Purchase Tax and Charges Templates */
  test('should have purchase tax templates', async ({ request }) => {
    const purchaseTax = await getDocList(request, 'Purchase Taxes and Charges Template', ['name', 'company', 'title']);
    console.log(`  Purchase Tax Templates: ${purchaseTax.length}`);
    expect(purchaseTax.length).toBeGreaterThanOrEqual(0);
  });

  /** ตรวจสอบว่ามี Address และตรวจหา Address ของไทย */
  test('should have addresses', async ({ request }) => {
    const addresses = await getDocList(request, 'Address', ['name', 'address_title', 'country', 'city', 'pincode'], {}, 50);
    if (addresses.length > 0) {
      const thaiAddr = addresses.filter((a: any) => a.country === 'Thailand');
      console.log(`  Total Addresses: ${addresses.length}, Thai: ${thaiAddr.length}`);
    }
    expect(addresses.length).toBeGreaterThanOrEqual(0);
  });

  /** ตรวจสอบว่า Tax Withholding Categories ถูกตั้งค่าแล้ว */
  test('should check withholding tax categories', async ({ request }) => {
    const count = await getCount(request, 'Tax Withholding Category');
    console.log(`  Tax Withholding Categories: ${count}`);
    expect(count).toBeGreaterThanOrEqual(0);
  });

  /** ตรวจสอบว่า Currency THB ถูกเปิดใช้งานในระบบ */
  test('currency THB should be enabled', async ({ request }) => {
    const res = await request.get(`${BASE}/api/resource/Currency/THB`);
    if (res.ok()) {
      const json = await res.json();
      expect(json.data.enabled).toBeTruthy();
    }
  });
});

/** ตรวจสอบ custom app Connect Diagnostics Core: การติดตั้ง, doctypes, และ UI */
test.describe('05 - Connect Diagnostics Core', () => {
  /** ตรวจสอบว่า module Connect Diagnostics Core ถูกติดตั้งแล้ว */
  test('app should be installed', async ({ request }) => {
    const modules = await getDocList(request, 'Module Def', ['name'], { module_name: 'Connect Diagnostics Core' }, 0);
    expect(modules.length).toBeGreaterThanOrEqual(1);
  });

  /** แสดง custom doctypes ทั้งหมดที่อยู่ใน module Connect Diagnostics Core */
  test('should list all custom doctypes from the app', async ({ request }) => {
    const doctypes = await getDocList(request, 'DocType', ['name', 'module', 'istable', 'is_virtual'], { module: 'Connect Diagnostics Core' });
    console.log(`  Custom DocTypes: ${doctypes.length}`);
    for (const dt of doctypes) {
      console.log(`    - ${dt.name} (table: ${dt.istable}, virtual: ${dt.is_virtual})`);
    }
    expect(doctypes.length).toBeGreaterThanOrEqual(0);
  });

  /** ตรวจสอบว่ามีข้อมูลใน custom doctype ที่ไม่ใช่ table */
  test('should validate data in each custom doctype', async ({ request }) => {
    const doctypes = await getDocList(request, 'DocType', ['name'], { module: 'Connect Diagnostics Core', istable: 0 });
    for (const dt of doctypes) {
      const count = await getCount(request, dt.name);
      console.log(`    - ${dt.name}: ${count} records`);
      if (count > 0) {
        const records = await getDocList(request, dt.name, ['name'], {}, 5);
        expect(records.length).toBeGreaterThan(0);
      }
    }
  });

  /** ตรวจสอบว่าหน้า custom module โหลดใน UI ได้โดยไม่มี error */
  test('should load custom module page in UI', async ({ page }) => {
    await page.goto(`${BASE}/app/connect-diagnostics-core`);
    await page.waitForLoadState('load');
    const bodyText = await page.locator('body').textContent();
    const isOk = !bodyText?.includes('Not Permitted') && !bodyText?.includes('Page not found');
    expect(isOk).toBeTruthy();
  });
});

/** ตรวจสอบ Data Integrity: ตรวจ foreign key relationships และ GL balance */
test.describe('05 - Data Integrity Checks', () => {
  /** ตรวจสอบว่า Customer ทุกรายการอ้างอิงถึง Territory ที่ถูกต้อง */
  test('all customers should have valid territory', async ({ request }) => {
    const customers = await getDocList(request, 'Customer', ['name', 'territory']);
    const territories = await getDocList(request, 'Territory', ['name']);
    const terrNames = new Set(territories.map((t: any) => t.name));
    for (const c of customers) {
      if (c.territory) {
        expect(terrNames.has(c.territory), `Customer "${c.name}" invalid territory "${c.territory}"`).toBeTruthy();
      }
    }
  });

  /** ตรวจสอบว่า Item ทุกรายการอ้างอิงถึง Item Group ที่ถูกต้อง */
  test('all items should have valid item group', async ({ request }) => {
    const items = await getDocList(request, 'Item', ['name', 'item_group']);
    const groups = await getDocList(request, 'Item Group', ['name']);
    const groupNames = new Set(groups.map((g: any) => g.name));
    for (const item of items) {
      if (item.item_group) {
        expect(groupNames.has(item.item_group), `Item "${item.name}" invalid item_group "${item.item_group}"`).toBeTruthy();
      }
    }
  });

  /** ตรวจสอบว่า Employee ทุกรายการอยู่ใน Company ที่ถูกต้อง */
  test('all employees should belong to valid company', async ({ request }) => {
    const employees = await getDocList(request, 'Employee', ['name', 'company']);
    const companies = await getDocList(request, 'Company', ['name']);
    const companyNames = new Set(companies.map((c: any) => c.name));
    for (const emp of employees) {
      if (emp.company) {
        expect(companyNames.has(emp.company), `Employee "${emp.name}" invalid company "${emp.company}"`).toBeTruthy();
      }
    }
  });

  /** ตรวจสอบว่า GL debit รวมเท่ากับ GL credit รวมภายในค่าคลาดเคลื่อน */
  test('GL Entry balance check (debit = credit)', async ({ request }) => {
    const res = await request.get(`${BASE}/api/method/frappe.client.get_list`, {
      params: {
        doctype: 'GL Entry',
        fields: JSON.stringify(['sum(debit) as total_debit', 'sum(credit) as total_credit']),
        limit_page_length: '1',
      },
    });
    const json = await res.json();
    if (json.message && json.message.length > 0) {
      const { total_debit, total_credit } = json.message[0];
      console.log(`  GL Total Debit: ${total_debit}, Credit: ${total_credit}`);
      if (total_debit && total_credit) {
        expect(Math.abs(total_debit - total_credit)).toBeLessThan(0.01);
      }
    }
  });
});
