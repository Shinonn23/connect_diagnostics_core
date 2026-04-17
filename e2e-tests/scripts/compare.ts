import { mkdirSync, writeFileSync } from 'node:fs';
import path from 'node:path';

import type { DatasetConfig } from './datasets';
import { FrappeClient, type FrappeField, type FrappeMeta } from './frappe';
import { loadSheetData, type SheetData } from './import-files';

type NormalizedValue = boolean | number | string | null;

interface ResolvedParentColumn {
  header: string;
  kind: 'parent';
  fieldname: string;
  fieldtype?: string;
}

interface ResolvedChildColumn {
  header: string;
  kind: 'child';
  tableFieldname: string;
  tableLabel: string;
  childDoctype: string;
  childFieldname: string;
  childFieldtype?: string;
}

type ResolvedColumn = ResolvedParentColumn | ResolvedChildColumn;

interface ExpectedRecord {
  key: string;
  displayKey: string;
  parent: Record<string, NormalizedValue>;
  children: Record<string, Array<Record<string, NormalizedValue>>>;
}

interface DatasetIssue {
  key: string;
  field: string;
  expected: unknown;
  actual: unknown;
}

export interface DatasetReport {
  file: string;
  doctype: string;
  source?: string;
  expectedRecords: number;
  missingRecords: string[];
  extraRecords: string[];
  duplicateLiveRecords: Array<{ key: string; liveNames: string[] }>;
  fieldMismatches: DatasetIssue[];
  childTableMismatches: DatasetIssue[];
  unresolvedHeaders: string[];
  errors: string[];
}

export interface ComparisonSummary {
  generatedAt: string;
  outputDir: string;
  hasFailures: boolean;
  reports: DatasetReport[];
}

/**
 * เปรียบเทียบข้อมูลทั้งหมดจากทุก dataset config กับ live Frappe server
 * @param client - FrappeClient สำหรับเรียก API
 * @param datasets - รายการ DatasetConfig ที่ต้องการเปรียบเทียบ
 * @returns ComparisonSummary พร้อม report ของทุก dataset
 */
export async function compareAllDatasets(
  client: FrappeClient,
  datasets: DatasetConfig[],
): Promise<ComparisonSummary> {
  const reports: DatasetReport[] = [];

  for (const dataset of datasets) {
    try {
      reports.push(await compareDataset(client, dataset));
    } catch (error) {
      reports.push({
        file: dataset.file,
        doctype: dataset.doctype,
        source: dataset.source,
        expectedRecords: 0,
        missingRecords: [],
        extraRecords: [],
        duplicateLiveRecords: [],
        fieldMismatches: [],
        childTableMismatches: [],
        unresolvedHeaders: [],
        errors: [error instanceof Error ? error.message : String(error)],
      });
    }
  }

  const outputDir = writeSummaryFiles(reports);
  const hasFailures = reports.some((report) =>
    [
      report.errors.length,
      report.unresolvedHeaders.length,
      report.missingRecords.length,
      report.extraRecords.length,
      report.duplicateLiveRecords.length,
      report.fieldMismatches.length,
      report.childTableMismatches.length,
    ].some((count) => count > 0),
  );

  return {
    generatedAt: new Date().toISOString(),
    outputDir,
    hasFailures,
    reports,
  };
}

/**
 * เปรียบเทียบ dataset เดี่ยวกับข้อมูลจริงใน Frappe แบบ record-by-record
 * @param client - FrappeClient สำหรับเรียก API
 * @param dataset - DatasetConfig ของ dataset ที่ต้องการเปรียบเทียบ
 * @returns DatasetReport แจ้งผลการเปรียบเทียบ
 */
async function compareDataset(
  client: FrappeClient,
  dataset: DatasetConfig,
): Promise<DatasetReport> {
  const sheet = await loadSheetData(dataset);
  const { columns, unresolvedHeaders } = await resolveColumns(client, dataset, sheet);
  const report: DatasetReport = {
    file: dataset.file,
    doctype: dataset.doctype,
    source: sheet.filePath,
    expectedRecords: 0,
    missingRecords: [],
    extraRecords: [],
    duplicateLiveRecords: [],
    fieldMismatches: [],
    childTableMismatches: [],
    unresolvedHeaders,
    errors: [],
  };

  if (unresolvedHeaders.length > 0) {
    return report;
  }

  const hasChildColumns = columns.some((column) => column.kind === 'child');

  if ((dataset.comparison ?? 'record') === 'multiset') {
    return compareAsMultiset(client, dataset, columns, sheet, report);
  }

  const expectedRecords = buildExpectedRecords(dataset, sheet, columns, hasChildColumns);
  report.expectedRecords = expectedRecords.size;

  const identityColumns = resolveIdentityColumns(dataset, columns);
  const parentIdentityColumns = identityColumns.filter(
    (column): column is ResolvedParentColumn => column.kind === 'parent',
  );
  const requiresFullDocForIdentity = identityColumns.some(
    (column) => column.kind === 'child',
  );

  const liveKeyToRows = new Map<string, Array<Record<string, unknown>>>();
  const liveDocCache = new Map<string, Promise<Record<string, unknown>>>();
  const liveRows = await client.listAll(
    dataset.doctype,
    [...new Set(parentIdentityColumns.map((column) => column.fieldname))],
    dataset.liveFilters,
  );
  const getLiveDoc = (name: string) => {
    if (!liveDocCache.has(name)) {
      liveDocCache.set(name, client.getDoc(dataset.doctype, name));
    }
    return liveDocCache.get(name)!;
  };

  for (const row of liveRows) {
    const keys = requiresFullDocForIdentity
      ? extractIdentityKeysFromLiveDoc(
          await getLiveDoc(String(row.name)),
          dataset,
          identityColumns,
          dataset.identityHeaders,
          dataset.caseInsensitiveIdentity,
        )
      : [
          makeKey(
            parentIdentityColumns.map((column) =>
              normalizeColumnValue(
                dataset,
                column.header,
                row[column.fieldname],
                column.fieldtype,
              ),
            ),
            dataset.caseInsensitiveIdentity,
          ),
        ];

    for (const key of keys) {
      if (!liveKeyToRows.has(key)) {
        liveKeyToRows.set(key, []);
      }
      liveKeyToRows.get(key)!.push(row);
    }
  }

  for (const [key, expectedRecord] of expectedRecords.entries()) {
    const matchingRows = liveKeyToRows.get(key) ?? [];

    if (matchingRows.length === 0) {
      report.missingRecords.push(expectedRecord.displayKey);
      continue;
    }

    if (matchingRows.length > 1) {
      report.duplicateLiveRecords.push({
        key: expectedRecord.displayKey,
        liveNames: matchingRows.map((row) => String(row.name)),
      });
      continue;
    }

    const liveRow = matchingRows[0];
    if (hasChildColumns) {
      const liveDoc = await getLiveDoc(String(liveRow.name));
      compareGroupedRecord(dataset, expectedRecord, liveDoc, columns, report);
    } else {
      const singleRow = await getLiveDoc(String(liveRow.name));
      compareFlatRecord(dataset, expectedRecord, singleRow, columns, report);
    }
  }

  if (dataset.compareExtra) {
    for (const [key, rows] of liveKeyToRows.entries()) {
      if (!expectedRecords.has(key)) {
        report.extraRecords.push(rows.map((row) => String(row.name)).join(', '));
      }
    }
  }

  return report;
}

