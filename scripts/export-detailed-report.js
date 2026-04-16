const https = require("https");
const xlsx = require("xlsx");
const path = require("path");
const os = require("os");
const fs = require("fs");
require("dotenv").config();

const BASE = "https://dev.connectdiagnostics.nomeaparadigm.com";

const SHEET_CONFIGS = [
	{ sheetName: "Companies", doctype: "Company", label: "Companies", keyExcel: ["Company"], keyApi: "company_name", keyIgnoreCase: true, fields: [
		{ excel: ["Company"], api: "company_name", ignoreCase: true },
		{ excel: ["Abbr"], api: "abbr" },
		{ excel: ["Default Currency"], api: "default_currency" },
		{ excel: ["Country"], api: "country" },
	] },
	{ sheetName: "Customers", doctype: "Customer", label: "Customers", keyExcel: ["ID", "Customer Name"], keyApi: "name", fields: [
		{ excel: ["Customer Name"], api: "customer_name" },
		{ excel: ["Customer Type"], api: "customer_type", ignoreCase: true },
		{ excel: ["Customer Group"], api: "customer_group" },
		{ excel: ["Territory"], api: "territory", ignoreCase: true },
		{ excel: ["Disabled"], api: "disabled", booleanField: true },
	] },
	{ sheetName: "Suppliers", doctype: "Supplier", label: "Suppliers", keyExcel: ["CD ID", "Supplier Name"], keyApi: "name", fields: [
		{ excel: ["Supplier Name"], api: "supplier_name" },
		{ excel: ["Supplier Group"], api: "supplier_group" },
		{ excel: ["Country"], api: "country", countryAlias: true },
		{ excel: ["Disabled"], api: "disabled", booleanField: true },
	] },
	{ sheetName: "Items", doctype: "Item", label: "Items", keyExcel: ["ID", "CD Item Code"], keyApi: "name", fields: [
		{ excel: ["Item Name (40 Char)"], api: "item_name" },
		{ excel: ["Item Group"], api: "item_group" },
		{ excel: ["Default Unit of Measure"], api: "stock_uom", ignoreCase: true },
		{ excel: ["Maintain Stock"], api: "is_stock_item", booleanField: true },
		{ excel: ["Disabled"], api: "disabled", booleanField: true },
		{ excel: ["Has Batch No"], api: "has_batch_no", booleanField: true, skipWhenKey: "is_stock_item", skipWhenVal: false },
		{ excel: ["Has Serial No"], api: "has_serial_no", booleanField: true, skipWhenKey: "is_stock_item", skipWhenVal: false },
		{ excel: ["Brand"], api: "brand" },
	] },
	{ sheetName: "Employees", doctype: "Employee", label: "Employees", keyExcel: ["EmployeeID"], keyApi: "name", fields: [
		{ excel: ["EmployeeNameEN", "EmployeeSurnameEN"], api: "employee_name", isFullName: true },
		{ excel: ["Department"], api: "department", fuzzyMatch: "strip-cd" },
		{ excel: ["Employment Type"], api: "employment_type" },
		{ excel: ["Company"], api: "company" },
		{ excel: ["Gender"], api: "gender" },
	] },
	{ sheetName: "Warehouses", doctype: "Warehouse", label: "Warehouses", keyExcel: ["Warehouse Name"], keyApi: "warehouse_name", fields: [
		{ excel: ["Warehouse Name"], api: "warehouse_name" },
		{ excel: ["Company"], api: "company" },
		{ excel: ["Warehouse Type"], api: "warehouse_type" },
	] },
	{ sheetName: "Item_Groups", doctype: "Item Group", label: "Item Groups", keyExcel: ["Item Group Name"], keyApi: "name", fields: [
		{ excel: ["Item Group Name"], api: "item_group_name" },
		{ excel: ["Parent Item Group"], api: "parent_item_group" },
		{ excel: ["Is Group"], api: "is_group", booleanField: true },
	] },
	{ sheetName: "Customer_Groups", doctype: "Customer Group", label: "Customer Groups", keyExcel: ["Customer Group Name"], keyApi: "name", fields: [
		{ excel: ["Customer Group Name"], api: "customer_group_name" },
		{ excel: ["Parent Customer Group"], api: "parent_customer_group" },
	] },
	{ sheetName: "Supplier_Groups", doctype: "Supplier Group", label: "Supplier Groups", keyExcel: ["Supplier Group"], keyApi: "name", fields: [
		{ excel: ["Supplier Group"], api: "supplier_group_name" },
	] },
	{ sheetName: "Territories", doctype: "Territory", label: "Territories", keyExcel: ["Territory"], keyApi: "name", fields: [
		{ excel: ["Territory"], api: "territory_name" },
	] },
	{ sheetName: "Departments", doctype: "Department", label: "Departments", keyExcel: ["Department Name"], keyApi: "name", keyFuzzyMatch: "strip-cd", fields: [
		{ excel: ["Department Name"], api: "department_name", fuzzyMatch: "strip-cd" },
		{ excel: ["Company"], api: "company" },
	] },
	{ sheetName: "UOMs", doctype: "UOM", label: "UOMs", keyExcel: ["new name", "old name"], keyApi: "name", keyIgnoreCase: true, fields: [
		{ excel: ["new name", "old name"], api: "uom_name", ignoreCase: true },
	] },
	{ sheetName: "Currencies", doctype: "Currency", label: "Currencies", keyExcel: ["currency_code"], keyApi: "name", fields: [
		{ excel: ["currency_code"], api: "currency_name" },
	] },
	{ sheetName: "Brands", doctype: "Brand", label: "Brands", keyExcel: ["Brand"], keyApi: "name", fields: [] },
	{ sheetName: "Accounts New", doctype: "Account", label: "Accounts", keyExcel: ["Account Number", "Account Name"], keyApi: "name", keyExtractor: (val) => val.split(" - ")[0].trim(), filters: { company: "Connect Diagnostics" }, fields: [
		{ excel: ["Account Name"], api: "account_name" },
		{ excel: ["Root Type"], api: "root_type" },
		{ excel: ["Is Group"], api: "is_group", booleanField: true },
		{ excel: ["Account Type"], api: "account_type" },
		{ excel: ["Company"], api: "company" },
	] },
	{ sheetName: "Tax_Withholding_Categories", doctype: "Tax Withholding Category", label: "Tax Withholding Categories", keyExcel: ["Category Name"], keyApi: "name", fields: [
		{ excel: ["Category Name"], api: "name" },
		{ excel: ["Round Off Tax Amount"], api: "round_off_tax_amount", booleanField: true },
	] },
	{ sheetName: "Item_Tax_Templates", doctype: "Item Tax Template", label: "Item Tax Templates", keyExcel: ["Title"], keyApi: "title", keyFuzzyMatch: "strip-tax-suffix", filters: { company: "Connect Diagnostics" }, fields: [
		{ excel: ["Title"], api: "title", fuzzyMatch: "strip-tax-suffix" },
		{ excel: ["Company"], api: "company" },
	] },
];

