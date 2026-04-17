import click


@click.command("validate-stock")
def validate_stock():
	"""เปรียบเทียบ Google Sheets Stock Data กับ ERPNext API — config อ่านจาก Google Sheet"""
	from connect_diagnostics_core.tests.validation.runner import run_stock_validation

	run_stock_validation()