/**
 * เปรียบเทียบ dataset แบบ multiset — นับจำนวนแถวที่คาดหวัง vs ข้อมูลจริงโดยใช้ signature
 * @param client - FrappeClient สำหรับเรียก API
 * @param dataset - DatasetConfig ของ dataset ที่ต้องการเปรียบเทียบ
 * @param columns - รายการ ResolvedColumn ที่ map แล้ว
 * @param sheet - ข้อมูลจาก spreadsheet source
 * @param report - DatasetReport ที่จะเขียนผลลัพธ์
 */
async function compareAsMultiset(
  client: FrappeClient,
  dataset: DatasetConfig,
  columns: ResolvedColumn[],
  sheet: SheetData,
  report: DatasetReport,
): Promise<DatasetReport> {
  const parentColumns = columns.filter(
    (column): column is ResolvedParentColumn => column.kind === 'parent',
  );
  const liveRows = await client.listAll(
    dataset.doctype,
    [...new Set(parentColumns.map((column) => column.fieldname))],
    dataset.liveFilters,
  );
  const expectedCounter = new Map<string, number>();
  const liveCounter = new Map<string, number>();
      const renderedRows = new Map<string, string>();
  const headerIndex = new Map(sheet.headers.map((header, index) => [header, index]));

  for (const row of sheet.rows) {
    const signaturePayload: Record<string, NormalizedValue> = {};
    for (const column of parentColumns) {
      signaturePayload[column.header] = normalizeColumnValue(
        dataset,
        column.header,
        row[headerIndex.get(column.header) ?? -1],
        column.fieldtype,
      );
    }
    const signature = stableStringify(signaturePayload);
    renderedRows.set(signature, signature);
    expectedCounter.set(signature, (expectedCounter.get(signature) ?? 0) + 1);
  }

  for (const row of liveRows) {
    const signaturePayload: Record<string, NormalizedValue> = {};
    for (const column of parentColumns) {
      signaturePayload[column.header] = normalizeColumnValue(
        dataset,
        column.header,
        row[column.fieldname],
        column.fieldtype,
      );
    }
    const signature = stableStringify(signaturePayload);
    renderedRows.set(signature, signature);
    liveCounter.set(signature, (liveCounter.get(signature) ?? 0) + 1);
  }

  report.expectedRecords = sheet.rows.length;

  for (const signature of new Set([...expectedCounter.keys(), ...liveCounter.keys()])) {
    const expectedCount = expectedCounter.get(signature) ?? 0;
    const liveCount = liveCounter.get(signature) ?? 0;

    if (expectedCount > liveCount) {
      for (let index = 0; index < expectedCount - liveCount; index += 1) {
        report.missingRecords.push(renderedRows.get(signature) ?? signature);
      }
    }

    if (dataset.compareExtra && liveCount > expectedCount) {
      for (let index = 0; index < liveCount - expectedCount; index += 1) {
        report.extraRecords.push(renderedRows.get(signature) ?? signature);
      }
    }
  }

  return report;
}

/**
 * แก้ไข header ทั้งหมดใน sheet ให้เป็น ResolvedColumn โดยอ้างอิง Frappe meta
 * @param client - FrappeClient สำหรับดึง metadata
 * @param dataset - DatasetConfig ที่มีการตั้งค่า override
 * @param sheet - ข้อมูล spreadsheet ที่มี headers
 * @returns columns ที่แก้ไขแล้ว และ unresolvedHeaders ที่หาไม่เจอ
 */
async function resolveColumns(
  client: FrappeClient,
  dataset: DatasetConfig,
  sheet: SheetData,
): Promise<{ columns: ResolvedColumn[]; unresolvedHeaders: string[] }> {
  const meta = await client.getMeta(dataset.doctype);
  const columns: ResolvedColumn[] = [];
  const unresolvedHeaders: string[] = [];

  for (const header of sheet.headers) {
    if (!header) {
      continue;
    }

    if (dataset.ignoreHeaders?.includes(header)) {
      continue;
    }

    const resolved = await resolveColumn(client, meta, dataset, header);
    if (!resolved) {
      unresolvedHeaders.push(header);
      continue;
    }

    columns.push(resolved);
  }

  return { columns, unresolvedHeaders };
}

