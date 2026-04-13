const readline = require('readline');
const fs = require('fs');
const path = require('path');
const os = require('os');
const xlsx = require('xlsx');
const https = require('https');

const SQL = path.join(os.homedir(), 'Desktop', 'ERPNext Backups-002', 'rar', '20260413_214731-local-database.sql', '20260413_214731-local-database.sql');
const BASE = 'https://dev.connectdiagnostics.nomeaparadigm.com';

function login() {
  return new Promise((resolve, reject) => {
    const o = { hostname: new URL(BASE).hostname, path: '/api/method/login', method: 'POST', headers: { 'Content-Type': 'application/x-www-form-urlencoded' }, rejectUnauthorized: false };
    const r = https.request(o, (res) => { const c = res.headers['set-cookie'] || []; let d = ''; res.on('data', ch => d += ch); res.on('end', () => { const s = c.find(c => c.includes('sid=')); resolve(s ? s.match(/sid=([^;]+)/)[1] : ''); }); }); r.on('error', reject); r.write('usr=Administrator&pwd=' + process.env.ERP_PASSWORD); r.end();
  });
}
function apiGet(p, sid) {
  return new Promise((resolve, reject) => { https.get(BASE + p, { headers: { Cookie: 'sid=' + sid }, rejectUnauthorized: false }, (res) => { let d = ''; res.on('data', ch => d += ch); res.on('end', () => { try { resolve(JSON.parse(d)); } catch (e) { resolve(null); } }); }); });
}

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

function parse(sql, cols, rows) {
  const m = sql.match(/VALUES\s*\n?\s*/i); if (!m) return;
  const vs = sql.substring(sql.indexOf(m[0]) + m[0].length, sql.length - 2);
  for (const rec of split(vs)) { const f = fields(rec); if (f.length > 0) { const o = {}; for (let i = 0; i < cols.length && i < f.length; i++) o[cols[i]] = f[i]; rows.push(o); } }
}
function split(s) { const r = []; let d = 0, st = 0, q = false; for (let i = 0; i < s.length; i++) { const c = s[i]; if (c === '\\' && q) { i++; continue; } if (c === "'" && !q) q = true; else if (c === "'" && q) { if (i + 1 < s.length && s[i + 1] === "'") { i++; continue; } q = false; continue; } if (!q) { if (c === '(') { if (d === 0) st = i + 1; d++; } if (c === ')') { d--; if (d === 0) r.push(s.substring(st, i)); } } } return r; }
function fields(s) { const f = []; let c = '', q = false; for (let i = 0; i < s.length; i++) { const ch = s[i]; if (ch === '\\' && q) { c += s[i + 1] || ''; i++; continue; } if (ch === "'" && !q) { q = true; continue; } if (ch === "'" && q) { if (i + 1 < s.length && s[i + 1] === "'") { c += "'"; i++; continue; } q = false; continue; } if (q) { c += ch; continue; } if (ch === ',') { f.push(c.trim()); c = ''; continue; } if (ch !== ' ' || c.length > 0) c += ch; } f.push(c.trim()); return f.map(x => x === 'NULL' ? null : x); }
function norm(v) { if (v === null || v === undefined || v === '') return ''; return String(v).trim().replace(/\s{2,}/g, ' '); }

