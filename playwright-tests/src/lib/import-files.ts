import { existsSync, mkdirSync } from 'node:fs';
import { spawnSync } from 'node:child_process';
import path from 'node:path';

import type { DatasetConfig, MasterSourceFormat } from '../config/datasets';

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

function isRemoteUrl(value: string): boolean {
  return /^https?:\/\//i.test(value);
}

function isGoogleSheetsUrl(value: string): boolean {
  return /^https?:\/\/docs\.google\.com\/spreadsheets\//i.test(value);
}

function getGoogleSheetGid(url: URL): string | undefined {
  const direct = url.searchParams.get('gid');
  if (direct) {
    return direct;
  }

  const hashMatch = url.hash.match(/gid=(\d+)/i);
  return hashMatch?.[1];
}