/**
 * แก้ไข header ตัวเดียวให้เป็น ResolvedColumn — รองรับ parent field, child table field และ ID
 * @param client - FrappeClient สำหรับดึง child table meta
 * @param meta - FrappeMeta ของ DocType หลัก
 * @param dataset - DatasetConfig ที่มีการตั้งค่า override
 * @param header - ชื่อ header ใน spreadsheet
 * @returns ResolvedColumn หรือ null ถ้าหา field ไม่เจอ
 */
async function resolveColumn(
  client: FrappeClient,
  meta: FrappeMeta,
  dataset: DatasetConfig,
  header: string,
): Promise<ResolvedColumn | null> {
  const override = dataset.headerFieldOverrides?.[header];
  if (override) {
    return resolveOverride(client, meta, header, override);
  }

  if (header === 'ID') {
    return {
      header,
      kind: 'parent',
      fieldname: 'name',
      fieldtype: 'Data',
    };
  }

  const childMatch = header.match(/^(.*?) \((.*?)\)$/);
  if (childMatch) {
    const [, childLabel, tableLabel] = childMatch;
    const tableField = findField(meta.fields, tableLabel, { tableOnly: true });
    if (!tableField?.options) {
      return null;
    }

    const childMeta = await client.getMeta(tableField.options);
    const childField = findField(childMeta.fields, childLabel);
    if (!childField) {
      return null;
    }

    return {
      header,
      kind: 'child',
      tableFieldname: tableField.fieldname,
      tableLabel: tableField.label ?? tableLabel,
      childDoctype: tableField.options,
      childFieldname: childField.fieldname,
      childFieldtype: childField.fieldtype,
    };
  }

  const field = findField(meta.fields, header);
  if (!field) {
    return null;
  }

  return {
    header,
    kind: 'parent',
    fieldname: field.fieldname,
    fieldtype: field.fieldtype,
  };
}

/**
 * แก้ไข header ตาม override mapping เช่น "fieldname" หรือ "table.child_field"
 * @param client - FrappeClient สำหรับดึง child table meta
 * @param meta - FrappeMeta ของ DocType หลัก
 * @param header - ชื่อ header ต้นทาง
 * @param override - override string เช่น "name" หรือ "items.item_code"
 * @returns ResolvedColumn หรือ null ถ้า field ไม่ถูกต้อง
 */
async function resolveOverride(
  client: FrappeClient,
  meta: FrappeMeta,
  header: string,
  override: string,
): Promise<ResolvedColumn | null> {
  if (!override.includes('.')) {
    const field =
      override === 'name'
        ? { fieldname: 'name', fieldtype: 'Data' }
        : meta.fields.find((candidate) => candidate.fieldname === override);
    if (!field) {
      return null;
    }

    return {
      header,
      kind: 'parent',
      fieldname: field.fieldname,
      fieldtype: field.fieldtype,
    };
  }

  const [tableFieldname, childFieldname] = override.split('.');
  const tableField = meta.fields.find((field) => field.fieldname === tableFieldname);
  if (!tableField?.options) {
    return null;
  }

  const childMeta = await client.getMeta(tableField.options);
  const childField = childMeta.fields.find((field) => field.fieldname === childFieldname);
  if (!childField) {
    return null;
  }

  return {
    header,
    kind: 'child',
    tableFieldname,
    tableLabel: tableField.label ?? tableFieldname,
    childDoctype: tableField.options,
    childFieldname,
    childFieldtype: childField.fieldtype,
  };
}

/**
 * สร้าง map ของ expected records จาก spreadsheet โดยจัดกลุ่มตาม identity key และรองรับ carry-forward
 * @param dataset - DatasetConfig ที่มี identityHeaders และ splitHeaders
 * @param sheet - ข้อมูล spreadsheet ที่อ่านมา
 * @param columns - รายการ ResolvedColumn ที่ map แล้ว
 * @param hasChildColumns - มี child table column อยู่หรือไม่
 * @returns Map ของ identity key ไปยัง ExpectedRecord
 */
