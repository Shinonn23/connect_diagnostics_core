import { COUNTRY_ALIASES, ACCOUNT_TYPE_ALIASES, FieldMapping, SheetConfig } from './column-map';

/** อธิบายความไม่ตรงกันระดับ field เดียวระหว่างค่า Excel และ API */
export interface FieldDiff {
  field: string;
  excelValue: any;
  apiValue: any;
}

/** รวม field diffs ทั้งหมดของ record ที่ระบุด้วย key */
export interface RecordDiff {
  key: string;
  diffs: FieldDiff[];
}

/** ผลลัพธ์ validation สมบูรณ์ของ sheet เดียว รวมถึงจำนวน, ความไม่ตรง และสถานะ pass/fail */
export interface ValidationResult {
  sheetName: string;
  doctype: string;
  label: string;
  excelCount: number;
  apiCount: number;
  matched: number;
  missingInApi: string[];
  extraInApi: string[];
  fieldMismatches: RecordDiff[];
  passed: boolean;
}

/** Normalize string โดยแปลงค่า null/undefined/empty เป็น string ว่าง และลบ whitespace ซ้ำ */
function normalize(val: any): string {
  if (val === null || val === undefined || val === '') return '';
  if (typeof val === 'number') {
    if (Number.isInteger(val)) return String(val);
    return String(val);
  }
  return String(val).trim().replace(/\s{2,}/g, ' ');
}

/** แปลงค่าเป็น boolean โดยรองรับรูปแบบ '1', 'yes', 'true', '✓', '0', 'no', 'false', '✗' */
function toBool(val: any): boolean | null {
  if (val === null || val === undefined || val === '') return null;
  const s = String(val).trim().toLowerCase();
  if (['1', 'yes', 'true', '✓', 'checked'].includes(s)) return true;
  if (['0', 'no', 'false', '✗', 'unchecked', ''].includes(s)) return false;
  return null;
}

/** ตัด suffix "- CD" ออกจากท้าย string */
function stripCdSuffix(val: string): string {
  return val.replace(/\s*-\s*CD\s*$/, '').trim();
}

/** ตัด company suffix เช่น "- ... - CD/DKSH/UBIQ" ออกจากท้าย string */
function stripCompanySuffix(val: string): string {
  return val.replace(/\s*-\s*[^-]+\s*-\s*(CD|DKSH|UBIQ)\s*$/, '').trim();
}

/** ตัด tax suffix เช่น "- CD/DKSH/UBIQ" และตัวเลขท้ายสุดออกจาก string */
function stripTaxSuffix(val: string): string {
  let v = val.replace(/\s*-\s*(CD|DKSH|UBIQ)\s*$/, '').trim();
  v = v.replace(/\s+\d+$/, '').trim();
  return v;
}

/** แปลง float string โดยตัดท้าย ".0" ออก เช่น "10.0" → "10" */
function floatToString(val: any): string {
  const s = String(val).trim();
  if (s.endsWith('.0')) return s.slice(0, -2);
  return s;
}

/** เปรียบเทียบค่า Excel กับ API value ตาม mapping config รองรับ boolean, country alias, fuzzy match และ case-insensitive */
function compareValues(
  excelVal: any,
  apiVal: any,
  mapping: FieldMapping,
): boolean {
  const normEx = normalize(excelVal);
  const normAp = normalize(apiVal);

  if (normEx === '' && normAp === '') return true;
  if (!mapping.accountTypeAlias && (normEx === '' || normAp === '')) return normEx === normAp;

  if (mapping.booleanField) {
    const exBool = toBool(excelVal);
    const apBool = toBool(apiVal);
    if (exBool !== null && apBool !== null) return exBool === apBool;
  }

  if (mapping.countryAlias) {
    const aliases = COUNTRY_ALIASES[normEx] || COUNTRY_ALIASES[normAp];
    if (aliases) {
      return aliases.includes(normEx) && aliases.includes(normAp);
    }
  }

  if (mapping.accountTypeAlias) {
    const aliases = ACCOUNT_TYPE_ALIASES[normEx] || ACCOUNT_TYPE_ALIASES[normAp];
    if (aliases) {
      return aliases.includes(normEx) && aliases.includes(normAp);
    }
  }

  if (mapping.fuzzyMatch === 'account-type') {
    const aliases = ACCOUNT_TYPE_ALIASES[normEx] || ACCOUNT_TYPE_ALIASES[normAp];
    if (aliases) {
      return aliases.includes(normEx) && aliases.includes(normAp);
    }
    return normEx === normAp;
  }

  if (mapping.fuzzyMatch === 'strip-cd') {
    return stripCdSuffix(normEx) === stripCdSuffix(normAp);
  }

  if (mapping.fuzzyMatch === 'strip-tax-suffix') {
    return stripTaxSuffix(normEx) === stripTaxSuffix(normAp);
  }

  if (mapping.firstNameOnly) {
    return normAp.toLowerCase().startsWith(normEx.toLowerCase());
  }

  if (mapping.ignoreCase) {
    return normEx.toLowerCase() === normAp.toLowerCase();
  }

  return normEx === normAp;
}

