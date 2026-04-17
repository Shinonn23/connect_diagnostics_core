"""สร้าง Google Sheet config สำหรับ validation (3 tabs: SheetConfigs, FieldMappings, Aliases)
รันครั้งเดียว: python setup_config_sheet.py
ผลลัพธ์: จะสร้าง Google Sheet ใหม่แล้วพิมพ์ CONFIG_SHEET_ID ให้ใส่ใน .env
"""

import os
import sys

from google.oauth2 import service_account
from google.auth.credentials import Credentials
import google.auth
from googleapiclient.discovery import build


def get_credentials() -> Credentials:
	sa_path = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
	if sa_path and os.path.exists(sa_path):
		return service_account.Credentials.from_service_account_file(
			sa_path,
			scopes=["https://www.googleapis.com/auth/spreadsheets"],
		)
	return google.auth.default(scopes=["https://www.googleapis.com/auth/spreadsheets"])[0]


SHEET_CONFIGS = [
	[
		"sheet_name",
		"doctype",
		"label",
		"key_excel",
		"key_api",
		"key_ignore_case",
		"key_fuzzy_match",
		"filters",
		"key_extractor",
		"composite_key",
	],
	["Companies", "Company", "Companies", "Company", "company_name", "true", "", "", "", ""],
	["Customers", "Customer", "Customers", "ID;Customer Name", "name", "", "", "", "", ""],
	["Suppliers", "Supplier", "Suppliers", "CD ID;Supplier Name", "name", "", "", "", "", ""],
	["Items", "Item", "Items", "ID;CD Item Code", "name", "", "", "", "", ""],
	["Employees", "Employee", "Employees", "EmployeeID", "name", "", "", "", "", ""],
	["Warehouses", "Warehouse", "Warehouses", "Warehouse Name", "warehouse_name", "", "", "", "", ""],
	["Item_Groups", "Item Group", "Item Groups", "Item Group Name", "name", "", "", "", "", ""],
	[
		"Customer_Groups",
		"Customer Group",
		"Customer Groups",
		"Customer Group Name",
		"name",
		"",
		"",
		"",
		"",
		"",
	],
	["Supplier_Groups", "Supplier Group", "Supplier Groups", "Supplier Group", "name", "", "", "", "", ""],
	["Territories", "Territory", "Territories", "Territory", "name", "", "", "", "", ""],
	["Departments", "Department", "Departments", "Department Name", "name", "", "strip-cd", "", "", ""],
	["UOMs", "UOM", "UOMs", "new name;old name", "name", "true", "", "", "", ""],
	["Currencies", "Currency", "Currencies", "currency_code", "name", "", "", "", "", ""],
	["Brands", "Brand", "Brands", "Brand", "name", "", "", "", "", ""],
	[
		"Accounts New",
		"Account",
		"Accounts",
		"Account Number;Account Name",
		"name",
		"",
		"",
		"company=Connect Diagnostics",
		"split_dash",
		"",
	],
	[
		"Item_Prices",
		"Item Price",
		"Item Prices",
		"Item Code",
		"item_code",
		"",
		"",
		"",
		"",
		"item_code_pipe_price_list",
	],
	[
		"Tax_Withholding_Categories",
		"Tax Withholding Category",
		"Tax Withholding Categories",
		"Category Name",
		"name",
		"",
		"",
		"",
		"",
		"",
	],
	[
		"Item_Tax_Templates",
		"Item Tax Template",
		"Item Tax Templates",
		"Title",
		"title",
		"",
		"strip-tax-suffix",
		"company=Connect Diagnostics",
		"",
		"",
	],
]

