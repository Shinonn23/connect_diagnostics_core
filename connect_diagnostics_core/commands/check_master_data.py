# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

import click


@click.command("check-master-data")
def check_master_data() -> None:
	"""Compare Google Sheets master data against ERPNext and report discrepancies."""
	import frappe

	from connect_diagnostics_core.tests.validation.config import get_config
	from connect_diagnostics_core.tests.validation.runner import run_validation

	config = get_config(frappe.conf)
	run_validation(config)