/** ดึงค่าจาก Excel row ตามชื่อ column รองรับหลาย columns โดยคืนค่าแรกที่ไม่ว่าง */
function getExcelValue(row: Record<string, any>, excelCol: string | string[]): any {
  if (Array.isArray(excelCol)) {
    for (const col of excelCol) {
      const v = row[col];
      if (v !== null && v !== undefined && v !== '') return v;
    }
    return '';
  }
  return row[excelCol];
}

/** สร้าง lookup key จาก Excel row ตาม config รองรับ keyExtractor, keyFuzzyMatch และ keyIgnoreCase */
function getExcelKey(row: Record<string, any>, config: SheetConfig): string {
  const keys = Array.isArray(config.keyExcel) ? config.keyExcel : [config.keyExcel];
  for (const k of keys) {
    let v = normalize(row[k]);
    if (!v) continue;
    if (config.keyExtractor) v = config.keyExtractor(v);
    if (config.keyFuzzyMatch === 'float-to-string') {
      v = floatToString(v);
    }
    if (config.keyIgnoreCase) return v.toLowerCase();
    if (config.keyFuzzyMatch === 'strip-cd') return stripCdSuffix(v);
    if (config.keyFuzzyMatch === 'strip-company-suffix') return stripCompanySuffix(v);
    if (config.keyFuzzyMatch === 'strip-tax-suffix') return stripTaxSuffix(v);
    return v;
  }
  return '';
}

/** สร้าง lookup key จาก API record ตาม config รองรับ keyExtractor, keyFuzzyMatch และ keyIgnoreCase */
function getApiKey(rec: Record<string, any>, config: SheetConfig): string {
  let v = normalize(rec[config.keyApi]);
  if (config.keyExtractor) v = config.keyExtractor(v);
  if (config.keyFuzzyMatch === 'float-to-string') {
    v = floatToString(v);
  }
  if (config.keyIgnoreCase) return v.toLowerCase();
  if (config.keyFuzzyMatch === 'strip-cd') return stripCdSuffix(v);
  if (config.keyFuzzyMatch === 'strip-company-suffix') return stripCompanySuffix(v);
  if (config.keyFuzzyMatch === 'strip-tax-suffix') return stripTaxSuffix(v);
  return v;
}

/** เปรียบเทียบ Excel rows กับ API records ของ sheet แล้วคืน ValidationResult แบบละเอียด */
export function validateSheet(
  excelRows: Record<string, any>[],
  apiRecords: Record<string, any>[],
  config: SheetConfig,
): ValidationResult {
  const result: ValidationResult = {
    sheetName: config.sheetName,
    doctype: config.doctype,
    label: config.label,
    excelCount: 0,
    apiCount: apiRecords.length,
    matched: 0,
    missingInApi: [],
    extraInApi: [],
    fieldMismatches: [],
    passed: true,
  };

  const apiMap = new Map<string, Record<string, any>>();
  for (const rec of apiRecords) {
    const key = getApiKey(rec, config);
    apiMap.set(key, rec);

    if (config.compositeKey) {
      const compositeKey = `${normalize(rec['item_code'])}|${normalize(rec['price_list'])}`;
      apiMap.set(compositeKey.toLowerCase(), rec);
    }

    if (config.keyFuzzyMatch === 'float-to-string') {
      const fts = floatToString(normalize(rec[config.keyApi]));
      if (fts) apiMap.set(fts, rec);
    }
  }

  const matchedApiKeys = new Set<string>();

  for (const row of excelRows) {
    let excelKey: string;
    let displayKey: string;

    if (config.compositeKey) {
      const parts = config.compositeKey(row);
      excelKey = parts.toLowerCase();
      displayKey = parts.replace('|', ' / ');
    } else {
      excelKey = getExcelKey(row, config);
      displayKey = excelKey;
    }

    if (!excelKey && !config.compositeKey) {
      const allEmpty = Object.values(row).every(
        (v) => v === null || v === undefined || v === '',
      );
      if (allEmpty) continue;
    }

    const keyCols = Array.isArray(config.keyExcel) ? config.keyExcel : [config.keyExcel];
    const nonKeyValues = Object.entries(row)
      .filter(([k]) => !keyCols.includes(k))
      .map(([, v]) => v);
    const allNonKeyEmpty = nonKeyValues.every(
      (v) => v === null || v === undefined || v === '',
    );
    if (allNonKeyEmpty && !config.compositeKey) continue;

    result.excelCount++;

    if (!excelKey && !config.compositeKey) continue;

    let apiRec = apiMap.get(excelKey);

    if (!apiRec && !config.keyIgnoreCase) {
      for (const [k, v] of apiMap) {
        if (k.toLowerCase() === excelKey.toLowerCase()) {
          apiRec = v;
          break;
        }
      }
    }

    if (!apiRec) {
      result.missingInApi.push(displayKey);
      result.passed = false;
      continue;
    }

    const matchedKey = getApiKey(apiRec, config);
    matchedApiKeys.add(matchedKey);
    result.matched++;

    const diffs: FieldDiff[] = [];
    for (const fieldMap of config.fields) {
      if (fieldMap.skipWhen && fieldMap.skipWhen(apiRec)) continue;

      const exVal = getExcelValue(row, fieldMap.excel);
      const apVal = apiRec[fieldMap.api];

      if (normalize(exVal) === '') continue;

      if (!compareValues(exVal, apVal, fieldMap)) {
        diffs.push({
          field: fieldMap.api,
          excelValue: exVal,
          apiValue: apVal,
        });
      }
    }

    if (diffs.length > 0) {
      result.fieldMismatches.push({ key: displayKey, diffs });
      result.passed = false;
    }
  }

  const excelKeys = new Set<string>();
  for (const row of excelRows) {
    if (config.compositeKey) {
      const ck = config.compositeKey(row).toLowerCase();
      if (ck) excelKeys.add(ck);
    } else {
      const k = getExcelKey(row, config);
      if (k) excelKeys.add(k);
    }
  }

  for (const rec of apiRecords) {
    const apiKey = getApiKey(rec, config);
    let found = excelKeys.has(apiKey);
    if (!found && config.compositeKey) {
      const ck = `${normalize(rec['item_code'])}|${normalize(rec['price_list'])}`.toLowerCase();
      found = excelKeys.has(ck);
    }
    if (!found) {
      let display: string;
      if (config.compositeKey) {
        display = `${rec['item_code'] || ''} / ${rec['price_list'] || ''}`;
      } else {
        display = String(rec['name'] || rec[config.keyApi] || apiKey);
      }
      result.extraInApi.push(display);
    }
  }

  return result;
}