FIELD_MAPPINGS = [
	[
		"sheet_name",
		"excel_column",
		"api_field",
		"ignore_case",
		"fuzzy_match",
		"boolean_field",
		"alias_type",
		"first_name_only",
		"skip_when",
	],
	["Companies", "Company", "company_name", "true", "", "", "", "", ""],
	["Companies", "Abbr", "abbr", "", "", "", "", "", ""],
	["Companies", "Default Currency", "default_currency", "", "", "", "", "", ""],
	["Companies", "Country", "country", "", "", "", "", "", ""],
	["Customers", "Customer Name", "customer_name", "", "", "", "", "", ""],
	["Customers", "Customer Type", "customer_type", "true", "", "", "", "", ""],
	["Customers", "Customer Group", "customer_group", "", "", "", "", "", ""],
	["Customers", "Territory", "territory", "true", "", "", "", "", ""],
	["Customers", "Disabled", "disabled", "", "", "true", "", "", ""],
	["Suppliers", "Supplier Name", "supplier_name", "", "", "", "", "", ""],
	["Suppliers", "Supplier Group", "supplier_group", "", "", "", "", "", ""],
	["Suppliers", "Country", "country", "", "", "", "country", "", ""],
	["Suppliers", "Disabled", "disabled", "", "", "true", "", "", ""],
	["Items", "Item Name (40 Char)", "item_name", "", "", "", "", "", ""],
	["Items", "Item Group", "item_group", "", "", "", "", "", ""],
	["Items", "Default Unit of Measure", "stock_uom", "true", "", "", "", "", ""],
	["Items", "Maintain Stock", "is_stock_item", "", "", "true", "", "", ""],
	["Items", "Disabled", "disabled", "", "", "true", "", "", ""],
	["Items", "Has Batch No", "has_batch_no", "", "", "true", "", "", "not_is_stock_item"],
	["Items", "Has Serial No", "has_serial_no", "", "", "true", "", "", "not_is_stock_item"],
	["Items", "Brand", "brand", "", "", "", "", "", ""],
	["Employees", "EmployeeNameEN;EmployeeSurnameEN", "employee_name", "", "", "", "", "true", ""],
	["Employees", "Department", "department", "", "strip-cd", "", "", "", ""],
	["Employees", "Employment Type", "employment_type", "", "", "", "", "", ""],
	["Employees", "Company", "company", "", "", "", "", "", ""],
	["Employees", "Gender", "gender", "", "", "", "", "", ""],
	["Warehouses", "Warehouse Name", "warehouse_name", "", "", "", "", "", ""],
	["Warehouses", "Company", "company", "", "", "", "", "", ""],
	["Warehouses", "Warehouse Type", "warehouse_type", "", "", "", "", "", ""],
	["Item_Groups", "Item Group Name", "item_group_name", "", "", "", "", "", ""],
	["Item_Groups", "Parent Item Group", "parent_item_group", "", "", "", "", "", ""],
	["Item_Groups", "Is Group", "is_group", "", "", "true", "", "", ""],
	["Customer_Groups", "Customer Group Name", "customer_group_name", "", "", "", "", "", ""],
	["Customer_Groups", "Parent Customer Group", "parent_customer_group", "", "", "", "", "", ""],
	["Supplier_Groups", "Supplier Group", "supplier_group_name", "", "", "", "", "", ""],
	["Territories", "Territory", "territory_name", "", "", "", "", "", ""],
	["Departments", "Department Name", "department_name", "", "strip-cd", "", "", "", ""],
	["Departments", "Company", "company", "", "", "", "", "", ""],
	["UOMs", "new name;old name", "uom_name", "true", "", "", "", "", ""],
	["Currencies", "currency_code", "currency_name", "", "", "", "", "", ""],
	["Accounts New", "Account Name", "account_name", "", "", "", "", "", ""],
	["Accounts New", "Root Type", "root_type", "", "", "", "", "", ""],
	["Accounts New", "Is Group", "is_group", "", "", "true", "", "", ""],
	["Accounts New", "Account Type", "account_type", "", "account-type", "", "account_type", "", ""],
	["Accounts New", "Company", "company", "", "", "", "", "", ""],
	["Item_Prices", "Price List", "price_list", "", "", "", "", "", ""],
	["Item_Prices", "Price List Rate;Rate", "price_list_rate", "", "", "", "", "", ""],
	["Tax_Withholding_Categories", "Category Name", "name", "", "", "", "", "", ""],
	[
		"Tax_Withholding_Categories",
		"Round Off Tax Amount",
		"round_off_tax_amount",
		"",
		"",
		"true",
		"",
		"",
		"",
	],
	["Item_Tax_Templates", "Title", "title", "", "strip-tax-suffix", "", "", "", ""],
	["Item_Tax_Templates", "Company", "company", "", "", "", "", "", ""],
]

