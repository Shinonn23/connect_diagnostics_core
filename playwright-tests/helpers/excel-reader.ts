import * as xlsx from 'xlsx';
import * as path from 'path';
import * as fs from 'fs';
import * as os from 'os';

export interface ExcelData {
  sheets: Map<string, Record<string, any>[]>;
  filePath: string;
}

const SEARCH_DIRS = [
  process.env.EXCEL_DIR,
  path.join(__dirname, '..', 'data'),
  path.join(os.homedir(), 'Desktop'),
].filter(Boolean) as string[];

function findExcelFile(): string {
  for (const dir of SEARCH_DIRS) {
    if (!fs.existsSync(dir)) continue;
    const files = fs.readdirSync(dir);
    const match = files.find(
      (f) =>
        f.startsWith('CD-ERPNext') &&
        f.includes('v.3') &&
        f.endsWith('.xlsx'),
    );
    if (match) return path.join(dir, match);
  }
  throw new Error(
    `Cannot find CD-ERPNext Master Data Excel file. Searched: ${SEARCH_DIRS.join(', ')}`,
  );
}

export function loadExcel(filePath?: string): ExcelData {
  const fp = filePath || findExcelFile();
  console.log(`  Excel: ${fp}`);

  const wb = xlsx.readFile(fp, { cellDates: true });
  const sheets = new Map<string, Record<string, any>[]>();

  for (const name of wb.SheetNames) {
    const ws = wb.Sheets[name];
    const json = xlsx.utils.sheet_to_json<Record<string, any>>(ws, {
      defval: '',
      raw: false,
    });
    sheets.set(name, json);
  }

  console.log(`  Loaded ${wb.SheetNames.length} sheets`);
  return { sheets, filePath: fp };
}

export function getSheet(
  data: ExcelData,
  sheetName: string,
): Record<string, any>[] {
  const rows = data.sheets.get(sheetName);
  if (!rows) {
    console.warn(`  WARNING: Sheet "${sheetName}" not found`);
    return [];
  }
  return rows;
}
