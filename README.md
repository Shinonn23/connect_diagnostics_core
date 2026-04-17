### Connect Diagnostics Core

Custom app for Connect Diagnostics to manage and implement company-specific business logic, workflows, and processes on ERPNext.

### Installation

You can install this app using the [bench](https://github.com/frappe/bench) CLI:

```bash
cd $PATH_TO_YOUR_BENCH
bench get-app $URL_OF_THIS_REPO --branch develop
bench install-app connect_diagnostics_core
```

### Contributing

This app uses `pre-commit` for code formatting and linting. Please [install pre-commit](https://pre-commit.com/#installation) and enable it for this repository:

```bash
cd apps/connect_diagnostics_core
pre-commit install
```

Pre-commit is configured to use the following tools for checking and formatting your code:

- ruff
- eslint
- prettier
- pyupgrade

### CI

This app can use GitHub Actions for CI. The following workflows are configured:

- CI: Installs this app and runs unit tests on every push to `develop` branch.
- Linters: Runs [Frappe Semgrep Rules](https://github.com/frappe/semgrep-rules) and [pip-audit](https://pypi.org/project/pip-audit/) on every pull request.

### Data Validation

เปรียบเทียบ Master Data จาก Google Sheets กับ ERPNext API แบบ field-by-field

**Setup:**
```bash
# ติดตั้ง dependencies
bench pip install google-api-python-client google-auth

# ล็อกอิน Google (ADC)
gcloud auth application-default login

# สร้าง config Google Sheet (รันครั้งเดียว)
python connect_diagnostics_core/tests/validation/setup_config_sheet.py
# → จะได้ CONFIG_SHEET_ID ใส่ใน .env

# ตั้งค่า .env
GOOGLE_SHEET_ID=1P40NXIF72wm4YVLfqN0l3-W3GXLt2GVraVLY9bKZXFQ
CONFIG_SHEET_ID=<from setup script>
```

**รัน validation:**
```bash
bench validate-master    # เทียบทุก sheet (17 sheets)
bench validate-stock     # เฉพาะ stock-related (5 sheets)
```

**แก้ mapping config:** แก้ที่ Google Sheet "CD-ERPNext Validation Config" ได้เลย ไม่ต้องแก้โค้ด

### License

bsl-1.0