const COUNTRY_ALIASES = {
	"South Korea": ["South Korea", "Korea, Republic of", "Republic of Korea"],
	"Korea, Republic of": ["South Korea", "Korea, Republic of", "Republic of Korea"],
};

function login() {
	return new Promise((resolve, reject) => {
		const o = { hostname: new URL(BASE).hostname, path: "/api/method/login", method: "POST", headers: { "Content-Type": "application/x-www-form-urlencoded" }, rejectUnauthorized: false };
		const r = https.request(o, (res) => {
			const c = res.headers["set-cookie"] || [];
			let d = "";
			res.on("data", (ch) => (d += ch));
			res.on("end", () => { const s = c.find((c) => c.includes("sid=")); resolve(s ? s.match(/sid=([^;]+)/)[1] : ""); });
		});
		r.on("error", reject);
		r.write("usr=Administrator&pwd=" + process.env.ERP_PASSWORD);
		r.end();
	});
}

function apiGet(p, sid) {
	return new Promise((resolve) => {
		https.get(BASE + p, { headers: { Cookie: "sid=" + sid }, rejectUnauthorized: false }, (res) => {
			let d = "";
			res.on("data", (ch) => (d += ch));
			res.on("end", () => { try { resolve(JSON.parse(d)); } catch { resolve(null); } });
		});
	});
}

function norm(v) { if (v === null || v === undefined || v === "") return ""; if (typeof v === "number") return String(v); return String(v).trim().replace(/\s{2,}/g, " "); }
function toBool(v) { if (v === null || v === undefined || v === "") return null; const s = String(v).trim().toLowerCase(); if (["1","yes","true","✓","checked"].includes(s)) return true; if (["0","no","false","✗","unchecked"].includes(s)) return false; return null; }
function stripCd(v) { return v.replace(/\s*-\s*CD\s*$/, "").trim(); }
function stripTaxSuffix(v) { let r = v.replace(/\s*-\s*(CD|DKSH|UBIQ)\s*$/, "").trim(); return r.replace(/\s+\d+$/, "").trim(); }
function getExcelVal(row, cols) { for (const c of cols) { const v = row[c]; if (v !== null && v !== undefined && v !== "") return v; } return ""; }

function getExcelKey(row, config) {
	for (const k of config.keyExcel) {
		let v = norm(row[k]);
		if (!v) continue;
		if (config.keyExtractor) v = config.keyExtractor(v);
		if (config.keyIgnoreCase) return v.toLowerCase();
		if (config.keyFuzzyMatch === "strip-cd") return stripCd(v);
		if (config.keyFuzzyMatch === "strip-tax-suffix") return stripTaxSuffix(v);
		return v;
	}
	return "";
}