ALIASES = [
	["alias_type", "key", "values"],
	["country", "South Korea", "South Korea;Korea, Republic of;Republic of Korea"],
	["country", "Korea, Republic of", "South Korea;Korea, Republic of;Republic of Korea"],
	["account_type", "Expense", "Expense;Expense Account;Indirect Expense;Depreciation"],
	["account_type", "Expense Account", "Expense;Expense Account;Indirect Expense;Depreciation"],
	["account_type", "Indirect Expense", "Expense;Expense Account;Indirect Expense;Depreciation"],
	["account_type", "Current Asset", "Current Asset;Bank;Cash;Receivable;Stock Asset;"],
	["account_type", "Accrued Expenses", "Accrued Expenses;Payable"],
	["account_type", "Payable", "Accrued Expenses;Payable"],
	["account_type", "Depreciation", "Depreciation;Expense;Expense Account"],
	["account_type", "Income Account", "Income Account;Income;Direct Income;Indirect Income"],
	["account_type", "Income", "Income Account;Income;Direct Income;Indirect Income"],
	["account_type", "Direct Income", "Income Account;Income;Direct Income;Indirect Income"],
	["account_type", "Indirect Income", "Income Account;Income;Direct Income;Indirect Income"],
	["account_type", "Fixed Asset", "Fixed Asset;Capital Stock;"],
	["account_type", "Cost of Goods Sold", "Cost of Goods Sold;COGS"],
	["account_type", "COGS", "Cost of Goods Sold;COGS"],
	["account_type", "Receivable", "Receivable;Current Asset;"],
	["account_type", "Stock Asset", "Stock Asset;Current Asset;"],
	["account_type", "Cash", "Cash;Current Asset;"],
	["account_type", "Bank", "Bank;Current Asset;"],
	["account_type", "Equity", "Equity;"],
	["account_type", "Chargeable", "Chargeable;"],
	["account_type", "Tax", "Tax;"],
	["account_type", "Round Off", "Round Off;"],
	["account_type", "Write Off", "Write Off;"],
]


def create_config_sheet():
	credentials = get_credentials()
	service = build("sheets", "v4", credentials=credentials)
	sheets_api = service.spreadsheets()

	spreadsheet = sheets_api.create(
		body={
			"properties": {"title": "CD-ERPNext Validation Config"},
			"sheets": [
				{"properties": {"title": "SheetConfigs"}},
				{"properties": {"title": "FieldMappings"}},
				{"properties": {"title": "Aliases"}},
			],
		}
	).execute()

	sheet_id = spreadsheet["spreadsheetId"]
	print(f"  Created Google Sheet: {sheet_id}")

	sheets_api.values().update(
		spreadsheetId=sheet_id,
		range="SheetConfigs!A1",
		valueInputOption="RAW",
		body={"values": SHEET_CONFIGS},
	).execute()

	sheets_api.values().update(
		spreadsheetId=sheet_id,
		range="FieldMappings!A1",
		valueInputOption="RAW",
		body={"values": FIELD_MAPPINGS},
	).execute()

	sheets_api.values().update(
		spreadsheetId=sheet_id,
		range="Aliases!A1",
		valueInputOption="RAW",
		body={"values": ALIASES},
	).execute()

	print(f"\n  Done! Add this to your .env:")
	print(f"  CONFIG_SHEET_ID={sheet_id}")
	print(f"\n  Sheet URL: https://docs.google.com/spreadsheets/d/{sheet_id}")


if __name__ == "__main__":
	create_config_sheet()
