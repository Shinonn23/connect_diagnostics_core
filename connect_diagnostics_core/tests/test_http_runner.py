"""ทดสอบ validation เต็ม flow ผ่าน HTTP API — ไม่ต้องมี bench/frappe
รัน: python test_http_runner.py [--sheet SHEET_NAME]
"""

import argparse
import json
import os
import sys

import requests

sys.path.insert(0, os.path.dirname(__file__))

from connect_diagnostics_core.tests.validation.config_loader import SheetConfig, load_all_configs
from connect_diagnostics_core.tests.validation.sheets_reader import get_sheet, load_master_data
from connect_diagnostics_core.tests.validation.validator import print_result, print_summary, validate_sheet


def load_env():
	env_path = os.path.join(os.path.dirname(__file__), ".env")
	if os.path.exists(env_path):
		with open(env_path) as f:
			for line in f:
				line = line.strip()
				if line and not line.startswith("#") and "=" in line:
					key, value = line.split("=", 1)
					os.environ.setdefault(key.strip(), value.strip())


class ERPNextHTTPClient:
	def __init__(self, base_url: str, username: str, password: str):
		self.session = requests.Session()
		self.base_url = base_url.rstrip("/")
		res = self.session.post(
			f"{self.base_url}/api/method/login",
			data={"usr": username, "pwd": password},
			verify=False,
		)
		if res.status_code != 200:
			raise Exception(f"Login failed: {res.status_code} {res.text}")
		print(f"  Logged in to {self.base_url}")

	def get_doc_list(
		self,
		doctype: str,
		fields: list[str] | None = None,
		filters: dict | None = None,
		limit: int = 0,
	) -> list[dict]:
		params = {
			"doctype": doctype,
			"fields": json.dumps(fields or ["name"]),
			"filters": json.dumps(filters or {}),
			"limit_page_length": str(limit),
		}
		res = self.session.get(
			f"{self.base_url}/api/method/frappe.client.get_list",
			params=params,
			verify=False,
		)
		data = res.json()
		return data.get("message", [])


def run_test(sheet_filter: str | None = None):
	print("\n" + "=" * 65)
	print("  CD-ERPNext Validation Test (HTTP API mode)")
	print("=" * 65)

	print("\n[1/4] Loading config from Google Sheet...")
	configs, aliases = load_all_configs()
	if not configs:
		print("  ERROR: No configs loaded — check CONFIG_SHEET_ID in .env")
		return

	if sheet_filter:
		configs = [c for c in configs if c.sheet_name == sheet_filter or c.doctype == sheet_filter]
		if not configs:
			print(f"  ERROR: No config found for '{sheet_filter}'")
			print(f"  Available: {', '.join(c.sheet_name for c in load_all_configs()[0])}")
			return

	print(f"  Configs: {len(configs)} sheets, Aliases: {sum(len(v) for v in aliases.values())} entries")

	print("\n[2/4] Loading master data from Google Sheet...")
	sheet_data = load_master_data()
	print(f"  Loaded {len(sheet_data)} tabs")

	print("\n[3/4] Connecting to ERPNext...")
	base_url = os.environ.get("BASE_URL", "https://dev.connectdiagnostics.nomeaparadigm.com")
	username = os.environ.get("ERP_USERNAME", "Administrator")
	password = os.environ.get("ERP_PASSWORD", "")
	client = ERPNextHTTPClient(base_url, username, password)

	print("\n[4/4] Running validation...")
	all_results = []
	for config in configs:
		sheet_rows = get_sheet(sheet_data, config.sheet_name)
		api_fields = ["name", *list({f.api for f in config.fields})]
		if config.key_api != "name" and config.key_api not in api_fields:
			api_fields.append(config.key_api)

		try:
			api_records = client.get_doc_list(config.doctype, api_fields, config.filters, 0)
		except Exception as e:
			print(f"  ERROR fetching {config.doctype}: {e}")
			api_records = []

		result = validate_sheet(sheet_rows, api_records, config, aliases)
		all_results.append(result)
		print_result(result)

	print_summary(all_results)

	failed = [r for r in all_results if not r.passed]
	return len(failed) == 0


if __name__ == "__main__":
	load_env()

	parser = argparse.ArgumentParser(description="Test CD-ERPNext validation via HTTP API")
	parser.add_argument("--sheet", help="Run only specific sheet/doctype (e.g. 'Companies' or 'Customer')")
	args = parser.parse_args()

	import urllib3

	urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

	success = run_test(args.sheet)
	sys.exit(0 if success else 1)