function getApiKey(rec, config) {
	let v = norm(rec[config.keyApi]);
	if (config.keyExtractor) v = config.keyExtractor(v);
	if (config.keyIgnoreCase) return v.toLowerCase();
	if (config.keyFuzzyMatch === "strip-cd") return stripCd(v);
	if (config.keyFuzzyMatch === "strip-tax-suffix") return stripTaxSuffix(v);
	return v;
}

function compareVals(exVal, apVal, mapping) {
	const nEx = norm(exVal), nAp = norm(apVal);
	if (nEx === "" && nAp === "") return true;
	if (nEx === "" || nAp === "") return nEx === nAp;
	if (mapping.booleanField) { const eb = toBool(exVal), ab = toBool(apVal); if (eb !== null && ab !== null) return eb === ab; }
	if (mapping.countryAlias) { const a = COUNTRY_ALIASES[nEx] || COUNTRY_ALIASES[nAp]; if (a) return a.includes(nEx) && a.includes(nAp); }
	if (mapping.fuzzyMatch === "strip-cd") return stripCd(nEx) === stripCd(nAp);
	if (mapping.fuzzyMatch === "strip-tax-suffix") return stripTaxSuffix(nEx) === stripTaxSuffix(nAp);
	if (mapping.isFullName) { const p = nEx.split(" ").filter(Boolean); return p.length === 1 ? nAp.toLowerCase().startsWith(p[0].toLowerCase()) : nAp.toLowerCase().startsWith(p[0].toLowerCase()); }
	if (mapping.ignoreCase) return nEx.toLowerCase() === nAp.toLowerCase();
	return nEx === nAp;
}

function findExcelFile() {
	const dirs = [path.join(__dirname, "..", "data"), path.join(os.homedir(), "Desktop")];
	for (const d of dirs) { if (!fs.existsSync(d)) continue; const f = fs.readdirSync(d).find((f) => f.startsWith("CD-ERPNext") && f.includes("v.3") && f.endsWith(".xlsx")); if (f) return path.join(d, f); }
	throw new Error("Cannot find CD-ERPNext Excel file");
}