function buildExpectedRecords(
  dataset: DatasetConfig,
  sheet: SheetData,
  columns: ResolvedColumn[],
  hasChildColumns: boolean,
): Map<string, ExpectedRecord> {
  const records = new Map<string, ExpectedRecord>();
  const headerIndex = new Map(sheet.headers.map((header, index) => [header, index]));
  const carryForward = new Map<string, unknown>();
  const columnsByHeader = new Map(columns.map((column) => [column.header, column]));
  const childColumns = columns.filter(
    (column): column is ResolvedChildColumn => column.kind === 'child',
  );
  const parentColumns = columns.filter(
    (column): column is ResolvedParentColumn => column.kind === 'parent',
  );
  const hasChildIdentityColumns = dataset.identityHeaders.some(
    (header) => columnsByHeader.get(header)?.kind === 'child',
  );

  for (const rawRow of sheet.rows) {
    if (!rawRow.some((value) => !isBlank(value))) {
      continue;
    }

    if (
      dataset.requiredHeaders?.some((header) =>
        isBlank(rawRow[headerIndex.get(header) ?? -1]),
      )
    ) {
      continue;
    }

    const isContinuation =
      (hasChildColumns || hasChildIdentityColumns) &&
      dataset.identityHeaders.every((header) =>
        isBlank(rawRow[headerIndex.get(header) ?? -1]),
      );

    if (
      !isContinuation &&
      dataset.identityHeaders.every((header) =>
        isBlank(rawRow[headerIndex.get(header) ?? -1]),
      )
    ) {
      continue;
    }

    const effectiveValues = new Map<string, unknown>();
    for (const column of parentColumns) {
      const rawValue = rawRow[headerIndex.get(column.header) ?? -1];
      if (!isBlank(rawValue)) {
        carryForward.set(column.header, rawValue);
        effectiveValues.set(column.header, rawValue);
      } else if (isContinuation) {
        effectiveValues.set(column.header, carryForward.get(column.header) ?? null);
      } else {
        carryForward.delete(column.header);
        effectiveValues.set(column.header, null);
      }
    }

    for (const header of dataset.identityHeaders) {
      const column = columnsByHeader.get(header);
      if (!column || column.kind !== 'child') {
        continue;
      }

      const rawValue = rawRow[headerIndex.get(column.header) ?? -1];
      if (!isBlank(rawValue)) {
        carryForward.set(column.header, rawValue);
      } else if (!isContinuation) {
        carryForward.delete(column.header);
      }
    }

    const keyParts = dataset.identityHeaders.map((header) => {
      const column = columnsByHeader.get(header);
      if (!column) {
        throw new Error(
          `Identity header "${header}" in ${dataset.file} could not be resolved.`,
        );
      }

      if (column.kind === 'parent') {
        return normalizeColumnValue(
          dataset,
          column.header,
          effectiveValues.get(header),
          column.fieldtype,
        );
      }

      const rawValue = rawRow[headerIndex.get(column.header) ?? -1];
      const effectiveValue = !isBlank(rawValue)
        ? rawValue
        : isContinuation
          ? carryForward.get(column.header) ?? null
          : null;
      return normalizeColumnValue(
        dataset,
        column.header,
        effectiveValue,
        column.childFieldtype,
      );
    });
    const key = makeKey(keyParts, dataset.caseInsensitiveIdentity);
    const displayKey = keyParts.map((part) => String(part ?? '')).join(' | ');

    if (!records.has(key)) {
      records.set(key, {
        key,
        displayKey,
        parent: {},
        children: {},
      });
    }

    const record = records.get(key)!;
    for (const column of parentColumns) {
      record.parent[column.fieldname] = normalizeColumnValue(
        dataset,
        column.header,
        effectiveValues.get(column.header),
        column.fieldtype,
      );
    }

    const childColumnsByTable = groupBy(childColumns, (column) => column.tableFieldname);
    for (const [tableFieldname, tableColumns] of childColumnsByTable.entries()) {
      const childRows = expandExpectedChildRows(
        dataset,
        rawRow,
        headerIndex,
        tableColumns,
      );
      if (childRows.length > 0) {
        if (!record.children[tableFieldname]) {
          record.children[tableFieldname] = [];
        }
        record.children[tableFieldname].push(...childRows);
      }
    }
  }

  return records;
}

/**
 * ดึง ResolvedColumn สำหรับ identity headers ตามลำดับที่กำหนดใน config
 * @param dataset - DatasetConfig ที่มี identityHeaders
 * @param columns - รายการ ResolvedColumn ที่ map แล้ว
 * @returns รายการ ResolvedColumn ตาม identity headers
 */
function resolveIdentityColumns(
  dataset: DatasetConfig,
  columns: ResolvedColumn[],
): ResolvedColumn[] {
  return dataset.identityHeaders.map((header) => {
    const column = columns.find((resolvedColumn) => resolvedColumn.header === header);
    if (!column) {
      throw new Error(
        `Identity header "${header}" in ${dataset.file} could not be resolved.`,
      );
    }
    return column;
  });
}

/**
 * ดึง identity keys ทั้งหมดจาก live document — คำนวณ cartesian product ของ child table rows
 * @param liveDoc - document จริงจาก Frappe API
 * @param dataset - DatasetConfig ที่มีการตั้งค่า identity
 * @param identityColumns - รายการ ResolvedColumn สำหรับ identity
 * @param identityHeaders - ชื่อ headers ที่ใช้เป็น identity
 * @param caseInsensitiveIdentity - ไม่สนใจตัวพิมพ์เล็ก/ใหญ่หรือไม่
 * @returns array ของ identity key strings
 */
function extractIdentityKeysFromLiveDoc(
  liveDoc: Record<string, unknown>,
  dataset: DatasetConfig,
  identityColumns: ResolvedColumn[],
  identityHeaders: string[],
  caseInsensitiveIdentity = false,
): string[] {
  const valuesByHeader = new Map<string, NormalizedValue>();
  const childIdentityColumns = identityColumns.filter(
    (column): column is ResolvedChildColumn => column.kind === 'child',
  );

  for (const column of identityColumns) {
    if (column.kind !== 'parent') {
      continue;
    }
    valuesByHeader.set(
      column.header,
      normalizeColumnValue(
        dataset,
        column.header,
        liveDoc[column.fieldname],
        column.fieldtype,
      ),
    );
  }

  let combinations: Array<Map<string, NormalizedValue>> = [new Map(valuesByHeader)];
  const childColumnsByTable = groupBy(childIdentityColumns, (column) => column.tableFieldname);

  for (const [tableFieldname, tableColumns] of childColumnsByTable.entries()) {
    const liveRows = Array.isArray(liveDoc[tableFieldname])
      ? (liveDoc[tableFieldname] as Array<Record<string, unknown>>)
      : [];
    const rowValueMaps = new Map<string, Map<string, NormalizedValue>>();

    if (liveRows.length === 0) {
      const emptyValues = new Map<string, NormalizedValue>();
      for (const column of tableColumns) {
        emptyValues.set(column.header, null);
      }
      rowValueMaps.set(stableStringify(Object.fromEntries(emptyValues)), emptyValues);
    } else {
      for (const row of liveRows) {
        const rowValues = new Map<string, NormalizedValue>();
        for (const column of tableColumns) {
          rowValues.set(
            column.header,
            normalizeColumnValue(
              dataset,
              column.header,
              row[column.childFieldname],
              column.childFieldtype,
            ),
          );
        }
        rowValueMaps.set(stableStringify(Object.fromEntries(rowValues)), rowValues);
      }
    }

    const nextCombinations: Array<Map<string, NormalizedValue>> = [];
    for (const baseValues of combinations) {
      for (const rowValues of rowValueMaps.values()) {
        const merged = new Map(baseValues);
        for (const [header, value] of rowValues.entries()) {
          merged.set(header, value);
        }
        nextCombinations.push(merged);
      }
    }
    combinations = nextCombinations;
  }

  return [
    ...new Set(
      combinations.map((combination) =>
        makeKey(
          identityHeaders.map((header) => combination.get(header) ?? null),
          caseInsensitiveIdentity,
        ),
      ),
    ),
  ];
}

