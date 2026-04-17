import { test, expect } from '@playwright/test';
import { getDocList, getCount, checkRequiredFields } from '../lib/frappe-api';

const BASE = process.env.BASE_URL || 'https://dev.connectdiagnostics.nomeaparadigm.com';

/** ตรวจสอบข้อมูล HR Setup (Department, Designation, Employment Type) */
test.describe('04 - HR Setup', () => {
	/** ตรวจสอบว่า Department มีอย่างน้อย 1 record ในระบบ */
	test('should have departments', async ({ request }) => {
		const count = await getCount(request, 'Department');
		console.log(`  Departments: ${count}`);
		expect(count).toBeGreaterThanOrEqual(1);
	});

	/** ตรวจสอบว่า Designation มีอย่างน้อย 1 record ในระบบ */
	test('should have designations', async ({ request }) => {
		const count = await getCount(request, 'Designation');
		console.log(`  Designations: ${count}`);
		expect(count).toBeGreaterThanOrEqual(1);
	});

	/** ตรวจสอบว่า Employment Type มีอย่างน้อย 1 record ในระบบ */
	test('should have employment types', async ({ request }) => {
		const count = await getCount(request, 'Employment Type');
		console.log(`  Employment Types: ${count}`);
		expect(count).toBeGreaterThanOrEqual(1);
	});

	/** ตรวจสอบว่าหน้า Department list page โหลดได้โดยไม่มี permission error */
	test('department list page loads', async ({ page }) => {
		await page.goto(`${BASE}/app/department`);
		await page.waitForLoadState('load');
		await expect(page.locator('body')).not.toContainText('Not Permitted');
	});
});

/** ตรวจสอบว่า Leave Types มีอยู่และถูกต้อง */
test.describe('04 - Leave Management', () => {
	/** ตรวจสอบว่า Leave Type มีอย่างน้อย 1 record ในระบบ */
	test('should have leave types', async ({ request }) => {
		const count = await getCount(request, 'Leave Type');
		console.log(`  Leave Types: ${count}`);
		expect(count).toBeGreaterThanOrEqual(1);
	});

	/** ตรวจสอบว่า Leave Type ทุกรายการมี leave_type_name กำหนดไว้ */
	test('leave types should have names', async ({ request }) => {
		const types = await getDocList(request, 'Leave Type', ['name', 'leave_type_name']);
		for (const lt of types) {
			expect(lt.leave_type_name).toBeTruthy();
		}
	});

	// TODO: Phase 2 — ตรวจสอบ Leave Allocation
	// test('should validate leave allocations (if any)', async ({ request }) => { ... });

	// TODO: Phase 2 — โหลดหน้า Leave Application
	// test('leave application list page loads', async ({ page }) => { ... });
});

// TODO: Phase 2 — Attendance tests (เปิดเมื่อ CD พร้อม)
// - Attendance record validation
// - Attendance list page load

// TODO: Phase 2 — Payroll tests (เปิดเมื่อ CD พร้อม)
// - Salary Component validation
// - Salary Structure validation
// - Payroll Entry validation
// - Salary Slip page load

// TODO: Phase 2 — Expense Management tests (เปิดเมื่อ CD พร้อม)
// - Expense Claim page load
// - Employee Advance page load
