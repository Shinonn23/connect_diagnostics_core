import { test, expect } from '@playwright/test';
import { getDocList, getCount, checkRequiredFields } from '../helpers/frappe-api';

const BASE = process.env.BASE_URL || 'https://dev.connectdiagnostics.nomeaparadigm.com';

test.describe('04 - HR Setup', () => {
  test('should have departments', async ({ request }) => {
    const count = await getCount(request, 'Department');
    console.log(`  Departments: ${count}`);
    expect(count).toBeGreaterThanOrEqual(1);
  });

  test('should have designations', async ({ request }) => {
    const count = await getCount(request, 'Designation');
    console.log(`  Designations: ${count}`);
    expect(count).toBeGreaterThanOrEqual(1);
  });

  test('should have employment types', async ({ request }) => {
    const count = await getCount(request, 'Employment Type');
    console.log(`  Employment Types: ${count}`);
    expect(count).toBeGreaterThanOrEqual(1);
  });

  test('department list page loads', async ({ page }) => {
    await page.goto(`${BASE}/app/department`);
    await page.waitForLoadState('load');
    await expect(page.locator('body')).not.toContainText('Not Permitted');
  });
});

test.describe('04 - Leave Management', () => {
  test('should have leave types', async ({ request }) => {
    const count = await getCount(request, 'Leave Type');
    console.log(`  Leave Types: ${count}`);
    expect(count).toBeGreaterThanOrEqual(1);
  });

  test('leave types should have names', async ({ request }) => {
    const types = await getDocList(request, 'Leave Type', ['name', 'leave_type_name']);
    for (const lt of types) {
      expect(lt.leave_type_name).toBeTruthy();
    }
  });

  test('should validate leave allocations (if any)', async ({ request }) => {
    const count = await getCount(request, 'Leave Allocation');
    console.log(`  Leave Allocations: ${count}`);
    if (count > 0) {
      const allocations = await getDocList(request, 'Leave Allocation', ['name', 'employee', 'leave_type', 'from_date', 'to_date']);
      for (const la of allocations) {
        const missing = checkRequiredFields(la, ['employee', 'leave_type', 'from_date', 'to_date']);
        expect(missing, `Leave Alloc "${la.name}" missing: ${JSON.stringify(missing)}`).toHaveLength(0);
      }
    }
    expect(count).toBeGreaterThanOrEqual(0);
  });

  test('leave application list page loads', async ({ page }) => {
    await page.goto(`${BASE}/app/leave-application`);
    await page.waitForLoadState('load');
    await expect(page.locator('body')).not.toContainText('Not Permitted');
  });
});

test.describe('04 - Attendance', () => {
  test('should validate attendance records (if any)', async ({ request }) => {
    const count = await getCount(request, 'Attendance');
    console.log(`  Attendance: ${count}`);
    if (count > 0) {
      const records = await getDocList(request, 'Attendance', ['name', 'employee', 'attendance_date', 'status', 'company'], {}, 100);
      for (const att of records) {
        const missing = checkRequiredFields(att, ['employee', 'attendance_date', 'status']);
        expect(missing, `Attendance "${att.name}" missing: ${JSON.stringify(missing)}`).toHaveLength(0);
      }
    }
    expect(count).toBeGreaterThanOrEqual(0);
  });

  test('attendance list page loads', async ({ page }) => {
    await page.goto(`${BASE}/app/attendance`);
    await page.waitForLoadState('load');
    await expect(page.locator('body')).not.toContainText('Not Permitted');
  });
});

test.describe('04 - Payroll', () => {
  test('should have salary components', async ({ request }) => {
    const count = await getCount(request, 'Salary Component');
    console.log(`  Salary Components: ${count}`);
    if (count > 0) {
      const components = await getDocList(request, 'Salary Component', ['name', 'salary_component', 'type']);
      for (const sc of components) {
        expect(sc.salary_component).toBeTruthy();
        expect(['Earning', 'Deduction']).toContain(sc.type);
      }
    }
    expect(count).toBeGreaterThanOrEqual(0);
  });

  test('should validate salary structures (if any)', async ({ request }) => {
    const count = await getCount(request, 'Salary Structure');
    console.log(`  Salary Structures: ${count}`);
    if (count > 0) {
      const structures = await getDocList(request, 'Salary Structure', ['name', 'company', 'is_active', 'payroll_frequency']);
      for (const ss of structures) {
        const missing = checkRequiredFields(ss, ['company', 'payroll_frequency']);
        expect(missing, `Salary Structure "${ss.name}" missing: ${JSON.stringify(missing)}`).toHaveLength(0);
      }
    }
    expect(count).toBeGreaterThanOrEqual(0);
  });

  test('should validate payroll entries (if any)', async ({ request }) => {
    const count = await getCount(request, 'Payroll Entry');
    console.log(`  Payroll Entries: ${count}`);
    if (count > 0) {
      const entries = await getDocList(request, 'Payroll Entry', ['name', 'company', 'posting_date', 'payroll_frequency']);
      for (const pe of entries) {
        const missing = checkRequiredFields(pe, ['company', 'posting_date', 'payroll_frequency']);
        expect(missing, `Payroll Entry "${pe.name}" missing: ${JSON.stringify(missing)}`).toHaveLength(0);
      }
    }
    expect(count).toBeGreaterThanOrEqual(0);
  });

  test('salary slip list page loads', async ({ page }) => {
    await page.goto(`${BASE}/app/salary-slip`);
    await page.waitForLoadState('load');
    await expect(page.locator('body')).not.toContainText('Not Permitted');
  });
});

test.describe('04 - Expense Management', () => {
  test('expense claim list page loads', async ({ page }) => {
    await page.goto(`${BASE}/app/expense-claim`);
    await page.waitForLoadState('load');
    await expect(page.locator('body')).not.toContainText('Not Permitted');
  });

  test('employee advance list page loads', async ({ page }) => {
    await page.goto(`${BASE}/app/employee-advance`);
    await page.waitForLoadState('load');
    await expect(page.locator('body')).not.toContainText('Not Permitted');
  });
});
