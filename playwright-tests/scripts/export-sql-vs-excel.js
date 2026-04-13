const readline = require('readline');
const fs = require('fs');
const path = require('path');
const os = require('os');
const xlsx = require('xlsx');

const SQL_PATH = path.join(
  os.homedir(), 'Desktop', 'ERPNext Backups-002', 'rar',
  '20260413_214731-local-database.sql', '20260413_214731-local-database.sql'
);
const EXCEL_DIR = path.join(os.homedir(), 'Desktop');

function findExcel() {
  const files = fs.readdirSync(EXCEL_DIR);
  return path.join(EXCEL_DIR, files.find(f => f.startsWith('CD-ERPNext') && f.includes('v.3') && f.endsWith('.xlsx')));
}

async function parseSqlTable(sqlPath, tableName) {
  return new Promise((resolve, reject) => {
    const columns = [], rows = [];
    let inCreate = false, inInsert = false, insertBuffer = '';
    const rl = readline.createInterface({ input: fs.createReadStream(sqlPath, { encoding: 'utf8' }) });
    rl.on('line', (line) => {
      const t = line.trim();
      if (t.startsWith(`-- Table structure for table \`${tableName}\``)) { inCreate = true; return; }
      if (inCreate && t.startsWith('CREATE TABLE')) return;
      if (inCreate && t.startsWith('`')) { const m = t.match(/^`(\w+)`/); if (m) columns.push(m[1]); return; }
      if (inCreate && (t === ')' || t.startsWith(')'))) { inCreate = false; return; }
      if (t.startsWith('INSERT INTO `' + tableName + '`')) { inInsert = true; insertBuffer = t; if (t.endsWith(';')) { inInsert = false; parseInsert(insertBuffer, columns, rows); } return; }
      if (inInsert) { insertBuffer += '\n' + t; if (t.endsWith(';')) { inInsert = false; parseInsert(insertBuffer, columns, rows); } return; }
      if (t.startsWith('-- Table structure for table') && columns.length > 0) rl.close();
    });
    rl.on('close', () => resolve({ columns, rows }));
    rl.on('error', reject);
  });
}

function parseInsert(sql, columns, rows) {
  const m = sql.match(/VALUES\s*\n?\s*/i);
  if (!m) return;
  const vs = sql.substring(sql.indexOf(m[0]) + m[0].length, sql.length - 2);
  for (const rec of splitRecords(vs)) {
    const fields = parseFields(rec);
    if (fields.length > 0) {
      const obj = {};
      for (let i = 0; i < columns.length && i < fields.length; i++) obj[columns[i]] = fields[i];
      rows.push(obj);
    }
  }
}

function splitRecords(str) {
  const records = []; let depth = 0, start = 0, inQ = false;
  for (let i = 0; i < str.length; i++) {
    const c = str[i];
    if (c === '\\' && inQ) { i++; continue; }
    if (c === "'" && !inQ) inQ = true;
    else if (c === "'" && inQ) {
      if (i + 1 < str.length && str[i + 1] === "'") { i++; continue; }
      inQ = false; continue;
    }
    if (!inQ) { if (c === '(') { if (depth === 0) start = i + 1; depth++; } if (c === ')') { depth--; if (depth === 0) records.push(str.substring(start, i)); } }
  }
  return records;
}

function parseFields(str) {
  const fields = []; let cur = '', inQ = false;
  for (let i = 0; i < str.length; i++) {
    const c = str[i];
    if (c === '\\' && inQ) { cur += str[i + 1] || ''; i++; continue; }
    if (c === "'" && !inQ) { inQ = true; continue; }
    if (c === "'" && inQ) {
      if (i + 1 < str.length && str[i + 1] === "'") { cur += "'"; i++; continue; }
      inQ = false; continue;
    }
    if (inQ) { cur += c; continue; }
    if (c === ',') { fields.push(cur.trim()); cur = ''; continue; }
    if (c !== ' ' || cur.length > 0) cur += c;
  }
  fields.push(cur.trim());
  return fields.map(f => f === 'NULL' ? null : f);
}