/**
 * ขยายแถว child table ที่คาดหวังจาก raw spreadsheet row — รองรับ multi-value expansion
 * @param dataset - DatasetConfig ที่มีการตั้งค่า splitHeaders
 * @param rawRow - แถวข้อมูลดิบจาก spreadsheet
 * @param headerIndex - map ของ header ไปยัง index
 * @param tableColumns - รายการ ResolvedChildColumn ใน child table เดียวกัน
 * @returns array ของ normalized child row records
 */
function expandExpectedChildRows(
  dataset: DatasetConfig,
  rawRow: unknown[],
  headerIndex: Map<string, number>,
  tableColumns: ResolvedChildColumn[],
): Array<Record<string, NormalizedValue>> {
  const valueOptions = tableColumns.map((column) => {
    const rawValue = rawRow[headerIndex.get(column.header) ?? -1];
    return {
      column,
      values: expandExpectedValues(
        dataset,
        column.header,
        rawValue,
        column.childFieldtype,
        dataset.splitHeaders?.[column.header],
      ),
    };
  });

  const expandedRows: Array<Record<string, NormalizedValue>> = [];

  const walk = (
    index: number,
    currentRow: Record<string, NormalizedValue>,
    hasValue: boolean,
  ) => {
    if (index >= valueOptions.length) {
      if (hasValue) {
        expandedRows.push(currentRow);
      }
      return;
    }

    const { column, values } = valueOptions[index];
    for (const value of values) {
      walk(
        index + 1,
        {
          ...currentRow,
          [column.childFieldname]: value,
        },
        hasValue || value !== null,
      );
    }
  };

  walk(0, {}, false);
  return expandedRows;
}

/**
 * ขยายค่าที่คาดหวังจาก raw value — แยกด้วย delimiter ถ้ามี splitHeaders config
 * @param dataset - DatasetConfig ที่มีการตั้งค่า value transforms
 * @param header - ชื่อ header
 * @param rawValue - ค่าดิบจาก spreadsheet
 * @param fieldtype - ประเภท field ของ Frappe
 * @param splitDelimiter - delimiter สำหรับแยกค่า เช่น ","
 * @returns array ของ NormalizedValue ที่แยกแล้ว
 */
function expandExpectedValues(
  dataset: DatasetConfig,
  header: string,
  rawValue: unknown,
  fieldtype: string | undefined,
  splitDelimiter?: string,
): NormalizedValue[] {
  if (splitDelimiter && typeof rawValue === 'string' && rawValue.includes(splitDelimiter)) {
    const parts = rawValue
      .split(splitDelimiter)
      .map((part) => part.trim())
      .filter((part) => part !== '');
    if (parts.length > 0) {
      return parts.map((part) =>
        normalizeColumnValue(dataset, header, part, fieldtype),
      );
    }
  }

  return [normalizeColumnValue(dataset, header, rawValue, fieldtype)];
}

/**
 * เปรียบเทียบ flat record (ไม่มี child table) ระหว่าง expected กับ live row
 * @param dataset - DatasetConfig สำหรับดึงการตั้งค่า normalize
 * @param expected - ExpectedRecord ที่คาดหวัง
 * @param liveRow - document จริงจาก Frappe
 * @param columns - รายการ ResolvedColumn ที่ map แล้ว
 * @param report - DatasetReport สำหรับเก็บ field mismatches
 */
function compareFlatRecord(
  dataset: DatasetConfig,
  expected: ExpectedRecord,
  liveRow: Record<string, unknown>,
  columns: ResolvedColumn[],
  report: DatasetReport,
) {
  for (const column of columns) {
    if (column.kind !== 'parent') {
      continue;
    }
    const expectedValue = expected.parent[column.fieldname] ?? null;
    const actualValue = normalizeColumnValue(
      dataset,
      column.header,
      liveRow[column.fieldname],
      column.fieldtype,
    );
    if (!valuesEqual(expectedValue, actualValue)) {
      report.fieldMismatches.push({
        key: expected.displayKey,
        field: column.header,
        expected: expectedValue,
        actual: actualValue,
      });
    }
  }
}

/**
 * เปรียบเทียบ grouped record (มี child tables) ระหว่าง expected กับ live doc แบบ multiset per table
 * @param dataset - DatasetConfig สำหรับดึงการตั้งค่า normalize
 * @param expected - ExpectedRecord ที่คาดหวัง
 * @param liveDoc - document จริงจาก Frappe พร้อม child tables
 * @param columns - รายการ ResolvedColumn ที่ map แล้ว
 * @param report - DatasetReport สำหรับเก็บ mismatches
 */
