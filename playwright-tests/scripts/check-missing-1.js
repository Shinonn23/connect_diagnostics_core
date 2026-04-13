const readline = require('readline');
const fs = require('fs');
const path = require('path');
const os = require('os');
const xlsx = require('xlsx');
const https = require('https');

const SQL = path.join(os.homedir(), 'Desktop', 'ERPNext Backups-002', 'rar', '20260413_214731-local-database.sql', '20260413_214731-local-database.sql');
const BASE = 'https://dev.connectdiagnostics.nomeaparadigm.com';
function login() { return new Promise((resolve, reject) => { const o = { hostname: new URL(BASE).hostname, path: '/api/method/login', method: 'POST', headers: { 'Content-Type': 'application/x-www-form-urlencoded' }, rejectUnauthorized: false }; const r = https.request(o, (res) => { const c = res.headers['set-cookie'] || []; let d = ''; res.on('data', ch => d += ch); res.on('end', () => { const s = c.find(c => c.includes('sid=')); resolve(s ? s.match(/sid=([^;]+)/)[1] : ''); }); }); r.on('error', reject); r.write('usr=Administrator&pwd=' + process.env.ERP_PASSWORD); r.end(); }); }
function apiGet(p, sid) { return new Promise((resolve, reject) => { https.get(BASE + p, { headers: { Cookie: 'sid=' + sid }, rejectUnauthorized: false }, (res) => { let d = ''; res.on('data', ch => d += ch); res.on('end', () => { try { resolve(JSON.parse(d)); } catch (e) { resolve(null); } }); }); }); }
function norm(v) { if (v === null || v === undefined || v === '') return ''; return String(v).trim(); }

async function parseTable(name) {
  return new Promise((resolve) => {
    const cols = [], rows = [];
    let inC = false, inI = false, buf = '';
    const rl = readline.createInterface({ input: fs.createReadStream(SQL) });
    rl.on('line', (l) => {
      const t = l.trim();
      if (t.startsWith('-- Table structure for table `' + name + '`')) { inC = true; return; }
      if (inC && t.startsWith('CREATE TABLE')) return;
      if (inC && t.startsWith('`')) { const m = t.match(/^`(\w+)`/); if (m) cols.push(m[1]); return; }
      if (inC && (t === ')' || t.startsWith(')'))) { inC = false; return; }
      if (t.startsWith('INSERT INTO `' + name + '`')) { inI = true; buf = t; if (t.endsWith(';')) { inI = false; parse(buf, cols, rows); } return; }
      if (inI) { buf += '\n' + t; if (t.endsWith(';')) { inI = false; parse(buf, cols, rows); } return; }
      if (t.startsWith('-- Table structure for table') && cols.length > 0) rl.close();
    });
    rl.on('close', () => resolve(rows));
  });
}
function parse(sql, cols, rows) { const m = sql.match(/VALUES\s*\n?\s*/i); if (!m) return; const vs = sql.substring(sql.indexOf(m[0]) + m[0].length, sql.length - 2); for (const rec of split(vs)) { const f = fields(rec); if (f.length > 0) { const o = {}; for (let i = 0; i < cols.length && i < f.length; i++) o[cols[i]] = f[i]; rows.push(o); } } }
function split(s) { const r = []; let d = 0, st = 0, q = false; for (let i = 0; i < s.length; i++) { const c = s[i]; if (c === '\\' && q) { i++; continue; } if (c === "'" && !q) q = true; else if (c === "'" && q) { if (i + 1 < s.length && s[i + 1] === "'") { i++; continue; } q = false; continue; } if (!q) { if (c === '(') { if (d === 0) st = i + 1; d++; } if (c === ')') { d--; if (d === 0) r.push(s.substring(st, i)); } } } return r; }
function fields(s) { const f = []; let c = '', q = false; for (let i = 0; i < s.length; i++) { const ch = s[i]; if (ch === '\\' && q) { c += s[i + 1] || ''; i++; continue; } if (ch === "'" && !q) { q = true; continue; } if (ch === "'" && q) { if (i + 1 < s.length && s[i + 1] === "'") { c += "'"; i++; continue; } q = false; continue; } if (q) { c += ch; continue; } if (ch === ',') { f.push(c.trim()); c = ''; continue; } if (ch !== ' ' || c.length > 0) c += ch; } f.push(c.trim()); return f.map(x => x === 'NULL' ? null : x); }