(async () => {
	console.log("=== CD-ERPNext Detailed Validation Report ===\n");
	const sid = await login();
	const excelPath = findExcelFile();
	console.log("Excel:", excelPath);
	const wb = xlsx.readFile(excelPath);
	const wbOut = xlsx.utils.book_new();
	const summaryRows = [];

	for (const config of SHEET_CONFIGS) {
		console.log(`\n--- ${config.label} ---`);
		const sheetData = wb.Sheets[config.sheetName];
		if (!sheetData) { console.log(`  Sheet "${config.sheetName}" not found, skip.`); continue; }
		const excelRows = xlsx.utils.sheet_to_json(sheetData, { defval: "", raw: false });

		const apiFields = ["name", ...new Set(config.fields.map((f) => f.api))];
		if (config.keyApi !== "name" && !apiFields.includes(config.keyApi)) apiFields.push(config.keyApi);
		if (config.keyExtractor) apiFields.push("account_number");

		const p = new URLSearchParams();
		p.set("doctype", config.doctype);
		p.set("fields", JSON.stringify(apiFields));
		p.set("filters", JSON.stringify(config.filters || {}));
		p.set("limit_page_length", "0");

		const apiRes = await apiGet("/api/method/frappe.client.get_list?" + p.toString(), sid);
		const apiRecords = (apiRes && apiRes.message) || [];
		console.log(`  Excel: ${excelRows.length}, API: ${apiRecords.length}`);

		const apiMap = new Map();
		for (const rec of apiRecords) {
			const key = getApiKey(rec, config);
			if (key) apiMap.set(key, rec);
			if (config.keyExtractor && rec.account_number) apiMap.set(norm(rec.account_number), rec);
		}

		let matched = 0, missing = 0, mismatchCount = 0;
		const keyCols = config.keyExcel;
		const issues = [];
		const failedRecordKeys = new Set();

		for (const row of excelRows) {
			const excelKey = getExcelKey(row, config);
			if (!excelKey) {
				const nonKeyValues = Object.entries(row).filter(([k]) => !keyCols.includes(k)).map(([, v]) => v);
				if (nonKeyValues.every((v) => v === null || v === undefined || v === "")) continue;
				continue;
			}

			let apiRec = apiMap.get(excelKey);
			if (!apiRec && !config.keyIgnoreCase) {
				for (const [k, v] of apiMap) { if (k.toLowerCase() === excelKey.toLowerCase()) { apiRec = v; break; } }
			}

			if (!apiRec) {
				missing++;
				const displayId = keyCols.map((k) => row[k]).filter(Boolean).join(" / ");
				issues.push({ Key: displayId, Field: "-", "Excel Value": "-", "API Value": "-", Category: "MISSING_IN_API" });
				failedRecordKeys.add(excelKey);
				continue;
			}

			matched++;
			let recHasIssue = false;

			for (const fieldMap of config.fields) {
				if (fieldMap.skipWhenKey && apiRec[fieldMap.skipWhenKey] !== undefined) {
					if (toBool(apiRec[fieldMap.skipWhenKey]) === fieldMap.skipWhenVal) continue;
				}
				const exVal = getExcelVal(row, fieldMap.excel);
				const apVal = apiRec[fieldMap.api];
				if (norm(exVal) === "") continue;

				if (!compareVals(exVal, apVal, fieldMap)) {
					mismatchCount++;
					recHasIssue = true;
					issues.push({
						Key: excelKey,
						Field: fieldMap.api,
						"Excel Value": String(exVal ?? "").substring(0, 100),
						"API Value": String(apVal ?? "(null)").substring(0, 100),
						Category: norm(apVal) === "" ? "API_EMPTY" : "MISMATCH",
					});
				}
			}

			if (recHasIssue) failedRecordKeys.add(excelKey);
		}

		const status = (missing === 0 && mismatchCount === 0) ? "PASS" : "FAIL";

		summaryRows.push({
			Sheet: config.label,
			DocType: config.doctype,
			"Excel Rows": excelRows.length,
			"API Records": apiRecords.length,
			Matched: matched,
			Missing: missing,
			Mismatches: mismatchCount,
			"Columns Checked": config.fields.length,
			"Key Column(s)": config.keyExcel.join(", "),
			"Column Mapping": config.fields.map((f) => `${f.excel.join("/")} → ${f.api}`).join(", ") || "(key only)",
			Status: status,
		});

		if (issues.length > 0) {
			const sheetName = config.label.length > 25 ? config.label.substring(0, 25) : config.label;
			xlsx.utils.book_append_sheet(wbOut, xlsx.utils.json_to_sheet(issues), `${sheetName} - Issues (${issues.length})`);

			const fullRows = [];
			for (const row of excelRows) {
				const excelKey = getExcelKey(row, config);
				if (!excelKey || !failedRecordKeys.has(excelKey)) continue;

				let apiRec = apiMap.get(excelKey);
				if (!apiRec && !config.keyIgnoreCase) {
					for (const [k, v] of apiMap) { if (k.toLowerCase() === excelKey.toLowerCase()) { apiRec = v; break; } }
				}

				const fullRow = { Key: excelKey };
				for (const fieldMap of config.fields) {
					const exVal = getExcelVal(row, fieldMap.excel);
					const apVal = apiRec ? apiRec[fieldMap.api] : "";
					fullRow[`${fieldMap.excel.join("/")} (Excel)`] = String(exVal ?? "");
					fullRow[`${fieldMap.api} (API)`] = String(apVal ?? "");
				}
				fullRows.push(fullRow);
			}

			if (fullRows.length > 0) {
				xlsx.utils.book_append_sheet(wbOut, xlsx.utils.json_to_sheet(fullRows), `${sheetName} - Full Data (${fullRows.length})`);
			}
		}

		console.log(`  Matched: ${matched}, Missing: ${missing}, Mismatches: ${mismatchCount} → ${status}`);
	}

	xlsx.utils.book_append_sheet(wbOut, xlsx.utils.json_to_sheet(summaryRows), "Summary");

	const totalExcel = summaryRows.reduce((s, r) => s + r["Excel Rows"], 0);
	const totalApi = summaryRows.reduce((s, r) => s + r["API Records"], 0);
	const totalMatched = summaryRows.reduce((s, r) => s + r.Matched, 0);
	const totalMissing = summaryRows.reduce((s, r) => s + r.Missing, 0);
	const totalMismatches = summaryRows.reduce((s, r) => s + r.Mismatches, 0);
	const totalPassed = summaryRows.filter((r) => r.Status === "PASS").length;
	const totalFailed = summaryRows.filter((r) => r.Status === "FAIL").length;

	console.log("\n========================================");
	const outFile = path.join(path.dirname(excelPath), `CD-ERPNext Validation Report ${new Date().toISOString().replace(/[:.]/g, "-").substring(0, 19)}.xlsx`);
	xlsx.writeFile(wbOut, outFile);
	console.log("Exported:", outFile);
	console.log(`  PASS: ${totalPassed}, FAIL: ${totalFailed}`);
	console.log(`  Matched: ${totalMatched}/${totalExcel}, Missing: ${totalMissing}, Mismatches: ${totalMismatches}`);
	console.log("========================================");

	process.exit(0);
})();
