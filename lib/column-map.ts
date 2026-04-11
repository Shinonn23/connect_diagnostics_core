/** แมป Excel column (หรือหลาย column) ไปยัง API field พร้อม comparison strategies เพิ่มเติม */
  export interface FieldMapping {
  excel: string | string[];
  api: string;
  ignoreCase?: boolean;
  fuzzyMatch?: 'strip-cd' | 'strip-parent' | 'strip-company-suffix' | 'strip-tax-suffix';
  booleanField?: boolean;
  countryAlias?: boolean;
  isFullName?: boolean;
  firstNameOnly?: boolean;
  skipWhen?: (apiRec: Record<string, any>) => boolean;
}

/** configuration สมบูรณ์สำหรับ validate Excel sheet เดียวกับ Frappe DocType */
export interface SheetConfig {
  sheetName: string;
  doctype: string;
  label: string;
  keyExcel: string | string[];
  keyApi: string;
  keyIgnoreCase?: boolean;
  keyFuzzyMatch?: 'strip-cd' | 'strip-company-suffix' | 'strip-tax-suffix' | 'float-to-string' | 'account-number';
  fields: FieldMapping[];
  compositeKey?: (row: Record<string, any>) => string;
  lookupKey?: string;
  filters?: Record<string, any>;
  keyExtractor?: (val: string) => string;
}

