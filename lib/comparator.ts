/** configuration สำหรับเปรียบเทียบ records ของ Frappe DocType ระหว่างสอง environments */
export interface CompareConfig {
  doctype: string;
  fields: string[];
  keyField?: string;
  label?: string;
}

/** อธิบายความแตกต่างระดับ field เดียวระหว่างค่า master และ dev */
export interface FieldDiff {
  field: string;
  masterValue: any;
  devValue: any;
}

/** รวม field diffs ทั้งหมดของ record ที่ระบุ */
export interface RecordDiff {
  name: string;
  diffs: FieldDiff[];
}

/** ผลลัพธ์การเปรียบเทียบสมบูรณ์ระหว่าง master และ dev สำหรับ DocType เดียว */
export interface CompareResult {
  doctype: string;
  label: string;
  masterCount: number;
  devCount: number;
  masterOnly: string[];
  devOnly: string[];
  fieldMismatches: RecordDiff[];
  passed: boolean;
}

const allResults: CompareResult[] = [];

/** คืน CompareResult entries ทั้งหมดที่สะสมไว้ระหว่าง session */
export function getAllResults(): CompareResult[] {
  return allResults;
}

/** เปรียบเทียบ record sets ของ master และ dev สำหรับ DocType คืน missing, extra และ field diffs */
export function compareRecords(
  masterRecords: any[],
  devRecords: any[],
  config: CompareConfig,
): CompareResult {
  const key = config.keyField || 'name';
  const label = config.label || config.doctype;
  const masterMap = new Map(masterRecords.map((r: any) => [r[key], r]));
  const devMap = new Map(devRecords.map((r: any) => [r[key], r]));

  const masterOnly: string[] = [];
  const devOnly: string[] = [];
  const fieldMismatches: RecordDiff[] = [];

  for (const name of masterMap.keys()) {
    if (!devMap.has(name)) {
      masterOnly.push(String(name));
    }
  }

  for (const name of devMap.keys()) {
    if (!masterMap.has(name)) {
      devOnly.push(String(name));
    }
  }

  for (const [name, masterRec] of masterMap) {
    const devRec = devMap.get(name);
    if (!devRec) continue;

    const diffs: FieldDiff[] = [];
    for (const field of config.fields) {
      const mv = masterRec[field] ?? null;
      const dv = devRec[field] ?? null;
      if (normalize(mv) !== normalize(dv)) {
        diffs.push({ field, masterValue: mv, devValue: dv });
      }
    }

    if (diffs.length > 0) {
      fieldMismatches.push({ name: String(name), diffs });
    }
  }

  const passed =
    masterOnly.length === 0 &&
    devOnly.length === 0 &&
    fieldMismatches.length === 0;

  const result: CompareResult = {
    doctype: config.doctype,
    label,
    masterCount: masterRecords.length,
    devCount: devRecords.length,
    masterOnly,
    devOnly,
    fieldMismatches,
    passed,
  };

  allResults.push(result);
  return result;
}

/** Normalize string โดยแปลง null/undefined เป็น string ว่างและ trim whitespace */
function normalize(val: any): string {
  if (val === null || val === undefined) return '';
  if (typeof val === 'number') return String(val);
  if (typeof val === 'boolean') return String(val);
  return String(val).trim();
}

/** พิมพ์ CompareResult เดียวไปที่ console พร้อม icons และรายละเอียด */
export function printReport(result: CompareResult) {
  const icon = result.passed ? '✅' : '❌';
  console.log(
    `\n${icon} ${result.label} (${result.doctype}): Master(${result.masterCount}) vs Dev(${result.devCount})`,
  );

  if (result.masterOnly.length > 0) {
    console.log(`  📤 Missing in Dev (${result.masterOnly.length}):`);
    for (const name of result.masterOnly.slice(0, 30)) {
      console.log(`     - ${name}`);
    }
    if (result.masterOnly.length > 30) {
      console.log(`     ... and ${result.masterOnly.length - 30} more`);
    }
  }

  if (result.devOnly.length > 0) {
    console.log(`  📥 Extra in Dev (${result.devOnly.length}):`);
    for (const name of result.devOnly.slice(0, 30)) {
      console.log(`     - ${name}`);
    }
    if (result.devOnly.length > 30) {
      console.log(`     ... and ${result.devOnly.length - 30} more`);
    }
  }

  if (result.fieldMismatches.length > 0) {
    console.log(`  ⚠️  Field Mismatches (${result.fieldMismatches.length}):`);
    for (const rec of result.fieldMismatches.slice(0, 30)) {
      for (const diff of rec.diffs) {
        console.log(
          `     - ${rec.name}.${diff.field}: Master="${diff.masterValue}" → Dev="${diff.devValue}"`,
        );
      }
    }
    if (result.fieldMismatches.length > 30) {
      console.log(
        `     ... and ${result.fieldMismatches.length - 30} more records`,
      );
    }
  }
}

/** พิมพ์สรุปผลรวมจาก comparison results ทั้งหมดที่สะสมไว้ใน session */
export function printSummary() {
  const results = getAllResults();
  const passed = results.filter((r) => r.passed).length;
  const failed = results.filter((r) => !r.passed).length;
  const totalMaster = results.reduce((s, r) => s + r.masterCount, 0);
  const totalDev = results.reduce((s, r) => s + r.devCount, 0);
  const totalMissing = results.reduce((s, r) => s + r.masterOnly.length, 0);
  const totalExtra = results.reduce((s, r) => s + r.devOnly.length, 0);
  const totalMismatches = results.reduce(
    (s, r) => s + r.fieldMismatches.length,
    0,
  );

  console.log('\n');
  console.log('═'.repeat(70));
  console.log('  COMPARISON SUMMARY');
  console.log('═'.repeat(70));
  console.log(`  Total DocTypes compared: ${results.length}`);
  console.log(`  ✅ Passed: ${passed}  ❌ Failed: ${failed}`);
  console.log(
    `  Total records: Master(${totalMaster}) vs Dev(${totalDev})`,
  );
  console.log(`  Missing in Dev: ${totalMissing} records`);
  console.log(`  Extra in Dev: ${totalExtra} records`);
  console.log(`  Field mismatches: ${totalMismatches} records`);
  console.log('═'.repeat(70));

  if (failed > 0) {
    console.log('\n  Failed DocTypes:');
    for (const r of results.filter((r) => !r.passed)) {
      console.log(
        `    ❌ ${r.label}: missing=${r.masterOnly.length}, extra=${r.devOnly.length}, mismatches=${r.fieldMismatches.length}`,
      );
    }
  }
  console.log('');
}
