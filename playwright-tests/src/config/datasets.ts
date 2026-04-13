import { existsSync, readFileSync } from 'node:fs';
import path from 'node:path';

export type ComparisonMode = 'record' | 'multiset';
export type MasterSourceFormat = 'auto' | 'csv' | 'xlsx';

export interface DatasetConfig {
  file: string;
  doctype: string;
  identityHeaders: string[];
  requiredHeaders?: string[];
  source?: string;
  worksheet?: number | string;
  format?: MasterSourceFormat;
  enabled?: boolean;
  comparison?: ComparisonMode;
  compareExtra?: boolean;
  caseInsensitiveIdentity?: boolean;
  liveFilters?: Record<string, string | number | boolean>;
  ignoreHeaders?: string[];
  headerFieldOverrides?: Record<string, string>;
  splitHeaders?: Record<string, string>;
  valueTransforms?: Record<string, string>;
  notes?: string;
}

export const DEFAULT_DATASETS_CONFIG_PATH = path.resolve(
  process.cwd(),
  process.env.MASTER_DATASETS_CONFIG ?? 'master-data.datasets.json',
);

export function loadDatasets(
  configPath = DEFAULT_DATASETS_CONFIG_PATH,
): DatasetConfig[] {
  if (!existsSync(configPath)) {
    throw new Error(
      `Dataset config file not found at "${configPath}". Set MASTER_DATASETS_CONFIG or create master-data.datasets.json.`,
    );
  }

  const content = readFileSync(configPath, 'utf-8');
  const raw = JSON.parse(content) as unknown;

  if (!Array.isArray(raw)) {
    throw new Error(`Dataset config "${configPath}" must be a JSON array.`);
  }

  return raw
    .map((entry, index) => normalizeDatasetConfig(entry, index, configPath))
    .filter((dataset) => dataset.enabled !== false);
}

function normalizeDatasetConfig(
  entry: unknown,
  index: number,
  configPath: string,
): DatasetConfig {
  if (!entry || typeof entry !== 'object') {
    throw new Error(
      `Dataset config "${configPath}" entry #${index + 1} must be an object.`,
    );
  }

  const dataset = entry as Record<string, unknown>;
  const file = asRequiredString(dataset.file, 'file', index, configPath);
  const doctype = asRequiredString(dataset.doctype, 'doctype', index, configPath);
  const identityHeaders = asStringArray(
    dataset.identityHeaders,
    'identityHeaders',
    index,
    configPath,
  );

  return {
    file,
    doctype,
    identityHeaders,
    source: asOptionalString(dataset.source),
    worksheet: asOptionalWorksheet(dataset.worksheet, index, configPath),
    format: asOptionalFormat(dataset.format, index, configPath),
    enabled: asOptionalBoolean(dataset.enabled),
    comparison: asOptionalComparison(dataset.comparison, index, configPath),
    compareExtra: asOptionalBoolean(dataset.compareExtra),
    caseInsensitiveIdentity: asOptionalBoolean(dataset.caseInsensitiveIdentity),
    liveFilters: asOptionalPrimitiveRecord(dataset.liveFilters, index, configPath),
    requiredHeaders: asOptionalRequiredHeaders(dataset.requiredHeaders, index, configPath),
    ignoreHeaders: asOptionalStringArray(dataset.ignoreHeaders, index, configPath),
    headerFieldOverrides: asOptionalStringRecord(
      dataset.headerFieldOverrides,
      index,
      configPath,
    ),
    splitHeaders: asOptionalStringRecord(
      dataset.splitHeaders,
      index,
      configPath,
    ),
    valueTransforms: asOptionalStringRecord(
      dataset.valueTransforms,
      index,
      configPath,
      'valueTransforms',
    ),
    notes: asOptionalString(dataset.notes),
  };
}

function asRequiredString(
  value: unknown,
  fieldName: string,
  index: number,
  configPath: string,
): string {
  if (typeof value !== 'string' || !value.trim()) {
    throw new Error(
      `Dataset config "${configPath}" entry #${index + 1} requires a non-empty "${fieldName}" string.`,
    );
  }

  return value.trim();
}