/** รายการหลักของ sheet-to-doctype validation configurations ที่ใช้โดย validator */
export const SHEET_CONFIGS: SheetConfig[] = [
  {
    sheetName: 'Companies',
    doctype: 'Company',
    label: 'Companies',
    keyExcel: 'Company',
    keyApi: 'company_name',
    keyIgnoreCase: true,
    fields: [
      { excel: 'Company', api: 'company_name', ignoreCase: true },
      { excel: 'Abbr', api: 'abbr' },
      { excel: 'Default Currency', api: 'default_currency' },
      { excel: 'Country', api: 'country' },
    ],
  },
  {
    sheetName: 'Customers',
    doctype: 'Customer',
    label: 'Customers',
    keyExcel: ['ID', 'Customer Name'],
    keyApi: 'name',
    fields: [
      { excel: 'Customer Name', api: 'customer_name' },
      { excel: 'Customer Type', api: 'customer_type', ignoreCase: true },
      { excel: 'Customer Group', api: 'customer_group' },
      { excel: 'Territory', api: 'territory', ignoreCase: true },
      { excel: 'Disabled', api: 'disabled', booleanField: true },
    ],
  },
  {
    sheetName: 'Suppliers',
    doctype: 'Supplier',
    label: 'Suppliers',
    keyExcel: ['CD ID', 'Supplier Name'],
    keyApi: 'name',
    fields: [
      { excel: 'Supplier Name', api: 'supplier_name' },
      { excel: 'Supplier Group', api: 'supplier_group' },
      { excel: 'Country', api: 'country', countryAlias: true },
      { excel: 'Disabled', api: 'disabled', booleanField: true },
    ],
  },
  {
    sheetName: 'Items',
    doctype: 'Item',
    label: 'Items',
    keyExcel: ['ID', 'CD Item Code'],
    keyApi: 'name',
    fields: [
      { excel: 'Item Name (40 Char)', api: 'item_name' },
      { excel: 'Item Group', api: 'item_group' },
      { excel: 'Default Unit of Measure', api: 'stock_uom', ignoreCase: true },
      { excel: 'Maintain Stock', api: 'is_stock_item', booleanField: true },
      { excel: 'Disabled', api: 'disabled', booleanField: true },
      { excel: 'Has Batch No', api: 'has_batch_no', booleanField: true, skipWhen: (rec) => !rec.is_stock_item },
      { excel: 'Has Serial No', api: 'has_serial_no', booleanField: true, skipWhen: (rec) => !rec.is_stock_item },
      { excel: 'Brand', api: 'brand' },
    ],
  },
  {
    sheetName: 'Employees',
    doctype: 'Employee',
    label: 'Employees',
    keyExcel: 'EmployeeID',
    keyApi: 'name',
    fields: [
      { excel: ['EmployeeNameEN', 'EmployeeSurnameEN'], api: 'employee_name', isFullName: true, firstNameOnly: true },
      { excel: 'Department', api: 'department', fuzzyMatch: 'strip-cd' },
      { excel: 'Employment Type', api: 'employment_type' },
      { excel: 'Company', api: 'company' },
      { excel: 'Gender', api: 'gender' },
    ],
  },
  {
    sheetName: 'Warehouses',
    doctype: 'Warehouse',
    label: 'Warehouses',
    keyExcel: 'Warehouse Name',
    keyApi: 'warehouse_name',
    fields: [
      { excel: 'Warehouse Name', api: 'warehouse_name' },
      { excel: 'Company', api: 'company' },
      { excel: 'Warehouse Type', api: 'warehouse_type' },
    ],
  },
  {
    sheetName: 'Item_Groups',
    doctype: 'Item Group',
    label: 'Item Groups',
    keyExcel: 'Item Group Name',
    keyApi: 'name',
    fields: [
      { excel: 'Item Group Name', api: 'item_group_name' },
      { excel: 'Parent Item Group', api: 'parent_item_group' },
      { excel: 'Is Group', api: 'is_group', booleanField: true },
    ],
  },
  {
    sheetName: 'Customer_Groups',
    doctype: 'Customer Group',
    label: 'Customer Groups',
    keyExcel: 'Customer Group Name',
    keyApi: 'name',
    fields: [
      { excel: 'Customer Group Name', api: 'customer_group_name' },
      { excel: 'Parent Customer Group', api: 'parent_customer_group' },
    ],
  },
  {
    sheetName: 'Supplier_Groups',
    doctype: 'Supplier Group',
    label: 'Supplier Groups',
    keyExcel: 'Supplier Group',
    keyApi: 'name',
    fields: [
      { excel: 'Supplier Group', api: 'supplier_group_name' },
    ],
  },
  {
    sheetName: 'Territories',
    doctype: 'Territory',
    label: 'Territories',
    keyExcel: 'Territory',
    keyApi: 'name',
    fields: [
      { excel: 'Territory', api: 'territory_name' },
    ],
  },
  {
    sheetName: 'Departments',
    doctype: 'Department',
    label: 'Departments',
    keyExcel: 'Department Name',
    keyApi: 'name',
    keyFuzzyMatch: 'strip-cd',
    fields: [
      { excel: 'Department Name', api: 'department_name', fuzzyMatch: 'strip-cd' },
      { excel: 'Company', api: 'company' },
    ],
  },
  {
    sheetName: 'UOMs',
    doctype: 'UOM',
    label: 'UOMs',
    keyExcel: ['new name', 'old name'],
    keyApi: 'name',
    keyIgnoreCase: true,
    fields: [
      { excel: ['new name', 'old name'], api: 'uom_name', ignoreCase: true },
    ],
  },
  {
    sheetName: 'Currencies',
    doctype: 'Currency',
    label: 'Currencies',
    keyExcel: 'currency_code',
    keyApi: 'name',
    fields: [
      { excel: 'currency_code', api: 'currency_name' },
    ],
  },
  {
    sheetName: 'Brands',
    doctype: 'Brand',
    label: 'Brands',
    keyExcel: 'Brand',
    keyApi: 'name',
    fields: [],
  },
  {
    sheetName: 'Accounts New',
    doctype: 'Account',
    label: 'Accounts',
    keyExcel: ['Account Number', 'Account Name'],
    keyApi: 'name',
    keyExtractor: (val: string) => val.split(' - ')[0].trim(),
    filters: { company: 'Connect Diagnostics' },
    fields: [
      { excel: 'Account Name', api: 'account_name' },
      { excel: 'Root Type', api: 'root_type' },
      { excel: 'Is Group', api: 'is_group', booleanField: true },
      { excel: 'Account Type', api: 'account_type' },
      { excel: 'Company', api: 'company' },
    ],
  },
  {
    sheetName: 'Item_Prices',
    doctype: 'Item Price',
    label: 'Item Prices',
    keyExcel: 'Item Code',
    keyApi: 'item_code',
    compositeKey: (row: Record<string, any>) =>
      `${row['Item Code']}|${row['Price List']}`,
    fields: [
      { excel: 'Price List', api: 'price_list' },
      { excel: ['Price List Rate', 'Rate'], api: 'price_list_rate' },
    ],
  },
  {
    sheetName: 'Tax_Withholding_Categories',
    doctype: 'Tax Withholding Category',
    label: 'Tax Withholding Categories',
    keyExcel: 'Category Name',
    keyApi: 'name',
    fields: [
      { excel: 'Category Name', api: 'name' },
      { excel: 'Round Off Tax Amount', api: 'round_off_tax_amount', booleanField: true },
    ],
  },
  {
    sheetName: 'Item_Tax_Templates',
    doctype: 'Item Tax Template',
    label: 'Item Tax Templates',
    keyExcel: 'Title',
    keyApi: 'title',
    keyFuzzyMatch: 'strip-tax-suffix',
    filters: { company: 'Connect Diagnostics' },
    fields: [
      { excel: 'Title', api: 'title', fuzzyMatch: 'strip-tax-suffix' },
      { excel: 'Company', api: 'company' },
    ],
  },
];

/** การแมปชื่อประเทศไปยัง alias spellings ที่ยอมรับสำหรับ fuzzy matching */
export const COUNTRY_ALIASES: Record<string, string[]> = {
  'South Korea': ['South Korea', 'Korea, Republic of', 'Republic of Korea'],
  'Korea, Republic of': ['South Korea', 'Korea, Republic of', 'Republic of Korea'],
};
