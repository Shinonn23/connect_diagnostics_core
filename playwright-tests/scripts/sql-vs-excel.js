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
  const match = files.find(f => f.startsWith('CD-ERPNext') && f.includes('v.3') && f.endsWith('.xlsx'));
  return path.join(EXCEL_DIR, match);
}

async function parseSqlTable(sqlPath, tableName) {
  return new Promise((resolve, reject) => {
    const columns = [];
    const rows = [];
    let inCreate = false;
    let inInsert = false;
    let insertBuffer = '';

    const rl = readline.createInterface({ input: fs.createReadStream(sqlPath, { encoding: 'utf8' }) });

    rl.on('line', (line) => {
      const trimmed = line.trim();

      if (trimmed.startsWith(`-- Table structure for table \`${tableName}\``)) {
        inCreate = true;
        return;
      }

      if (inCreate && trimmed.startsWith('CREATE TABLE')) {
        return;
      }

      if (inCreate && trimmed.startsWith('`')) {
        const colMatch = trimmed.match(/^`(\w+)`/);
        if (colMatch) columns.push(colMatch[1]);
        return;
      }

      if (inCreate && (trimmed === ')' || trimmed.startsWith(')'))) {
        inCreate = false;
        return;
      }

      if (trimmed === `-- Dumping data for table \`${tableName}\``) {
        return;
      }

      if (trimmed.startsWith('LOCK TABLES') || trimmed.startsWith('UNLOCK TABLES') ||
          trimmed.startsWith('/*!40')) {
        return;
      }

      if (trimmed.startsWith('INSERT INTO `' + tableName + '`')) {
        inInsert = true;
        insertBuffer = trimmed;
        if (trimmed.endsWith(';')) {
          inInsert = false;
          parseInsert(insertBuffer, columns, rows);
        }
        return;
      }

      if (inInsert) {
        insertBuffer += '\n' + trimmed;
        if (trimmed.endsWith(';')) {
          inInsert = false;
          parseInsert(insertBuffer, columns, rows);
        }
        return;
      }

      if (trimmed.startsWith('-- Table structure for table') && columns.length > 0) {
        rl.close();
      }
    });

    rl.on('close', () => resolve({ columns, rows }));
    rl.on('error', reject);
  });
}

function parseInsert(sql, columns, rows) {
  const valuesMatch = sql.match(/VALUES\s*\n?\s*/i);
  if (!valuesMatch) return;

  const valuesStart = sql.indexOf(valuesMatch[0]) + valuesMatch[0].length;
  const valuesStr = sql.substring(valuesStart, sql.length - 2);

  const records = splitRecords(valuesStr);
  for (const rec of records) {
    const fields = parseFields(rec);
    if (fields.length > 0) {
      const obj = {};
      for (let i = 0; i < columns.length && i < fields.length; i++) {
        obj[columns[i]] = fields[i];
      }
      rows.push(obj);
    }
  }
}

function splitRecords(str) {
  const records = [];
  let depth = 0;
  let start = 0;
  let inQuote = false;
  for (let i = 0; i < str.length; i++) {
    const c = str[i];
    if (c === "'" && (i === 0 || str[i - 1] !== '\\')) inQuote = !inQuote;
    if (!inQuote) {
      if (c === '(') { if (depth === 0) start = i + 1; depth++; }
      if (c === ')') { depth--; if (depth === 0) records.push(str.substring(start, i)); }
    }
  }
  return records;
}

function parseFields(str) {
  const fields = [];
  let current = '';
  let inQuote = false;
  for (let i = 0; i < str.length; i++) {
    const c = str[i];
    if (c === "'" && !inQuote) { inQuote = true; continue; }
    if (c === "'" && inQuote) {
      if (i + 1 < str.length && str[i + 1] === "'") { current += "'"; i++; continue; }
      if (i + 1 < str.length && str[i + 1] === '\\') { current += str[i + 1]; i++; continue; }
      inQuote = false; continue;
    }
    if (inQuote) { current += c; continue; }
    if (c === ',') { fields.push(current.trim()); current = ''; continue; }
    if (c !== ' ' || current.length > 0) current += c;
  }
  fields.push(current.trim());

  return fields.map(f => {
    if (f === 'NULL') return null;
    return f;
  });
}

