import { existsSync, mkdirSync } from 'node:fs';
import { spawnSync } from 'node:child_process';
import path from 'node:path';

import type { DatasetConfig, MasterSourceFormat } from './datasets';

const XLSX = require('xlsx');

export interface SheetData {
  headers: string[];
  rows: unknown[][];
  filePath: string;
}

const DEFAULT_IMPORT_RAR = path.resolve(
  process.cwd(),
  process.env.MASTER_IMPORT_RAR ?? 'ERPNext Backups/ERPNext Import.rar',
);

const DEFAULT_IMPORT_DIR = path.resolve(
  process.cwd(),
  process.env.MASTER_IMPORT_DIR ?? '.tmp_extract/ERPNext Import',
);

/**
 * ตรวจสอบและสร้าง import directory — ถ้าไม่มีจะแตก RAR archive ด้วย tar
 * @returns path ของ import directory ที่พร้อมใช้งาน
 */
export function ensureImportDirectory(): string {
  if (existsSync(DEFAULT_IMPORT_DIR)) {
    return DEFAULT_IMPORT_DIR;
  }

  if (!existsSync(DEFAULT_IMPORT_RAR)) {
    throw new Error(
      `Master import source not found. Checked "${DEFAULT_IMPORT_DIR}" and "${DEFAULT_IMPORT_RAR}".`,
    );
  }

  const extractRoot = path.dirname(DEFAULT_IMPORT_DIR);
  mkdirSync(extractRoot, { recursive: true });

  const result = spawnSync('tar', ['-xf', DEFAULT_IMPORT_RAR, '-C', extractRoot], {
    cwd: process.cwd(),
    encoding: 'utf-8',
    shell: process.platform === 'win32',
  });

  if (result.status !== 0) {
    throw new Error(
      `Failed to extract "${DEFAULT_IMPORT_RAR}" with tar.\n${result.stderr || result.stdout}`,
    );
  }

  if (!existsSync(DEFAULT_IMPORT_DIR)) {
    throw new Error(`Extraction finished but "${DEFAULT_IMPORT_DIR}" is still missing.`);
  }

  return DEFAULT_IMPORT_DIR;
}

/**
 * โหลดข้อมูลจาก spreadsheet source — รองรับ local file, remote URL และ Google Sheets
 * @param dataset - DatasetConfig ที่มี source path หรือ URL
 * @returns SheetData ที่มี headers, rows และ filePath
 */
export async function loadSheetData(dataset: DatasetConfig): Promise<SheetData> {
  const source = dataset.source?.trim();

  if (!source) {
    const importDir = ensureImportDirectory();
    const filePath = path.join(importDir, dataset.file);
    return readWorkbookFromFile(filePath, dataset);
  }

  if (isRemoteUrl(source)) {
    const resolvedUrl = normalizeRemoteSourceUrl(source, dataset);
    const response = await fetch(resolvedUrl);

    if (!response.ok) {
      throw new Error(
        `Failed to fetch "${resolvedUrl}" for "${dataset.file}": ${response.status} ${response.statusText}`,
      );
    }

    const buffer = Buffer.from(await response.arrayBuffer());
    return readWorkbookFromBuffer(buffer, resolvedUrl, dataset, response.headers.get('content-type'));
  }

  const filePath = path.resolve(process.cwd(), source);
  if (!existsSync(filePath)) {
    throw new Error(
      `Configured source "${source}" for "${dataset.file}" was not found at "${filePath}".`,
    );
  }

  return readWorkbookFromFile(filePath, dataset);
}

/**
 * แปลง remote source URL ให้เป็น export URL ที่เหมาะสม — รองรับ Google Sheets export เป็น CSV/XLSX
 * @param urlText - URL ต้นทาง
 * @param dataset - DatasetConfig ที่มี format และ worksheet config
 * @returns URL ที่แปลงแล้วสำหรับ download
 */
export function normalizeRemoteSourceUrl(
  urlText: string,
  dataset: Pick<DatasetConfig, 'file' | 'format' | 'worksheet'>,
): string {
  if (!isGoogleSheetsUrl(urlText)) {
    return urlText;
  }

  const url = new URL(urlText);
  const pathMatch = url.pathname.match(/\/spreadsheets\/d\/([^/]+)/);
  if (!pathMatch) {
    return urlText;
  }

  const documentId = pathMatch[1];
  const configuredFormat = dataset.format && dataset.format !== 'auto'
    ? dataset.format
    : undefined;
  const gid = getGoogleSheetGid(url);

  if (configuredFormat === 'xlsx') {
    return `https://docs.google.com/spreadsheets/d/${documentId}/export?format=xlsx`;
  }

  if (configuredFormat === 'csv' || gid !== undefined) {
    const exportUrl = new URL(
      `https://docs.google.com/spreadsheets/d/${documentId}/export`,
    );
    exportUrl.searchParams.set('format', 'csv');
    if (gid !== undefined) {
      exportUrl.searchParams.set('gid', gid);
    }
    return exportUrl.toString();
  }

  return `https://docs.google.com/spreadsheets/d/${documentId}/export?format=xlsx`;
}

/**
 * อ่าน workbook จาก local file path โดยใช้ XLSX library
 * @param filePath - path ของไฟล์ spreadsheet
 * @param dataset - DatasetConfig ที่มี worksheet config
 * @returns SheetData ที่อ่านจากไฟล์
 */
function readWorkbookFromFile(
  filePath: string,
  dataset: DatasetConfig,
): SheetData {
  const workbook = XLSX.readFile(filePath, {
    cellDates: true,
    raw: true,
  });

  return sheetDataFromWorkbook(workbook, filePath, dataset);
}