function compareGroupedRecord(
  dataset: DatasetConfig,
  expected: ExpectedRecord,
  liveDoc: Record<string, unknown>,
  columns: ResolvedColumn[],
  report: DatasetReport,
) {
  const parentColumns = columns.filter(
    (column): column is ResolvedParentColumn => column.kind === 'parent',
  );
  const childColumns = columns.filter(
    (column): column is ResolvedChildColumn => column.kind === 'child',
  );

  for (const column of parentColumns) {
    const expectedValue = expected.parent[column.fieldname] ?? null;
    const actualValue = normalizeColumnValue(
      dataset,
      column.header,
      liveDoc[column.fieldname],
      column.fieldtype,
    );
    if (!valuesEqual(expectedValue, actualValue)) {
      report.fieldMismatches.push({
        key: expected.displayKey,
        field: column.header,
        expected: expectedValue,
        actual: actualValue,
      });
    }
  }

  const childColumnsByTable = groupBy(childColumns, (column) => column.tableFieldname);
  for (const [tableFieldname, tableColumns] of childColumnsByTable.entries()) {
    const expectedRows = expected.children[tableFieldname] ?? [];
    const liveRows = Array.isArray(liveDoc[tableFieldname])
      ? (liveDoc[tableFieldname] as Array<Record<string, unknown>>)
      : [];

    const expectedCounter = new Map<string, number>();
    const liveCounter = new Map<string, number>();
    const signatureDisplay = new Map<string, string>();

    for (const row of expectedRows) {
      const signaturePayload = pickChildFields(row, tableColumns);
      const signature = stableStringify(signaturePayload);
      signatureDisplay.set(signature, signature);
      expectedCounter.set(signature, (expectedCounter.get(signature) ?? 0) + 1);
    }

    for (const row of liveRows) {
      const signaturePayload: Record<string, NormalizedValue> = {};
      for (const column of tableColumns) {
        signaturePayload[column.childFieldname] = normalizeColumnValue(
          dataset,
          column.header,
          row[column.childFieldname],
          column.childFieldtype,
        );
      }
      const signature = stableStringify(signaturePayload);
      signatureDisplay.set(signature, signature);
      liveCounter.set(signature, (liveCounter.get(signature) ?? 0) + 1);
    }

    for (const signature of new Set([...expectedCounter.keys(), ...liveCounter.keys()])) {
      const expectedCount = expectedCounter.get(signature) ?? 0;
      const liveCount = liveCounter.get(signature) ?? 0;
      if (expectedCount > liveCount) {
        for (let index = 0; index < expectedCount - liveCount; index += 1) {
          report.childTableMismatches.push({
            key: expected.displayKey,
            field: tableFieldname,
            expected: signatureDisplay.get(signature) ?? signature,
            actual: null,
          });
        }
      }
      if (liveCount > expectedCount) {
        for (let index = 0; index < liveCount - expectedCount; index += 1) {
          report.childTableMismatches.push({
            key: expected.displayKey,
            field: tableFieldname,
            expected: null,
            actual: signatureDisplay.get(signature) ?? signature,
          });
        }
      }
    }
  }
}

/**
 * เลือกเฉพาะ child field ที่อยู่ใน tableColumns จาก child row
 * @param row - record ของ child row
 * @param columns - รายการ ResolvedChildColumn ที่ต้องการ pick
 * @returns record ที่มีเฉพาะ field ที่อยู่ใน columns
 */
function pickChildFields(
  row: Record<string, NormalizedValue>,
  columns: ResolvedChildColumn[],
): Record<string, NormalizedValue> {
  const picked: Record<string, NormalizedValue> = {};
  for (const column of columns) {
    picked[column.childFieldname] = row[column.childFieldname] ?? null;
  }
  return picked;
}

/**
 * ค้นหา FrappeField ที่ตรงกับ header โดยใช้ fuzzy matching กับ label, fieldname, options
 * @param fields - รายการ FrappeField จาก meta
 * @param header - ชื่อ header ที่ต้องการหา
 * @param options - ตัวเลือกเสริม เช่น tableOnly เพื่อกรองเฉพาะ Table field
 * @returns FrappeField ที่ตรงที่สุด หรือ undefined
 */
function findField(
  fields: FrappeField[],
  header: string,
  options?: { tableOnly?: boolean },
): FrappeField | undefined {
  const candidates = options?.tableOnly
    ? fields.filter((field) =>
        ['Table', 'Table MultiSelect'].includes(field.fieldtype ?? ''),
      )
    : fields;
  const headerVariants = buildSearchVariants(header);
  const scored = candidates
    .map((field) => {
      const fieldVariants = [
        ...buildSearchVariants(field.label ?? ''),
        ...buildSearchVariants(field.fieldname),
        ...buildSearchVariants(field.options ?? ''),
      ];
      return {
        field,
        score: getVariantMatchScore(headerVariants, fieldVariants),
      };
    })
    .filter((entry) => entry.score > 0)
    .sort((left, right) => right.score - left.score);

  if (scored.length === 0) {
    return undefined;
  }

  if (scored.length > 1 && scored[0].score === scored[1].score && scored[0].score >= 2) {
    return undefined;
  }

  return scored[0].field;
}

/**
 * สร้าง search variants สำหรับ fuzzy matching — เช่น ตัด suffix "name", "code", "number"
 * @param value - ข้อความต้นทาง
 * @returns array ของ variant strings
 */
function buildSearchVariants(value: string): string[] {
  const normalized = normalizeToken(value);
  const variants = new Set<string>();

  if (normalized) {
    variants.add(normalized);
  }

  for (const suffix of ['name', 'code', 'number', 'no']) {
    if (normalized.endsWith(suffix) && normalized.length > suffix.length) {
      variants.add(normalized.slice(0, -suffix.length));
    }
  }

  return [...variants];
}

