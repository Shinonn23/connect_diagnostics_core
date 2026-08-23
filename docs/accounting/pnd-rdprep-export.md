# PND → RD Prep `.txt` export

Export PND withholding data (ภ.ง.ด.1/1ก/3/53) as delimited `.txt` files for the Revenue
Department's **RD Prep** desktop program. RD Prep imports the text file, produces the `.rdx`,
and uploads it to e-Filing.

## Key architectural facts

- Source: the official RD Prep manual v1.0 at
  `https://efiling.rd.go.th/content/download/RDPrep.pdf` (84 pages).
- This app does **not** produce `.rdx`. Accounting systems export `.txt` or `.csv`; RD Prep
  imports it and creates the `.rdx`.
- RD Prep is a desktop application. The current e-Filing Open API lists forms other than
  PND1/3/53 and requires service-provider registration, so `.txt` → RD Prep is the supported
  path for these forms.
- RD Prep uses a column-mapping UI (manual pages 57–60 and 72), with the first row as headers.
  Column order is therefore not rigidly fixed: required fields must be separate columns, a
  header row must be present, and `|` is the safest delimiter because Thai names and addresses
  may contain commas.
- The manual does not settle date formatting or Buddhist/Gregorian year representation. Verify
  those details on the first real import during UAT.

## Required field set

- **PND1** (monthly, pages 24–25): payee tax ID, title, first/middle/last name, payment date,
  income type (`40(1)=1`, `40(1)(2)=2`, resident `40(2)=3`, non-resident `40(2)=4`), paid
  amount, withheld tax, and withholding condition (`1` withheld, `2` paid continuously,
  `3` paid one time).
- **PND3** (pages 35–36) and **PND53** (pages 46–47): payee tax ID, name and address,
  payment date, income description, tax rate, tax base, withheld tax, withholding condition,
  and the statutory remittance basis.
- **PND1ก**: annual per-employee summary including YTD income, tax, provident fund, SSO, and
  exemptions. Mid-year go-live YTD seeding is not built, so 1ก is accurate only from submitted
  slips.

## Existing data sources

- **PND3/PND53:** reuse ERPNext Thailand's `Withholding Tax Cert` and `Withholding Tax Items`
  plus its `pnd3` and `pnd53` Query Reports. Its `tax_payer` values already map to the PND
  withholding condition.
- **PND1/1ก:** use HRMS Salary Slip. Employee `national_id` is the 13-digit tax ID, the
  `Withholding Tax` salary component is the PIT amount, and Salary Slips are submitted only via
  Payroll Entry. These reports are built in this app.

## Locked decisions

- Use `.txt` → RD Prep, not direct `.rdx` generation or the Open API.
- Split reports by form, group them in one workspace section, and share the export engine.
- Keep the implementation in `connect_diagnostics_core`; reuse ERPNext Thailand for PND3/53.