/** พิมพ์ ValidationResult เดียวไปที่ console พร้อม icons และรายละเอียด */
export function printResult(r: ValidationResult) {
  const icon = r.passed ? '✅' : '❌';
  console.log(`\n${'═'.repeat(65)}`);
  console.log(`  ${icon} ${r.label} → ${r.doctype}`);
  console.log(`${'═'.repeat(65)}`);
  console.log(`  Excel: ${r.excelCount} records | API: ${r.apiCount} records`);
  console.log(`  Matched: ${r.matched}`);

  if (r.missingInApi.length > 0) {
    console.log(`  📤 Missing in API (${r.missingInApi.length}):`);
    for (const m of r.missingInApi.slice(0, 20)) {
      console.log(`     - ${m}`);
    }
    if (r.missingInApi.length > 20) {
      console.log(`     ... and ${r.missingInApi.length - 20} more`);
    }
  }

  if (r.extraInApi.length > 0) {
    console.log(`  📥 Extra in API (${r.extraInApi.length}):`);
    for (const m of r.extraInApi.slice(0, 10)) {
      console.log(`     - ${m}`);
    }
    if (r.extraInApi.length > 10) {
      console.log(`     ... and ${r.extraInApi.length - 10} more`);
    }
  }

  if (r.fieldMismatches.length > 0) {
    console.log(`  ⚠️  Field Mismatches (${r.fieldMismatches.length}):`);
    for (const rec of r.fieldMismatches.slice(0, 20)) {
      console.log(`     - ${rec.key}:`);
      for (const d of rec.diffs) {
        console.log(`       .${d.field}: Excel="${d.excelValue}" → API="${d.apiValue}"`);
      }
    }
    if (r.fieldMismatches.length > 20) {
      console.log(`     ... and ${r.fieldMismatches.length - 20} more records`);
    }
  }
}

/** พิมพ์สรุปผลรวมจาก ValidationResult ทั้งหมด */
export function printSummary(results: ValidationResult[]) {
  const passed = results.filter((r) => r.passed).length;
  const failed = results.filter((r) => !r.passed).length;
  const totalExcel = results.reduce((s, r) => s + r.excelCount, 0);
  const totalApi = results.reduce((s, r) => s + r.apiCount, 0);
  const totalMissing = results.reduce((s, r) => s + r.missingInApi.length, 0);
  const totalMismatches = results.reduce((s, r) => s + r.fieldMismatches.length, 0);

  console.log(`\n${'═'.repeat(65)}`);
  console.log('  FINAL SUMMARY');
  console.log(`${'═'.repeat(65)}`);
  console.log(`  Sheets checked:  ${results.length}`);
  console.log(`  ✅ Passed:       ${passed}`);
  console.log(`  ❌ Failed:       ${failed}`);
  console.log(`  Total Excel:     ${totalExcel} records`);
  console.log(`  Total API:       ${totalApi} records`);
  console.log(`  Missing in API:  ${totalMissing} records`);
  console.log(`  Field mismatch:  ${totalMismatches} records`);
  console.log(`${'═'.repeat(65)}`);

  if (failed > 0) {
    console.log('\n  ❌ Failed sheets:');
    for (const r of results) {
      if (!r.passed) {
        console.log(
          `    - ${r.label} (${r.doctype}): missing=${r.missingInApi.length}, mismatches=${r.fieldMismatches.length}`,
        );
      }
    }
  } else {
    console.log('\n  ✅ ALL DATA VALIDATED SUCCESSFULLY!');
  }
  console.log('');
}
