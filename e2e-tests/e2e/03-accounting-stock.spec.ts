import { test, expect } from '@playwright/test';
import { getDocList, getCount, checkRequiredFields } from '../lib/frappe-api';

const BASE = process.env.BASE_URL || 'https://dev.connectdiagnostics.nomeaparadigm.com';

/** ตรวจสอบการตั้งค่า Accounting ที่จำเป็น (Fiscal Year, Cost Center, Currency) */
test.describe('03 - Accounting Settings', () => {
	/** ตรวจสอบว่า Fiscal Year มีอย่างน้อย 1 record ในระบบ */
	test('fiscal year should exist', async ({ request }) => {
		const count = await getCount(request, 'Fiscal Year');
		console.log(`  Fiscal Years: ${count}`);
		expect(count).toBeGreaterThanOrEqual(1);
	});

	/** ตรวจสอบว่า Fiscal Year ปัจจุบันมี status active (disabled=0) */
	test('current fiscal year should be active', async ({ request }) => {
		const fy = await getDocList(request, 'Fiscal Year', ['name', 'year_start_date', 'year_end_date', 'disabled'], { disabled: 0 });
		expect(fy.length).toBeGreaterThanOrEqual(1);
		console.log(`  Active FY: ${fy.map((f: any) => f.name).join(', ')}`);
	});

	/** ตรวจสอบว่า Cost Center มีอย่างน้อย 1 record ในระบบ */
	test('cost center should exist', async ({ request }) => {
		const count = await getCount(request, 'Cost Center');
		console.log(`  Cost Centers: ${count}`);
		expect(count).toBeGreaterThanOrEqual(1);
	});

	/** ตรวจสอบว่า Currency ที่ enabled มีอย่างน้อย 1 สกุลเงิน */
	test('enabled currencies exist', async ({ request }) => {
		const currencies = await getDocList(request, 'Currency', ['name', 'enabled'], { enabled: 1 });
		console.log(`  Enabled Currencies: ${currencies.length}`);
		expect(currencies.length).toBeGreaterThanOrEqual(1);
	});
});

/** ตรวจสอบการตั้งค่า Stock (UOM) และหน้า stock-related โหลดได้ถูกต้อง */
test.describe('03 - Stock', () => {
	/** ตรวจสอบว่า UOM (Unit of Measure) มีอย่างน้อย 1 record ในระบบ */
	test('should have UOM defined', async ({ request }) => {
		const count = await getCount(request, 'UOM');
		console.log(`  UOMs: ${count}`);
		expect(count).toBeGreaterThan(0);
	});

	// TODO: Phase 2 — CD ยังไม่ได้ให้ข้อมูล Stock Entry, เปิดเมื่อพร้อม
	// test('should validate stock entries (if any)', async ({ request }) => {
	//   const count = await getCount(request, 'Stock Entry');
	//   console.log(`  Stock Entries: ${count}`);
	//   if (count > 0) {
	//     const entries = await getDocList(request, 'Stock Entry', ['name', 'stock_entry_type', 'posting_date', 'company', 'docstatus']);
	//     for (const se of entries) {
	//       const missing = checkRequiredFields(se, ['stock_entry_type', 'posting_date', 'company']);
	//       expect(missing, `SE "${se.name}" missing: ${JSON.stringify(missing)}`).toHaveLength(0);
	//     }
	//   }
	//   expect(count).toBeGreaterThanOrEqual(0);
	// });

	// TODO: Phase 2 — เปิดการทดสอบหน้า Stock Entry เมื่อมีข้อมูลพร้อม
	// test('stock entry list page loads', async ({ page }) => {
	//   await page.goto(`${BASE}/app/stock-entry`);
	//   await page.waitForLoadState('load');
	//   await expect(page.locator('body')).not.toContainText('Not Permitted');
	// });

	/** ตรวจสอบว่าหน้า Stock Ledger Report โหลดได้โดยไม่มี permission error */
	test('stock ledger report loads', async ({ page }) => {
		await page.goto(`${BASE}/app/query-report/Stock Ledger`);
		await page.waitForLoadState('load');
		await expect(page.locator('body')).not.toContainText('Not Permitted');
	});
});

// TODO: Phase 2 — Transaction tests (เปิดเมื่อ CD พร้อม)
// - Sales Order validation + page load
// - Sales Invoice validation + page load
// - Purchase Order validation + page load
// - Purchase Invoice validation + page load
// - Payment Entry validation
// - Journal Entry validation
// - Quotation / Delivery Note / Purchase Receipt page loads