(async () => {
  const sid = await login();
  console.log('Logged in:', !!sid);

  // ===== ITEMS =====
  console.log('\n=== ITEMS ===');
  const sqlItems = await parseTable('tabItem');
  const sqlItemMap = new Map(); for (const r of sqlItems) sqlItemMap.set(r.name, r);

  const p1 = new URLSearchParams(); p1.set('doctype', 'Item'); p1.set('fields', JSON.stringify(['name', 'brand', 'item_name', 'is_stock_item'])); p1.set('filters', JSON.stringify({})); p1.set('limit_page_length', '0');
  const apiItems = (await apiGet('/api/method/frappe.client.get_list?' + p1.toString(), sid)).message || [];
  const apiItemMap = new Map(); for (const r of apiItems) apiItemMap.set(r.name, r);

  console.log('SQL Items:', sqlItems.length, '| API Items:', apiItems.length);

  let sqlOnlyBrand = 0, apiOnlyBrand = 0, bothBrand = 0;
  const diffBrands = [];
  for (const [id, sql] of sqlItemMap) {
    const api = apiItemMap.get(id);
    if (!api) continue;
    const sb = norm(sql.brand), ab = norm(api.brand);
    if (sb === '' && ab === '') bothBrand++;
    else if (sb === '' && ab !== '') { apiOnlyBrand++; }
    else if (sb !== '' && ab === '') { sqlOnlyBrand++; }
    else if (sb !== ab) diffBrands.push({ id, sql: sb, api: ab });
  }
  console.log('Brand both empty:', bothBrand);
  console.log('Brand SQL only (null in API):', sqlOnlyBrand);
  console.log('Brand API only (null in SQL):', apiOnlyBrand);
  console.log('Brand different:', diffBrands.length);

  // ===== ACCOUNTS =====
  console.log('\n=== ACCOUNTS (CD only) ===');
  const sqlAcc = await parseTable('tabAccount');
  const sqlAccCD = sqlAcc.filter(r => norm(r.company).toLowerCase().includes('connect'));
  const sqlAccMap = new Map(); for (const r of sqlAccCD) sqlAccMap.set(r.name, r);

  const p2 = new URLSearchParams(); p2.set('doctype', 'Account'); p2.set('fields', JSON.stringify(['name', 'account_number', 'account_type', 'root_type', 'company'])); p2.set('filters', JSON.stringify({ company: 'Connect Diagnostics' })); p2.set('limit_page_length', '0');
  const apiAcc = (await apiGet('/api/method/frappe.client.get_list?' + p2.toString(), sid)).message || [];
  const apiAccMap = new Map(); for (const r of apiAcc) apiAccMap.set(r.name, r);

  console.log('SQL Accounts (CD):', sqlAccCD.length, '| API Accounts (CD):', apiAcc.length);

  let typeMatch = 0, typeSqlEmpty = 0, typeApiEmpty = 0, typeDiff = 0;
  for (const [name, sql] of sqlAccMap) {
    const api = apiAccMap.get(name);
    if (!api) continue;
    const st = norm(sql.account_type), at = norm(api.account_type);
    if (st === '' && at === '') typeMatch++;
    else if (st === '' && at !== '') { typeSqlEmpty++; }
    else if (st !== '' && at === '') { typeApiEmpty++; }
    else if (st.toLowerCase() !== at.toLowerCase()) typeDiff++;
  }
  console.log('Type both empty:', typeMatch);
  console.log('Type SQL empty, API has value:', typeSqlEmpty);
  console.log('Type SQL has value, API empty:', typeApiEmpty);
  console.log('Type different:', typeDiff);

  // ===== CUSTOMERS =====
  console.log('\n=== CUSTOMERS ===');
  const sqlCust = await parseTable('tabCustomer');
  const sqlCustMap = new Map(); for (const r of sqlCust) sqlCustMap.set(r.name, r);
  const p3 = new URLSearchParams(); p3.set('doctype', 'Customer'); p3.set('fields', JSON.stringify(['name', 'customer_group'])); p3.set('filters', JSON.stringify({})); p3.set('limit_page_length', '0');
  const apiCust = (await apiGet('/api/method/frappe.client.get_list?' + p3.toString(), sid)).message || [];
  const apiCustMap = new Map(); for (const r of apiCust) apiCustMap.set(r.name, r);

  console.log('SQL Customers:', sqlCust.length, '| API Customers:', apiCust.length);
  let sqlCustNoGroup = 0, apiCustNoGroup = 0;
  for (const [id, r] of sqlCustMap) { if (!norm(r.customer_group)) sqlCustNoGroup++; }
  for (const [id, r] of apiCustMap) { if (!norm(r.customer_group)) apiCustNoGroup++; }
  console.log('SQL missing customer_group:', sqlCustNoGroup, '| API missing customer_group:', apiCustNoGroup);

  // ===== EMPLOYEES =====
  console.log('\n=== EMPLOYEES ===');
  const sqlEmp = await parseTable('tabEmployee');
  const p4 = new URLSearchParams(); p4.set('doctype', 'Employee'); p4.set('fields', JSON.stringify(['name', 'employee_name'])); p4.set('filters', JSON.stringify({})); p4.set('limit_page_length', '0');
  const apiEmp = (await apiGet('/api/method/frappe.client.get_list?' + p4.toString(), sid)).message || [];
  console.log('SQL Employees:', sqlEmp.length, '| API Employees:', apiEmp.length);

  const sqlEmpIds = new Set(sqlEmp.map(r => r.name));
  const apiEmpIds = new Set(apiEmp.map(r => r.name));
  for (const id of sqlEmpIds) { if (!apiEmpIds.has(id)) console.log('  In SQL, not in API:', id); }
  for (const id of apiEmpIds) { if (!sqlEmpIds.has(id)) console.log('  In API, not in SQL:', id); }

  // ===== SUPPLIERS =====
  console.log('\n=== SUPPLIERS ===');
  const sqlSup = await parseTable('tabSupplier');
  const p5 = new URLSearchParams(); p5.set('doctype', 'Supplier'); p5.set('fields', JSON.stringify(['name'])); p5.set('filters', JSON.stringify({})); p5.set('limit_page_length', '0');
  const apiSup = (await apiGet('/api/method/frappe.client.get_list?' + p5.toString(), sid)).message || [];
  console.log('SQL Suppliers:', sqlSup.length, '| API Suppliers:', apiSup.length);

  // ===== FINAL COMPARISON =====
  console.log('\n========================================');
  console.log('SQL vs API vs Excel');
  console.log('========================================');
  console.log('Items:       SQL=' + sqlItems.length + ' API=' + apiItems.length + ' (brand null in SQL=' + sqlOnlyBrand + ', in API=' + apiOnlyBrand + ')');
  console.log('Accounts:    SQL=' + sqlAccCD.length + ' API=' + apiAcc.length + ' (type empty in SQL=' + typeSqlEmpty + ', API added=' + typeSqlEmpty + ')');
  console.log('Customers:   SQL=' + sqlCust.length + ' API=' + apiCust.length + ' (no group in SQL=' + sqlCustNoGroup + ', API=' + apiCustNoGroup + ')');
  console.log('Employees:   SQL=' + sqlEmp.length + ' API=' + apiEmp.length);
  console.log('Suppliers:   SQL=' + sqlSup.length + ' API=' + apiSup.length);

  process.exit(0);
})();