function asOptionalString(value: unknown): string | undefined {
  if (typeof value !== 'string' || !value.trim()) {
    return undefined;
  }

  return value.trim();
}

function asStringArray(
  value: unknown,
  fieldName: string,
  index: number,
  configPath: string,
): string[] {
  if (!Array.isArray(value) || value.length === 0) {
    throw new Error(
      `Dataset config "${configPath}" entry #${index + 1} requires "${fieldName}" as a non-empty string array.`,
    );
  }

  return value.map((item) => {
    if (typeof item !== 'string' || !item.trim()) {
      throw new Error(
        `Dataset config "${configPath}" entry #${index + 1} has invalid "${fieldName}" value.`,
      );
    }
    return item.trim();
  });
}

function asOptionalStringArray(
  value: unknown,
  index: number,
  configPath: string,
): string[] | undefined {
  if (value === undefined) {
    return undefined;
  }

  return asStringArray(value, 'ignoreHeaders', index, configPath);
}

function asOptionalRequiredHeaders(
  value: unknown,
  index: number,
  configPath: string,
): string[] | undefined {
  if (value === undefined) {
    return undefined;
  }

  return asStringArray(value, 'requiredHeaders', index, configPath);
}

function asOptionalWorksheet(
  value: unknown,
  index: number,
  configPath: string,
): number | string | undefined {
  if (value === undefined || value === null || value === '') {
    return undefined;
  }

  if (typeof value === 'string' && value.trim()) {
    return value.trim();
  }

  if (typeof value === 'number' && Number.isInteger(value) && value >= 0) {
    return value;
  }

  throw new Error(
    `Dataset config "${configPath}" entry #${index + 1} has invalid "worksheet". Use sheet name or zero-based index.`,
  );
}

function asOptionalFormat(
  value: unknown,
  index: number,
  configPath: string,
): MasterSourceFormat | undefined {
  if (value === undefined) {
    return undefined;
  }

  if (value === 'auto' || value === 'csv' || value === 'xlsx') {
    return value;
  }

  throw new Error(
    `Dataset config "${configPath}" entry #${index + 1} has invalid "format". Use "auto", "csv", or "xlsx".`,
  );
}

function asOptionalComparison(
  value: unknown,
  index: number,
  configPath: string,
): ComparisonMode | undefined {
  if (value === undefined) {
    return undefined;
  }

  if (value === 'record' || value === 'multiset') {
    return value;
  }

  throw new Error(
    `Dataset config "${configPath}" entry #${index + 1} has invalid "comparison". Use "record" or "multiset".`,
  );
}

function asOptionalBoolean(value: unknown): boolean | undefined {
  if (typeof value !== 'boolean') {
    return undefined;
  }

  return value;
}

function asOptionalStringRecord(
  value: unknown,
  index: number,
  configPath: string,
  fieldName = 'headerFieldOverrides',
): Record<string, string> | undefined {
  if (value === undefined) {
    return undefined;
  }

  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    throw new Error(
      `Dataset config "${configPath}" entry #${index + 1} has invalid "${fieldName}".`,
    );
  }

  const output: Record<string, string> = {};
  for (const [key, rawValue] of Object.entries(value)) {
    if (typeof rawValue !== 'string' || !rawValue.trim()) {
      throw new Error(
        `Dataset config "${configPath}" entry #${index + 1} has invalid ${fieldName} value for "${key}".`,
      );
    }
    output[key] = rawValue.trim();
  }

  return output;
}

function asOptionalPrimitiveRecord(
  value: unknown,
  index: number,
  configPath: string,
): Record<string, string | number | boolean> | undefined {
  if (value === undefined) {
    return undefined;
  }

  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    throw new Error(
      `Dataset config "${configPath}" entry #${index + 1} has invalid "liveFilters".`,
    );
  }

  const output: Record<string, string | number | boolean> = {};
  for (const [key, rawValue] of Object.entries(value)) {
    if (
      typeof rawValue !== 'string' &&
      typeof rawValue !== 'number' &&
      typeof rawValue !== 'boolean'
    ) {
      throw new Error(
        `Dataset config "${configPath}" entry #${index + 1} has invalid liveFilters value for "${key}".`,
      );
    }
    output[key] = rawValue;
  }

  return output;
}
