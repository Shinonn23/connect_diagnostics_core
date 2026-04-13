const readline = require('readline');
const fs = require('fs');
const path = require('path');
const os = require('os');
const xlsx = require('xlsx');

const SQL = path.join(os.homedir(), 'Desktop', 'ERPNext Backups-002', 'rar', '20260413_214731-local-database.sql', '20260413_214731-local-database.sql');

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
  for (const rec of split(vs)) {
    const f = fields(rec); if (f.length > 0) { const o = {}; for (let i = 0; i < cols.length && i < f.length; i++) o[cols[i]] = f[i]; rows.push(o); }
  }
}
function split(s) { const r = []; let d = 0, st = 0, q = false; for (let i = 0; i < s.length; i++) { const c = s[i]; if (c === '\\' && q) { i++; continue; } if (c === "'" && !q) q = true; else if (c === "'" && q) { if (i + 1 < s.length && s[i + 1] === "'") { i++; continue; } q = false; continue; } if (!q) { if (c === '(') { if (d === 0) st = i + 1; d++; } if (c === ')') { d--; if (d === 0) r.push(s.substring(st, i)); } } } return r; }
function fields(s) { const f = []; let c = '', q = false; for (let i = 0; i < s.length; i++) { const ch = s[i]; if (ch === '\\' && q) { c += s[i + 1] || ''; i++; continue; } if (ch === "'" && !q) { q = true; continue; } if (ch === "'" && q) { if (i + 1 < s.length && s[i + 1] === "'") { c += "'"; i++; continue; } q = false; continue; } if (q) { c += ch; continue; } if (ch === ',') { f.push(c.trim()); c = ''; continue; } if (ch !== ' ' || c.length > 0) c += ch; } f.push(c.trim()); return f.map(x => x === 'NULL' ? null : x); }

(async () => {
  const empSql = await parseTable('tabEmployee');
  const sqlIds = new Set(empSql.map(r => r.name));
  console.log('SQL Employees:', empSql.length);
  for (const r of empSql) console.log('  SQL:', r.name, '-', (r.employee_name || '').substring(0, 30), '| company:', r.company);

  const dir = path.join(os.homedir(), 'Desktop');
  const files = fs.readdirSync(dir);
  const wb = xlsx.readFile(path.join(dir, files.find(f => f.startsWith('CD-ERPNext') && f.includes('v.3') && f.endsWith('.xlsx'))));
  const empEx = xlsx.utils.sheet_to_json(wb.Sheets['Employees'], { defval: '', raw: false });
  console.log('\nExcel Employees:', empEx.length);
  for (const r of empEx) {
    const id = String(r['EmployeeID'] || '').trim();
    const nonKey = Object.entries(r).filter(([k]) => k !== 'EmployeeID').every(([, v]) => v === null || v === undefined || v === '');
    if (nonKey) { console.log('  SKIP (empty row):', id); continue; }
    if (!sqlIds.has(id)) console.log('  MISSING IN SQL:', id, '-', r['EmployeeNameEN'] || '');
    else console.log('  OK:', id);
  }
  process.exit(0);
})();