/**
 * คำนวณคะแนนความใกล้เคียงระหว่าง header variants กับ field variants
 * @param left - search variants ของ header
 * @param right - search variants ของ field
 * @returns score 0-4 โดย 4 = exact match, 3 = suffix match, 1 = substring match
 */
function getVariantMatchScore(left: string[], right: string[]): number {
  for (const leftValue of left) {
    for (const rightValue of right) {
      if (!leftValue || !rightValue) {
        continue;
      }
      if (leftValue === rightValue) {
        return 4;
      }
      if (
        leftValue.endsWith(rightValue) ||
        rightValue.endsWith(leftValue)
      ) {
        return 3;
      }
      if (leftValue.includes(rightValue) || rightValue.includes(leftValue)) {
        return 1;
      }
    }
  }
  return 0;
}

/**
 * ทำ normalize string โดยแปลงเป็นตัวพิมพ์เล็กและลบอักขระที่ไม่ใช่ตัวอักษร/ตัวเลข
 * @param value - ข้อความต้นทาง
 * @returns string ที่ normalize แล้ว
 */
function normalizeToken(value: string): string {
  return value.toLowerCase().replace(/[^\p{L}\p{N}]+/gu, '');
}

/**
 * แปลงค่าดิบเป็น NormalizedValue ตาม Frappe fieldtype เช่น Check → boolean, Currency → number
 * @param value - ค่าดิบที่ต้องการ normalize
 * @param fieldtype - ประเภท field ของ Frappe เช่น "Check", "Currency", "Int"
 * @returns ค่าที่ normalize แล้ว
 */
function normalizeValue(value: unknown, fieldtype?: string): NormalizedValue {
  if (isBlank(value)) {
    return null;
  }

  if (value instanceof Date) {
    return toRoundedDateString(value);
  }

  const type = (fieldtype ?? '').toLowerCase();

  if (type === 'check') {
    if (typeof value === 'boolean') {
      return value;
    }
    if (typeof value === 'number') {
      return value !== 0;
    }
    if (typeof value === 'string') {
      return ['1', 'true', 'yes'].includes(value.trim().toLowerCase());
    }
  }

  if (['currency', 'float', 'percent', 'int', 'long int'].includes(type)) {
    const numeric = Number(value);
    if (Number.isFinite(numeric)) {
      return numeric;
    }
  }

  if (typeof value === 'number') {
    return String(value);
  }

  if (typeof value === 'boolean') {
    return value;
  }

  return String(value).trim().replace(/\r\n/g, '\n');
}

/**
 * normalize ค่าของ column ตาม header และ fieldtype แล้ว apply valueTransforms ถ้ามี
 * @param dataset - DatasetConfig ที่มีการตั้งค่า valueTransforms
 * @param header - ชื่อ header
 * @param value - ค่าที่ต้องการ normalize
 * @param fieldtype - ประเภท field ของ Frappe
 * @returns ค่าที่ normalize และ transform แล้ว
 */
function normalizeColumnValue(
  dataset: DatasetConfig,
  header: string,
  value: unknown,
  fieldtype?: string,
): NormalizedValue {
  let normalized = normalizeValue(value, fieldtype);
  const transformSpec = dataset.valueTransforms?.[header];
  if (!transformSpec) {
    return normalized;
  }

  for (const transform of transformSpec.split('|').map((part) => part.trim()).filter(Boolean)) {
    normalized = applyValueTransform(normalized, transform);
  }

  return normalized;
}

/**
 * apply transform ตัวเดียว เช่น trim_company_suffix, strip_leading_zeros, phone_digits ฯลฯ
 * @param value - NormalizedValue ที่จะ transform
 * @param transform - ชื่อ transform เช่น "trim_company_suffix"
 * @returns ค่าที่ transform แล้ว
 */
function applyValueTransform(
  value: NormalizedValue,
  transform: string,
): NormalizedValue {
  if (value === null) {
    return null;
  }

  switch (transform) {
    case 'trim_company_suffix':
      return typeof value === 'string'
        ? value.replace(/\s+-\s+[A-Z0-9]+$/u, '').trim()
        : value;
    case 'strip_leading_zeros':
      if (typeof value !== 'string') {
        return value;
      }
      if (!/^\d+$/u.test(value)) {
        return value;
      }
      return value.replace(/^0+(?=\d)/u, '');
    case 'collapse_whitespace':
      return typeof value === 'string'
        ? value.replace(/\s+/gu, ' ').trim()
        : value;
    case 'phone_digits':
      return typeof value === 'string'
        ? value.replace(/[^\d]+/gu, '')
        : value;
    case 'dash_to_null':
      return typeof value === 'string' && value.trim() === '-'
        ? null
        : value;
    case 'country_alias':
      if (typeof value !== 'string') {
        return value;
      }
      if (
        ['south korea', 'korea, republic of'].includes(value.trim().toLowerCase())
      ) {
        return 'south korea';
      }
      return value.trim().toLowerCase();
    case 'report_type_alias':
      if (typeof value !== 'string') {
        return value;
      }
      if (
        ['profit and loss', 'profit & loss'].includes(value.trim().toLowerCase())
      ) {
        return 'profit and loss';
      }
      return value.trim().toLowerCase();
    default:
      return value;
  }
}

/**
 * สร้าง identity key string จาก array ของ value parts โดยใช้ stable JSON stringify
 * @param parts - array ของ NormalizedValue ที่จะรวมเป็น key
 * @param caseInsensitive - ถ้า true จะแปลง string เป็นตัวพิมพ์เล็กก่อนสร้าง key
 * @returns identity key string
 */
function makeKey(
  parts: Array<NormalizedValue>,
  caseInsensitive = false,
): string {
  if (!caseInsensitive) {
    return stableStringify(parts);
  }

  return stableStringify(
    parts.map((part) =>
      typeof part === 'string' ? part.toLowerCase() : part,
    ),
  );
}

