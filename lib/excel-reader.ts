/** ข้อมูลที่โหลดจาก Google Sheets เก็บ sheet data เป็น Map ตามชื่อ tab */
export interface SheetData {
  sheets: Map<string, Record<string, any>[]>;
  source: string;
}

const DEFAULT_SHEET_ID = '1P40NXIF72wm4YVLfqN0l3-W3GXLt2GVraVLY9bKZXFQ';

let _cache: SheetData | null = null;
let _cacheKey = '';

/** สร้าง Google Auth credential โดยเช็ค GOOGLE_APPLICATION_CREDENTIALS (Service Account key) ก่อน ถ้าไม่มีจะใช้ Application Default Credentials (gcloud auth application-default login) */
function getGoogleAuth(google: any) {
  if (process.env.GOOGLE_APPLICATION_CREDENTIALS) {
    return new google.auth.GoogleAuth({
      keyFile: process.env.GOOGLE_APPLICATION_CREDENTIALS,
      scopes: ['https://www.googleapis.com/auth/spreadsheets.readonly'],
    });
  }
  return new google.auth.GoogleAuth({
    scopes: ['https://www.googleapis.com/auth/spreadsheets.readonly'],
  });
}

/** โหลดข้อมูลทั้งหมดจาก Google Sheets API โดยใช้ batchGet (1 API call สำหรับทุก sheet) แทนการเรียกแยกทีละ sheet เพื่อลด API quota usage */
async function fetchGoogleSheets(sheetId: string): Promise<SheetData> {
  const { google } = await import('googleapis');
  const auth = getGoogleAuth(google);
  const sheetsApi = google.sheets({ version: 'v4', auth });

  const meta = await sheetsApi.spreadsheets.get({ spreadsheetId: sheetId });
  const titles = (meta.data.sheets || [])
    .map((s: any) => s.properties?.title || '')
    .filter(Boolean);

  const sheets = new Map<string, Record<string, any>[]>();

  if (titles.length === 0) {
    return { sheets, source: `googlesheets://${sheetId}` };
  }

  const batchRes = await sheetsApi.spreadsheets.values.batchGet({
    spreadsheetId: sheetId,
    ranges: titles,
  });

  const valueRanges = batchRes.data.valueRanges || [];
  for (let i = 0; i < titles.length; i++) {
    const rows = valueRanges[i]?.values;
    if (!rows || rows.length <= 1) {
      sheets.set(titles[i], []);
      continue;
    }
    const headers = rows[0];
    const data: Record<string, any>[] = [];
    for (let r = 1; r < rows.length; r++) {
      const row: Record<string, any> = {};
      for (let c = 0; c < headers.length; c++) {
        row[headers[c]] = rows[r]?.[c] || '';
      }
      data.push(row);
    }
    sheets.set(titles[i], data);
  }

  console.log(`  Loaded ${sheets.size} sheets from Google Sheets (batchGet: 2 API calls)`);
  return { sheets, source: `googlesheets://${sheetId}` };
}

/** โหลดข้อมูลจาก Google Sheets API (cache ถ้าโหลดแล้ว) ใช้ Service Account key หรือ Application Default Credentials */
export async function loadGoogleSheets(): Promise<SheetData> {
  const sheetId = process.env.GOOGLE_SHEET_ID || DEFAULT_SHEET_ID;
  if (_cache && _cacheKey === sheetId) {
    console.log(`  Google Sheets: using cached data (${sheetId})`);
    return _cache;
  }
  console.log(`  Google Sheets: ${sheetId}`);
  _cache = await fetchGoogleSheets(sheetId);
  _cacheKey = sheetId;
  return _cache;
}

/** ดึง rows ของ sheet ตามชื่อจาก SheetData object ที่โหลดแล้ว คืน [] ถ้าไม่พบ */
export function getSheet(
  data: SheetData,
  sheetName: string,
): Record<string, any>[] {
  const rows = data.sheets.get(sheetName);
  if (!rows) {
    console.warn(`  WARNING: Sheet "${sheetName}" not found`);
    return [];
  }
  return rows;
}