(async () => {
  const sid = await login();
  const dir = path.join(os.homedir(), 'Desktop');
  const files = fs.readdirSync(dir);
  const wb = xlsx.readFile(path.join(dir, files.find(f => f.startsWith('CD-ERPNext') && f.includes('v.3') && f.endsWith('.xlsx'))));

  // ===== ITEMS =====
  console.log('=== ITEMS: ขาดใน SQL แต่มีใน API ===');
  const sqlItems = await parseTable('tabItem');
  const sqlItemSet = new Set(sqlItems.map(r => r.name));
  const p1 = new URLSearchParams(); p1.set('doctype', 'Item'); p1.set('fields', JSON.stringify(['name', 'item_name'])); p1.set('filters', JSON.stringify({})); p1.set('limit_page_length', '0');
  const apiItems = (await apiGet('/api/method/frappe.client.get_list?' + p1.toString(), sid)).message || [];
  for (const r of apiItems) { if (!sqlItemSet.has(r.name)) console.log('  API extra:', r.name, r.item_name); }
  const exItems = xlsx.utils.sheet_to_json(wb.Sheets['Items'], { defval: '', raw: false });
  for (const row of exItems) { const id = norm(row['ID']); if (id && !sqlItemSet.has(id)) console.log('  Excel missing in SQL:', id, row['Item Name (40 Char)']); }

  // ===== CUSTOMERS =====
  console.log('\n=== CUSTOMERS: ขาดใน SQL แต่มีใน API ===');
  const sqlCust = await parseTable('tabCustomer');
  const sqlCustSet = new Set(sqlCust.map(r => r.name));
  const p2 = new URLSearchParams(); p2.set('doctype', 'Customer'); p2.set('fields', JSON.stringify(['name', 'customer_name'])); p2.set('filters', JSON.stringify({})); p2.set('limit_page_length', '0');
  const apiCust = (await apiGet('/api/method/frappe.client.get_list?' + p2.toString(), sid)).message || [];
  for (const r of apiCust) { if (!sqlCustSet.has(r.name)) console.log('  API extra:', r.name, r.customer_name); }
  const exCust = xlsx.utils.sheet_to_json(wb.Sheets['Customers'], { defval: '', raw: false });
  for (const row of exCust) { const id = norm(row['ID']); if (id && !sqlCustSet.has(id)) console.log('  Excel missing in SQL:', id, row['Customer Name']); }

  // ===== EMPLOYEES =====
  console.log('\n=== EMPLOYEES: ขาดใน SQL แต่มีใน API ===');
  const sqlEmp = await parseTable('tabEmployee');
  const sqlEmpSet = new Set(sqlEmp.map(r => r.name));
  const p3 = new URLSearchParams(); p3.set('doctype', 'Employee'); p3.set('fields', JSON.stringify(['name', 'employee_name'])); p3.set('filters', JSON.stringify({})); p3.set('limit_page_length', '0');
  const apiEmp = (await apiGet('/api/method/frappe.client.get_list?' + p3.toString(), sid)).message || [];
  for (const r of apiEmp) { if (!sqlEmpSet.has(r.name)) console.log('  API extra:', r.name, r.employee_name); }
  for (const r of apiEmp) { if (sqlEmpSet.has(r.name)) sqlEmpSet.delete(r.name); }
  for (const id of sqlEmpSet) console.log('  SQL extra (not in API):', id);
  const exEmp = xlsx.utils.sheet_to_json(wb.Sheets['Employees'], { defval: '', raw: false });
  for (const row of exEmp) { const id = norm(row['EmployeeID']); const nonKey = Object.entries(row).filter(([k]) => k !== 'EmployeeID').every(([, v]) => v === null || v === undefined || v === ''); if (nonKey) continue; if (id && !apiEmp.map(r => r.name).includes(id)) console.log('  Excel missing in API:', id, row['EmployeeNameEN']); }

  // ===== SUPPLIERS =====
  console.log('\n=== SUPPLIERS: ขาดใน SQL แต่มีใน API ===');
  const sqlSup = await parseTable('tabSupplier');
  const sqlSupSet = new Set(sqlSup.map(r => r.name));
  const p4 = new URLSearchParams(); p4.set('doctype', 'Supplier'); p4.set('fields', JSON.stringify(['name', 'supplier_name'])); p4.set('filters', JSON.stringify({})); p4.set('limit_page_length', '0');
  const apiSup = (await apiGet('/api/method/frappe.client.get_list?' + p4.toString(), sid)).message || [];
  for (const r of apiSup) { if (!sqlSupSet.has(r.name)) console.log('  API extra:', r.name, r.supplier_name); }
  const exSup = xlsx.utils.sheet_to_json(wb.Sheets['Suppliers'], { defval: '', raw: false });
  for (const row of exSup) { const id = norm(row['CD ID']) || norm(row['Supplier Name']); if (id && !sqlSupSet.has(id)) console.log('  Excel missing in SQL:', id, row['Supplier Name']); }

  process.exit(0);
})();