/**
 * อ่าน workbook จาก Buffer (เช่นจาก fetch response) โดย infer format จาก content-type หรือ extension
 * @param buffer - Buffer ของข้อมูล spreadsheet
 * @param sourceLabel - ชื่อ source สำหรับ error message
 * @param dataset - DatasetConfig ที่มี format config
 * @param contentType - MIME type จาก HTTP response
 * @returns SheetData ที่อ่านจาก buffer
 */
function readWorkbookFromBuffer(
  buffer: Buffer,
  sourceLabel: string,
  dataset: DatasetConfig,
  contentType: string | null,
): SheetData {
  const inferredFormat = inferFormat(sourceLabel, dataset.format, contentType);
  const workbook = XLSX.read(buffer, {
    type: 'buffer',
    raw: true,
    cellDates: true,
    ...(inferredFormat === 'csv' ? { codepage: 65001 } : {}),
  });

  return sheetDataFromWorkbook(workbook, sourceLabel, dataset);
}

/**
 * แปลง workbook object เป็น SheetData โดยอ่าน sheet ตาม config และ extract headers + rows
 * @param workbook - XLSX workbook object
 * @param sourceLabel - ชื่อ source สำหรับ error message
 * @param dataset - DatasetConfig ที่มี worksheet config
 * @returns SheetData พร้อม headers และ rows
 */
function sheetDataFromWorkbook(
  workbook: { SheetNames: string[]; Sheets: Record<string, unknown> },
  sourceLabel: string,
  dataset: DatasetConfig,
): SheetData {
  const sheetName = resolveSheetName(workbook.SheetNames, dataset);
  const sheet = workbook.Sheets[sheetName];
  if (!sheet) {
    throw new Error(
      `Worksheet "${String(dataset.worksheet)}" was not found for "${dataset.file}" in "${sourceLabel}".`,
    );
  }

  const rows = XLSX.utils.sheet_to_json(sheet, {
    header: 1,
    defval: null,
    raw: true,
  }) as unknown[][];

  if (rows.length === 0) {
    throw new Error(`Sheet "${sheetName}" in "${sourceLabel}" is empty.`);
  }

  const [headerRow, ...bodyRows] = rows;
  const headers = (headerRow as unknown[]).map((value: unknown) =>
    String(value ?? '').trim(),
  );

  return {
    headers,
    rows: (bodyRows as unknown[][]).map((row: unknown[]) => row.slice(0, headers.length)),
    filePath: sourceLabel,
  };
}

/**
 * หาชื่อ sheet ที่ต้องการอ่านจาก workbook — รองรับชื่อ sheet หรือ zero-based index
 * @param sheetNames - รายชื่อ sheets ทั้งหมดใน workbook
 * @param dataset - DatasetConfig ที่มี worksheet config
 * @returns ชื่อ sheet ที่ต้องการ
 */
function resolveSheetName(
  sheetNames: string[],
  dataset: Pick<DatasetConfig, 'file' | 'worksheet'>,
): string {
  if (dataset.worksheet === undefined) {
    return sheetNames[0];
  }

  if (typeof dataset.worksheet === 'number') {
    const sheetName = sheetNames[dataset.worksheet];
    if (!sheetName) {
      throw new Error(
        `Worksheet index ${dataset.worksheet} is out of range for "${dataset.file}".`,
      );
    }
    return sheetName;
  }

  return dataset.worksheet;
}

/**
 * infer รูปแบบไฟล์ (csv/xlsx) จาก config, content-type หรือ file extension
 * @param sourceLabel - ชื่อ source หรือ URL สำหรับตรวจสอบ extension
 * @param configuredFormat - format ที่ตั้งไว้ใน config ("auto" = infer)
 * @param contentType - MIME type จาก HTTP response
 * @returns MasterSourceFormat ที่ infer แล้ว
 */
function inferFormat(
  sourceLabel: string,
  configuredFormat: MasterSourceFormat | undefined,
  contentType: string | null,
): MasterSourceFormat {
  if (configuredFormat && configuredFormat !== 'auto') {
    return configuredFormat;
  }

  const normalizedContentType = (contentType ?? '').toLowerCase();
  if (normalizedContentType.includes('text/csv')) {
    return 'csv';
  }
  if (
    normalizedContentType.includes(
      'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    ) ||
    normalizedContentType.includes('application/vnd.ms-excel')
  ) {
    return 'xlsx';
  }

  const extension = path.extname(sourceLabel).toLowerCase();
  if (extension === '.csv') {
    return 'csv';
  }

  return 'xlsx';
}

/**
 * ตรวจสอบว่า string เป็น remote URL (http:// หรือ https://) หรือไม่
 * @param value - string ที่ต้องการตรวจสอบ
 * @returns true ถ้าเป็น remote URL
 */
function isRemoteUrl(value: string): boolean {
  return /^https?:\/\//i.test(value);
}

/**
 * ตรวจสอบว่า URL เป็น Google Sheets URL หรือไม่
 * @param value - string URL ที่ต้องการตรวจสอบ
 * @returns true ถ้าเป็น Google Sheets URL
 */
function isGoogleSheetsUrl(value: string): boolean {
  return /^https?:\/\/docs\.google\.com\/spreadsheets\//i.test(value);
}

/**
 * ดึง Google Sheets gid parameter จาก query string หรือ URL hash fragment
 * @param url - URL object ของ Google Sheets URL
 * @returns gid string หรือ undefined ถ้าไม่มี
 */
function getGoogleSheetGid(url: URL): string | undefined {
  const direct = url.searchParams.get('gid');
  if (direct) {
    return direct;
  }

  const hashMatch = url.hash.match(/gid=(\d+)/i);
  return hashMatch?.[1];
}
