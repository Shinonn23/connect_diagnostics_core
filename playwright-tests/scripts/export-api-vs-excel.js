const https = require('https');
const xlsx = require('xlsx');
const path = require('path');
const os = require('os');
const fs = require('fs');

const BASE = 'https://dev.connectdiagnostics.nomeaparadigm.com';
function login() { return new Promise((resolve, reject) => { const o = { hostname: new URL(BASE).hostname, path: '/api/method/login', method: 'POST', headers: { 'Content-Type': 'application/x-www-form-urlencoded' }, rejectUnauthorized: false }; const r = https.request(o, (res) => { const c = res.headers['set-cookie'] || []; let d = ''; res.on('data', ch => d += ch); res.on('end', () => { const s = c.find(c => c.includes('sid=')); resolve(s ? s.match(/sid=([^;]+)/)[1] : ''); }); }); r.on('error', reject); r.write('usr=Administrator&pwd=' + process.env.ERP_PASSWORD); r.end(); }); }
function apiGet(p, sid) { return new Promise((resolve, reject) => { https.get(BASE + p, { headers: { Cookie: 'sid=' + sid }, rejectUnauthorized: false }, (res) => { let d = ''; res.on('data', ch => d += ch); res.on('end', () => { try { resolve(JSON.parse(d)); } catch (e) { resolve(null); } }); }); }); }
function norm(v) { if (v === null || v === undefined || v === '') return ''; return String(v).trim().replace(/\s{2,}/g, ' '); }
function stripCd(v) { return v.replace(/\s*-\s*CD\s*$/, '').trim(); }

function findExcelDir() {
  const dirs = [path.join(__dirname, '..', 'data'), path.join(os.homedir(), 'Desktop')];
  for (const d of dirs) { if (fs.existsSync(d)) { const f = fs.readdirSync(d).find(f => f.startsWith('CD-ERPNext') && f.includes('v.3') && f.endsWith('.xlsx')); if (f) return d; } }
  throw new Error('Cannot find CD-ERPNext Excel file in data/ or Desktop');
}

