# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

import click
import frappe
from frappe.commands import get_site, pass_context
from frappe.utils.bench_helper import CliCtxObj

from connect_diagnostics_core.tests.validation.config import get_config
from connect_diagnostics_core.tests.validation.runner import run_validation


@click.command("check-master-data")
@pass_context
def check_master_data(context: CliCtxObj) -> None:
	"""Compare Google Sheets master data against ERPNext and report discrepancies."""
	site = get_site(context)
	frappe.init(site=site)
	frappe.connect()
	config = get_config(frappe.get_site_config())
	run_validation(config)