function normalize(val) {
  if (val === null || val === undefined || val === '') return '';
  return String(val).trim().replace(/\s{2,}/g, ' ');
}

function compareField(excelVal, apiVal) {
  const ex = normalize(excelVal);
  const ap = normalize(apiVal);
  if (ex === '' && ap === '') return true;
  if (ex === '' || ap === '') return false;
  return ex.toLowerCase() === ap.toLowerCase();
}

function toBool(val) {
  if (val === null || val === undefined || val === '') return null;
  const s = String(val).trim().toLowerCase();
  if (['1', 'yes', 'true'].includes(s)) return true;
  if (['0', 'no', 'false'].includes(s)) return false;
  return null;
}

(async () => {
  console.log('Reading SQL dump...');
  console.log('File:', SQL_PATH);
  console.log('');

  const excelPath = findExcel();
  const wb = xlsx.readFile(excelPath, { cellDates: true });

  // ========================================
  // 1. ITEMS
  // ========================================
  console.log('=== ITEMS ===');
  const itemsSql = await parseSqlTable(SQL_PATH, 'tabItem');
  console.log('SQL Items:', itemsSql.rows.length);

  const itemsExcel = xlsx.utils.sheet_to_json(wb.Sheets['Items'], { defval: '', raw: false });
  console.log('Excel Items:', itemsExcel.length);

  const itemMap = new Map();
  for (const r of itemsSql.rows) itemMap.set(r.name, r);

  let brandMismatch = 0, brandMatch = 0, brandMissing = 0;
  const brandIssues = [];
  const otherIssues = [];

  for (const row of itemsExcel) {
    const id = String(row['ID'] || '').trim();
    if (!id) continue;
    const api = itemMap.get(id);
    if (!api) continue;

    // brand
    const exBrand = normalize(row['Brand']);
    const apBrand = normalize(api.brand);
    if (exBrand !== '') {
      if (apBrand === '') { brandMismatch++; brandIssues.push({ id, brand: exBrand }); }
      else brandMatch++;
    }

    // has_batch_no / has_serial_no (skip Product Bundle)
    if (api.is_stock_item === '1' || api.is_stock_item === '1') {
      const exBatch = toBool(row['Has Batch No']);
      const apBatch = toBool(api.has_batch_no);
      if (exBatch !== null && apBatch !== null && exBatch !== apBatch) {
        otherIssues.push({ id, field: 'has_batch_no', excel: row['Has Batch No'], api: api.has_batch_no });
      }
      const exSerial = toBool(row['Has Serial No']);
      const apSerial = toBool(api.has_serial_no);
      if (exSerial !== null && apSerial !== null && exSerial !== apSerial) {
        otherIssues.push({ id, field: 'has_serial_no', excel: row['Has Serial No'], api: api.has_serial_no });
      }
    }
  }

  console.log('Brand matched:', brandMatch);
  console.log('Brand mismatch (SQL null):', brandMismatch);
  console.log('Other field mismatches:', otherIssues.length);
  if (brandIssues.length > 0) {
    console.log('\nBrand issues (first 10):');
    for (const b of brandIssues.slice(0, 10)) console.log('  ' + b.id + ' -> ' + b.brand);
  }

  // ========================================
  // 2. ACCOUNTS (COA)
  // ========================================
  console.log('\n=== ACCOUNTS ===');
  const accSql = await parseSqlTable(SQL_PATH, 'tabAccount');
  console.log('SQL Accounts:', accSql.rows.length);

  const accExcel = xlsx.utils.sheet_to_json(wb.Sheets['Accounts New'], { defval: '', raw: false });
  console.log('Excel Accounts:', accExcel.length);

  const accMap = new Map();
  for (const r of accSql.rows) {
    const num = (r.account_number || r.name.split(' - ')[0]).trim();
    accMap.set(num, r);
  }

  let emptyType = 0, namingDiff = 0, realMismatch = 0;
  const emptyList = [], mismatchList = [];

  for (const row of accExcel) {
    const num = String(row['Account Number'] || '').trim();
    const api = accMap.get(num);
    if (!api) continue;

    const exType = normalize(row['Account Type']);
    const apType = normalize(api.account_type);

    if (exType !== '') {
      if (apType === '') { emptyType++; emptyList.push({ num, name: row['Account Name'], should: exType }); }
      else if (exType.toLowerCase() !== apType.toLowerCase()) {
        const isNaming = apType.toLowerCase().includes(exType.toLowerCase()) ||
          exType.toLowerCase().includes(apType.toLowerCase());
        if (isNaming) namingDiff++;
        else { realMismatch++; mismatchList.push({ num, name: row['Account Name'], excel: exType, api: apType }); }
      }
    }
  }

  console.log('Empty account_type:', emptyType);
  for (const e of emptyList) console.log('  [EMPTY] ' + e.num + ' | ' + e.name + ' | should="' + e.should + '"');
  console.log('Naming convention diff:', namingDiff);
  console.log('Real mismatch:', realMismatch);
  for (const m of mismatchList) console.log('  [MISMATCH] ' + m.num + ' | ' + m.name + ' | Excel="' + m.excel + '" API="' + m.api + '"');

  // ========================================
  // 3. CUSTOMERS
  // ========================================
  console.log('\n=== CUSTOMERS ===');
  const custSql = await parseSqlTable(SQL_PATH, 'tabCustomer');
  console.log('SQL Customers:', custSql.rows.length);
  const custExcel = xlsx.utils.sheet_to_json(wb.Sheets['Customers'], { defval: '', raw: false });
  console.log('Excel Customers:', custExcel.length);

  const custMap = new Map();
  for (const r of custSql.rows) custMap.set(r.name, r);

  let custMatch = 0, custMiss = 0, custGroupMissing = 0;
  for (const row of custExcel) {
    const id = String(row['ID'] || '').trim();
    if (!id) continue;
    const api = custMap.get(id);
    if (!api) { custMiss++; continue; }
    custMatch++;
    if (!api.customer_group || api.customer_group === '') custGroupMissing++;
  }
  console.log('Matched:', custMatch, 'Missing in SQL:', custMiss, 'Missing customer_group:', custGroupMissing);

  // ========================================
  // 4. EMPLOYEES
  // ========================================
  console.log('\n=== EMPLOYEES ===');
  const empSql = await parseSqlTable(SQL_PATH, 'tabEmployee');
  console.log('SQL Employees:', empSql.rows.length);
  const empExcel = xlsx.utils.sheet_to_json(wb.Sheets['Employees'], { defval: '', raw: false });
  console.log('Excel Employees:', empExcel.length);

  // ========================================
  // 5. WAREHOUSES
  // ========================================
  console.log('\n=== WAREHOUSES ===');
  const whSql = await parseSqlTable(SQL_PATH, 'tabWarehouse');
  console.log('SQL Warehouses:', whSql.rows.length);
  const whExcel = xlsx.utils.sheet_to_json(wb.Sheets['Warehouses'], { defval: '', raw: false });
  console.log('Excel Warehouses:', whExcel.length);

  // ========================================
  // SUMMARY
  // ========================================
  console.log('\n========================================');
  console.log('SUMMARY: SQL Dump vs Excel Comparison');
  console.log('========================================');
  console.log('Items:       SQL=' + itemsSql.rows.length + ' Excel=' + itemsExcel.length + ' Brand_null=' + brandMismatch + ' Other=' + otherIssues.length);
  console.log('Accounts:    SQL=' + accSql.rows.length + ' Excel=' + accExcel.length + ' Empty_type=' + emptyType + ' Naming=' + namingDiff + ' Mismatch=' + realMismatch);
  console.log('Customers:   SQL=' + custSql.rows.length + ' Excel=' + custExcel.length + ' Matched=' + custMatch + ' Missing=' + custMiss);
  console.log('Employees:   SQL=' + empSql.rows.length + ' Excel=' + empExcel.length);
  console.log('Warehouses:  SQL=' + whSql.rows.length + ' Excel=' + whExcel.length);

  process.exit(0);
})();