/**
 * แปลง value เป็น JSON string โดยเรียง key อย่างสม่ำเสมอ (deterministic serialization)
 * @param value - ค่าที่ต้องการ stringify
 * @returns JSON string ที่เรียง key แล้ว
 */
function stableStringify(value: unknown): string {
  return JSON.stringify(sortValue(value));
}

/**
 * เรียง object keys ตาม locale order แบบ recursive เพื่อให้ JSON.stringify ออกมาสม่ำเสมอ
 * @param value - ค่าที่ต้องการ sort
 * @returns ค่าที่เรียง key แล้ว
 */
function sortValue(value: unknown): unknown {
  if (Array.isArray(value)) {
    return value.map((entry) => sortValue(entry));
  }
  if (value && typeof value === 'object') {
    return Object.fromEntries(
      Object.entries(value as Record<string, unknown>)
        .sort(([left], [right]) => left.localeCompare(right))
        .map(([key, childValue]) => [key, sortValue(childValue)]),
    );
  }
  return value;
}

/**
 * เปรียบเทียบ NormalizedValue สองค่าว่าเท่ากันหรือไม่ — รองรับ null/false/0 เป็นค่าเทียบเท่า และ string-number coercion
 * @param left - ค่าฝั่งซ้าย
 * @param right - ค่าฝั่งขวา
 * @returns true ถ้าเท่ากัน
 */
function valuesEqual(left: NormalizedValue, right: NormalizedValue): boolean {
  if (left === right) {
    return true;
  }

  if (left === null && right === false) {
    return true;
  }

  if (right === null && left === false) {
    return true;
  }

  if (left === null && right === 0) {
    return true;
  }

  if (right === null && left === 0) {
    return true;
  }

  if (
    typeof left === 'number' &&
    typeof right === 'string' &&
    right.trim() !== '' &&
    Number.isFinite(Number(right))
  ) {
    return left === Number(right);
  }

  if (
    typeof right === 'number' &&
    typeof left === 'string' &&
    left.trim() !== '' &&
    Number.isFinite(Number(left))
  ) {
    return right === Number(left);
  }

  if (typeof left === 'string' && typeof right === 'string') {
    return left.trim().toLowerCase() === right.trim().toLowerCase();
  }

  return stableStringify(left) === stableStringify(right);
}

/**
 * ตรวจสอบว่าค่าเป็น blank (null, undefined หรือ string ว่าง) หรือไม่
 * @param value - ค่าที่ต้องการตรวจสอบ
 * @returns true ถ้าเป็น blank
 */
function isBlank(value: unknown): boolean {
  return value === null || value === undefined || String(value).trim() === '';
}

/**
 * จัดกลุ่ม items ตาม key ที่ได้จาก getKey function
 * @param items - รายการที่ต้องการจัดกลุ่ม
 * @param getKey - function สำหรับดึง group key จากแต่ละ item
 * @returns Map ของ key ไปยัง array ของ items
 */
function groupBy<T>(
  items: T[],
  getKey: (item: T) => string,
): Map<string, T[]> {
  const grouped = new Map<string, T[]>();
  for (const item of items) {
    const key = getKey(item);
    if (!grouped.has(key)) {
      grouped.set(key, []);
    }
    grouped.get(key)!.push(item);
  }
  return grouped;
}

/**
 * แปลง Date เป็น string รูปแบบ YYYY-MM-DD โดยปัดเศษถ้าเวลาใกล้เที่ยงคืน
 * @param value - Date object ที่ต้องการแปลง
 * @returns date string ในรูปแบบ YYYY-MM-DD
 */
function toRoundedDateString(value: Date): string {
  const rounded = new Date(value.getTime());
  if (
    rounded.getHours() === 23 &&
    rounded.getMinutes() >= 59
  ) {
    rounded.setDate(rounded.getDate() + 1);
  }

  const year = rounded.getFullYear();
  const month = String(rounded.getMonth() + 1).padStart(2, '0');
  const day = String(rounded.getDate()).padStart(2, '0');
  return `${year}-${month}-${day}`;
}

/**
 * เขียน summary files (JSON + Markdown) ไปยัง output directory ภายใต้ playwright-report/data-diff
 * @param reports - รายการ DatasetReport ทั้งหมด
 * @returns path ของ output directory
 */
function writeSummaryFiles(reports: DatasetReport[]): string {
  const outputDir = path.resolve(
    process.cwd(),
    'playwright-report',
    'data-diff',
    new Date().toISOString().replace(/[:.]/g, '-'),
  );
  mkdirSync(outputDir, { recursive: true });

  writeFileSync(
    path.join(outputDir, 'summary.json'),
    `${JSON.stringify({ generatedAt: new Date().toISOString(), reports }, null, 2)}\n`,
    'utf-8',
  );

  const markdown = [
    '# Master Data Comparison Summary',
    '',
    ...reports.flatMap((report) => [
      `## ${report.file} -> ${report.doctype}`,
      '',
      ...(report.source ? [`- Source: ${report.source}`] : []),
      `- Expected records: ${report.expectedRecords}`,
      `- Errors: ${report.errors.length}`,
      `- Unresolved headers: ${report.unresolvedHeaders.length}`,
      `- Missing records: ${report.missingRecords.length}`,
      `- Extra records: ${report.extraRecords.length}`,
      `- Duplicate live records: ${report.duplicateLiveRecords.length}`,
      `- Field mismatches: ${report.fieldMismatches.length}`,
      `- Child table mismatches: ${report.childTableMismatches.length}`,
      '',
    ]),
  ].join('\n');

  writeFileSync(path.join(outputDir, 'summary.md'), `${markdown}\n`, 'utf-8');
  return outputDir;
}
