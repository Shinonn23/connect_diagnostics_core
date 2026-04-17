import click


@click.command("validate-master")
def validate_master():
	"""เปรียบเทียบ Google Sheets Master Data กับ ERPNext API — config อ่านจาก Google Sheet"""
	from connect_diagnostics_core.tests.validation.runner import run_master_validation

	run_master_validation()