(async () => {
  const sid = await login();
  const dir = findExcelDir();
  const files = fs.readdirSync(dir);
  const match = files.find(f => f.startsWith('CD-ERPNext') && f.includes('v.3') && f.endsWith('.xlsx'));
  const wb = xlsx.readFile(path.join(dir, match));
  console.log('Excel:', match);

  const wbOut = xlsx.utils.book_new();
  const summaryRows = [];

  // ===== ITEMS =====
  console.log('Items...');
  const p1 = new URLSearchParams(); p1.set('doctype', 'Item'); p1.set('fields', JSON.stringify(['name', 'item_name', 'brand', 'is_stock_item'])); p1.set('filters', JSON.stringify({})); p1.set('limit_page_length', '0');
  const apiItems = (await apiGet('/api/method/frappe.client.get_list?' + p1.toString(), sid)).message || [];
  const apiItemMap = new Map(); for (const r of apiItems) apiItemMap.set(r.name, r);
  const exItems = xlsx.utils.sheet_to_json(wb.Sheets['Items'], { defval: '', raw: false });

  const itemRows = [];
  let itemMiss = 0;
  for (const row of exItems) {
    const id = String(row['ID'] || '').trim();
    if (!id) continue;
    const api = apiItemMap.get(id);
    if (!api) { itemMiss++; continue; }
    const exBrand = norm(row['Brand']);
    if (exBrand !== '' && norm(api.brand) === '') {
      itemRows.push({ ID: id, 'Item Name': (api.item_name || '').substring(0, 50), 'Brand (Excel)': exBrand, 'Brand (API)': 'null' });
    }
  }
  if (itemRows.length > 0) { xlsx.utils.book_append_sheet(wbOut, xlsx.utils.json_to_sheet(itemRows), 'Items - Brand Missing'); }
  summaryRows.push({ Sheet: 'Items', 'Excel Count': exItems.length, 'API Count': apiItems.length, 'Missing in API': itemMiss, 'Issues': itemRows.length, Note: 'brand=null' });

  // ===== ACCOUNTS =====
  console.log('Accounts...');
  const p2 = new URLSearchParams(); p2.set('doctype', 'Account'); p2.set('fields', JSON.stringify(['name', 'account_number', 'account_name', 'account_type', 'root_type', 'is_group'])); p2.set('filters', JSON.stringify({ company: 'Connect Diagnostics' })); p2.set('limit_page_length', '0');
  const apiAcc = (await apiGet('/api/method/frappe.client.get_list?' + p2.toString(), sid)).message || [];
  const apiAccNum = new Map(); for (const r of apiAcc) { const num = (r.account_number || '').trim(); if (num) apiAccNum.set(num, r); }
  const exAcc = xlsx.utils.sheet_to_json(wb.Sheets['Accounts New'], { defval: '', raw: false });

  const emptyType = [], realMismatch = [], namingDiff = [];
  for (const row of exAcc) {
    const num = String(row['Account Number'] || '').trim();
    const api = apiAccNum.get(num);
    if (!api) continue;
    const exType = norm(row['Account Type']);
    const apType = norm(api.account_type);
    if (exType === '') continue;
    if (apType === '') {
      emptyType.push({ 'Account Number': num, 'Account Name': row['Account Name'], 'Type (Excel)': exType, 'Type (API)': '(empty)', Category: 'EMPTY' });
    } else if (exType.toLowerCase() !== apType.toLowerCase()) {
      if (apType.toLowerCase().includes(exType.toLowerCase()) || exType.toLowerCase().includes(apType.toLowerCase())) {
        namingDiff.push({ 'Account Number': num, 'Account Name': row['Account Name'], 'Type (Excel)': exType, 'Type (API)': apType, Category: 'NAMING' });
      } else {
        realMismatch.push({ 'Account Number': num, 'Account Name': row['Account Name'], 'Type (Excel)': exType, 'Type (API)': apType, Category: 'MISMATCH' });
      }
    }
  }

  const allAcc = [...emptyType, ...realMismatch, ...namingDiff];
  if (allAcc.length > 0) { xlsx.utils.book_append_sheet(wbOut, xlsx.utils.json_to_sheet(allAcc), 'Accounts - Issues'); }
  summaryRows.push({ Sheet: 'Accounts', 'Excel Count': exAcc.length, 'API Count': apiAcc.length, 'Missing in API': 0, 'Issues': emptyType.length + realMismatch.length, Note: 'empty=' + emptyType.length + ', mismatch=' + realMismatch.length + ', naming=' + namingDiff.length });

  // ===== CUSTOMERS =====
  console.log('Customers...');
  const p3 = new URLSearchParams(); p3.set('doctype', 'Customer'); p3.set('fields', JSON.stringify(['name', 'customer_name', 'customer_group'])); p3.set('filters', JSON.stringify({})); p3.set('limit_page_length', '0');
  const apiCust = (await apiGet('/api/method/frappe.client.get_list?' + p3.toString(), sid)).message || [];
  const apiCustMap = new Map(); for (const r of apiCust) apiCustMap.set(r.name, r);
  const exCust = xlsx.utils.sheet_to_json(wb.Sheets['Customers'], { defval: '', raw: false });

  const custRows = [];
  let custMiss = 0;
  for (const row of exCust) {
    const keys = [String(row['ID'] || '').trim(), String(row['Customer Name'] || '').trim()];
    let api = null, usedKey = '';
    for (const k of keys) { if (k && apiCustMap.has(k)) { api = apiCustMap.get(k); usedKey = k; break; } }
    if (!api) { if (keys[0]) { custMiss++; } continue; }
    if (!api.customer_group || norm(api.customer_group) === '') {
      custRows.push({ ID: usedKey, 'Customer Name': (api.customer_name || '').substring(0, 40), 'Customer Group (Excel)': row['Customer Group'] || '', 'Customer Group (API)': '(empty)' });
    }
  }
  if (custRows.length > 0) { xlsx.utils.book_append_sheet(wbOut, xlsx.utils.json_to_sheet(custRows), 'Customers - No Group'); }
  summaryRows.push({ Sheet: 'Customers', 'Excel Count': exCust.length, 'API Count': apiCust.length, 'Missing in API': custMiss, 'Issues': custRows.length, Note: 'missing customer_group' });

  // ===== EMPLOYEES =====
  console.log('Employees...');
  const p4 = new URLSearchParams(); p4.set('doctype', 'Employee'); p4.set('fields', JSON.stringify(['name', 'employee_name'])); p4.set('filters', JSON.stringify({})); p4.set('limit_page_length', '0');
  const apiEmp = (await apiGet('/api/method/frappe.client.get_list?' + p4.toString(), sid)).message || [];
  const apiEmpMap = new Map(); for (const r of apiEmp) apiEmpMap.set(r.name, r);
  const exEmp = xlsx.utils.sheet_to_json(wb.Sheets['Employees'], { defval: '', raw: false });
  let empMiss = 0;
  for (const row of exEmp) {
    const id = String(row['EmployeeID'] || '').trim();
    if (!id) continue;
    const nonKey = Object.entries(row).filter(([k]) => k !== 'EmployeeID').every(([, v]) => v === null || v === undefined || v === '');
    if (nonKey) continue;
    if (!apiEmpMap.has(id)) empMiss++;
  }
  summaryRows.push({ Sheet: 'Employees', 'Excel Count': exEmp.length, 'API Count': apiEmp.length, 'Missing in API': empMiss, 'Issues': empMiss, Note: empMiss > 0 ? 'missing in API' : 'all matched' });

  // ===== SUPPLIERS =====
  console.log('Suppliers...');
  const p5 = new URLSearchParams(); p5.set('doctype', 'Supplier'); p5.set('fields', JSON.stringify(['name'])); p5.set('filters', JSON.stringify({})); p5.set('limit_page_length', '0');
  const apiSup = (await apiGet('/api/method/frappe.client.get_list?' + p5.toString(), sid)).message || [];
  const apiSupMap = new Map(); for (const r of apiSup) apiSupMap.set(r.name, r);
  const exSup = xlsx.utils.sheet_to_json(wb.Sheets['Suppliers'], { defval: '', raw: false });
  let supMiss = 0;
  for (const row of exSup) {
    const keys = [String(row['CD ID'] || '').trim(), String(row['Supplier Name'] || '').trim()];
    let found = false;
    for (const k of keys) { if (k && apiSupMap.has(k)) { found = true; break; } }
    if (!found && keys.some(k => k)) supMiss++;
  }
  summaryRows.push({ Sheet: 'Suppliers', 'Excel Count': exSup.length, 'API Count': apiSup.length, 'Missing in API': supMiss, 'Issues': supMiss, Note: supMiss > 0 ? 'missing in API' : 'all matched' });

  // ===== Summary =====
  xlsx.utils.book_append_sheet(wbOut, xlsx.utils.json_to_sheet(summaryRows), 'Summary');
  const outFile = path.join(dir, 'CD-ERPNext Validation Results.xlsx');
  xlsx.writeFile(wbOut, outFile);

  console.log('\n========================================');
  console.log('Exported:', outFile);
  console.log('========================================');
  for (const s of summaryRows) console.log('  ' + JSON.stringify(s));
  process.exit(0);
})();