function norm(val) {
  if (val === null || val === undefined || val === '') return '';
  return String(val).trim().replace(/\s{2,}/g, ' ');
}

(async () => {
  const excelPath = findExcel();
  const wb = xlsx.readFile(excelPath, { cellDates: true });
  const wbOut = xlsx.utils.book_new();
  const summaryRows = [];

  // ========================================
  // 1. ITEMS — brand issues only
  // ========================================
  console.log('Parsing Items...');
  const itemsSql = await parseSqlTable(SQL_PATH, 'tabItem');
  const itemsExcel = xlsx.utils.sheet_to_json(wb.Sheets['Items'], { defval: '', raw: false });
  const itemMap = new Map();
  for (const r of itemsSql.rows) itemMap.set(r.name, r);

  const itemRows = [];
  let itemMiss = 0, itemBrand = 0;
  for (const row of itemsExcel) {
    const id = String(row['ID'] || '').trim();
    if (!id) continue;
    const api = itemMap.get(id);
    if (!api) { itemMiss++; continue; }
    const exBrand = norm(row['Brand']);
    if (exBrand !== '' && norm(api.brand) === '') {
      itemRows.push({
        ID: id,
        'Item Name': (api.item_name || '').substring(0, 50),
        'Brand (Excel)': exBrand,
        'Brand (SQL)': 'null',
        Status: 'MISSING'
      });
      itemBrand++;
    }
  }
  if (itemRows.length > 0) { const ws = xlsx.utils.json_to_sheet(itemRows); xlsx.utils.book_append_sheet(wbOut, ws, 'Items - Brand Missing'); }
  summaryRows.push({ Sheet: 'Items', 'SQL Count': itemsSql.rows.length, 'Excel Count': itemsExcel.length, 'Missing in SQL': itemMiss, 'Brand=null': itemBrand });

  // ========================================
  // 2. ACCOUNTS — account_type issues
  // ========================================
  console.log('Parsing Accounts...');
  const accSql = await parseSqlTable(SQL_PATH, 'tabAccount');
  const accExcel = xlsx.utils.sheet_to_json(wb.Sheets['Accounts New'], { defval: '', raw: false });
  const accByNum = new Map();
  for (const r of accSql.rows) {
    const num = (r.account_number || '').trim();
    if (num && norm(r.company).toLowerCase().includes('connect')) accByNum.set(num, r);
  }

  const accRows = [];
  let accMiss = 0, accEmptyType = 0;
  for (const row of accExcel) {
    const num = String(row['Account Number'] || '').trim();
    const name = String(row['Account Name'] || '').trim();
    const api = accByNum.get(num);
    if (!api) { accMiss++; continue; }
    const exType = norm(row['Account Type']);
    const apType = norm(api.account_type);
    if (exType !== '' && apType === '') {
      accRows.push({
        'Account Number': num,
        'Account Name': name,
        'Account Type (Excel)': exType,
        'Account Type (SQL)': '(empty)',
        'Root Type': api.root_type || '',
        'Is Group': api.is_group || '',
        Status: 'EMPTY'
      });
      accEmptyType++;
    }
  }
  if (accRows.length > 0) { const ws = xlsx.utils.json_to_sheet(accRows); xlsx.utils.book_append_sheet(wbOut, ws, 'Accounts - Type Missing'); }
  summaryRows.push({ Sheet: 'Accounts', 'SQL Count (CD)': accByNum.size, 'Excel Count': accExcel.length, 'Missing in SQL': accMiss, 'Type Empty': accEmptyType });

  // ========================================
  // 3. CUSTOMERS — missing + customer_group
  // ========================================
  console.log('Parsing Customers...');
  const custSql = await parseSqlTable(SQL_PATH, 'tabCustomer');
  const custExcel = xlsx.utils.sheet_to_json(wb.Sheets['Customers'], { defval: '', raw: false });
  const custMap = new Map();
  for (const r of custSql.rows) custMap.set(r.name, r);

  const custRows = [];
  let custMiss = 0;
  for (const row of custExcel) {
    const id = String(row['ID'] || '').trim();
    if (!id) continue;
    const api = custMap.get(id);
    if (!api) {
      custRows.push({ ID: id, 'Customer Name': row['Customer Name'] || '', Issue: 'Missing in SQL', 'Customer Group (Excel)': row['Customer Group'] || '' });
      custMiss++;
      continue;
    }
    if (!api.customer_group || norm(api.customer_group) === '') {
      custRows.push({ ID: id, 'Customer Name': (api.customer_name || '').substring(0, 40), Issue: 'Missing customer_group', 'Customer Group (Excel)': row['Customer Group'] || '' });
    }
  }
  if (custRows.length > 0) { const ws = xlsx.utils.json_to_sheet(custRows); xlsx.utils.book_append_sheet(wbOut, ws, 'Customers - Issues'); }
  summaryRows.push({ Sheet: 'Customers', 'SQL Count': custSql.rows.length, 'Excel Count': custExcel.length, 'Missing in SQL': custMiss, 'Other Issues': custRows.length - custMiss });

  // ========================================
  // 4. SUPPLIERS
  // ========================================
  console.log('Parsing Suppliers...');
  const supSql = await parseSqlTable(SQL_PATH, 'tabSupplier');
  const supExcel = xlsx.utils.sheet_to_json(wb.Sheets['Suppliers'], { defval: '', raw: false });
  const supMap = new Map();
  for (const r of supSql.rows) supMap.set(r.name, r);
  let supMiss = 0;
  for (const row of supExcel) {
    const id = String(row['CD ID'] || row['Supplier Name'] || '').trim();
    if (id && !supMap.has(id)) supMiss++;
  }
  summaryRows.push({ Sheet: 'Suppliers', 'SQL Count': supSql.rows.length, 'Excel Count': supExcel.length, 'Missing in SQL': supMiss });

  // ========================================
  // 5. EMPLOYEES
  // ========================================
  console.log('Parsing Employees...');
  const empSql = await parseSqlTable(SQL_PATH, 'tabEmployee');
  const empExcel = xlsx.utils.sheet_to_json(wb.Sheets['Employees'], { defval: '', raw: false });
  const empMap = new Map();
  for (const r of empSql.rows) empMap.set(r.name, r);

  const empRows = [];
  for (const row of empExcel) {
    const id = String(row['EmployeeID'] || '').trim();
    if (!id) continue;
    const nonKeyEmpty = Object.entries(row).filter(([k]) => k !== 'EmployeeID').every(([, v]) => v === null || v === undefined || v === '');
    if (nonKeyEmpty) continue;
    if (!empMap.has(id)) empRows.push({ ID: id, Name: row['EmployeeNameEN'] || '', Surname: row['EmployeeSurnameEN'] || '', Department: row['Department'] || '' });
  }
  if (empRows.length > 0) { const ws = xlsx.utils.json_to_sheet(empRows); xlsx.utils.book_append_sheet(wbOut, ws, 'Employees - Missing'); }
  summaryRows.push({ Sheet: 'Employees', 'SQL Count': empSql.rows.length, 'Excel Count': empExcel.length, 'Missing in SQL': empRows.length });

  // ========================================
  // Summary
  // ========================================
  const wsSum = xlsx.utils.json_to_sheet(summaryRows);
  xlsx.utils.book_append_sheet(wbOut, wsSum, 'Summary');

  const outFile = path.join(EXCEL_DIR, 'CD-ERPNext SQL vs Excel Comparison.xlsx');
  xlsx.writeFile(wbOut, outFile);

  console.log('\n========================================');
  console.log('Exported:', outFile);
  console.log('========================================');
  for (const s of summaryRows) console.log('  ' + JSON.stringify(s));
  process.exit(0);
})();
