const https = require("https");
const xlsx = require("xlsx");
const path = require("path");
const os = require("os");
const fs = require("fs");

const BASE = "https://dev.connectdiagnostics.nomeaparadigm.com";

/** Login เข้า ERP instance แล้วคืนค่า session ID (sid) */
function login() {
	return new Promise((resolve, reject) => {
		const options = {
			hostname: new URL(BASE).hostname,
			path: "/api/method/login",
			method: "POST",
			headers: { "Content-Type": "application/x-www-form-urlencoded" },
			rejectUnauthorized: false,
		};
		const req = https.request(options, (res) => {
			const cookies = res.headers["set-cookie"] || [];
			let data = "";
			res.on("data", (chunk) => (data += chunk));
			res.on("end", () => {
				const sc = cookies.find((c) => c.includes("sid="));
				resolve(sc ? sc.match(/sid=([^;]+)/)[1] : "");
			});
		});
		req.on("error", reject);
		req.write("usr=Administrator&pwd=" + process.env.ERP_PASSWORD);
		req.end();
	});
}

/** ส่ง authenticated GET request ไปยัง ERP API แล้วคืนค่า parsed JSON response */
function apiGet(urlPath, sid) {
	return new Promise((resolve, reject) => {
		const req = https.get(
			BASE + urlPath,
			{
				headers: { Cookie: "sid=" + sid },
				rejectUnauthorized: false,
			},
			(res) => {
				let data = "";
				res.on("data", (chunk) => (data += chunk));
				res.on("end", () => {
					try {
						resolve(JSON.parse(data));
					} catch (e) {
						resolve(null);
					}
				});
			}
		);
		req.on("error", reject);
		req.end();
	});
}

/** Normalize ค่าให้เป็น string โดย trim และลด whitespace ซ้ำ */
function normalize(val) {
	if (val === null || val === undefined || val === "") return "";
	return String(val)
		.trim()
		.replace(/\s{2,}/g, " ");
}

/** แปลง truthy/falsy string (เช่น "1", "yes", "true") เป็น boolean */
function toBool(val) {
	if (val === null || val === undefined || val === "") return null;
	const s = String(val).trim().toLowerCase();
	if (["1", "yes", "true"].includes(s)) return true;
	if (["0", "no", "false"].includes(s)) return false;
	return null;
}

/** ลบ suffix " - CD" ท้าย string ออก */
function stripCdSuffix(val) {
	return val.replace(/\s*-\s*CD\s*$/, "").trim();
}

const COUNTRY_ALIASES = {
	"South Korea": ["South Korea", "Korea, Republic of", "Republic of Korea"],
	"Korea, Republic of": ["South Korea", "Korea, Republic of", "Republic of Korea"],
};

const SHEET_CONFIGS = [
	{
		sheetName: "Companies",
		doctype: "Company",
		label: "Companies",
		keyExcel: "Company Name",
		keyApi: "name",
		fields: [
			{ excel: "Company Name", api: "company_name" },
			{ excel: "Abbr", api: "abbr" },
			{ excel: "Currency", api: "default_currency" },
			{ excel: "Country", api: "country" },
		],
	},
	{
		sheetName: "Customers",
		doctype: "Customer",
		label: "Customers",
		keyExcel: ["ID", "Customer Name"],
		keyApi: "name",
		keyIgnoreCase: true,
		fields: [
			{ excel: "Customer Name", api: "customer_name" },
			{ excel: "Customer Group", api: "customer_group" },
			{ excel: "Territory", api: "territory", fuzzyMatch: "strip-cd" },
			{ excel: "Disabled", api: "disabled", booleanField: true },
		],
	},
	{
		sheetName: "Suppliers",
		doctype: "Supplier",
		label: "Suppliers",
		keyExcel: ["CD ID", "Supplier Name"],
		keyApi: "name",
		fields: [
			{ excel: "Supplier Name", api: "supplier_name" },
			{ excel: "Supplier Group", api: "supplier_group" },
			{ excel: "Country", api: "country", countryAlias: true },
			{ excel: "Disabled", api: "disabled", booleanField: true },
		],
	},
	{
		sheetName: "Items",
		doctype: "Item",
		label: "Items",
		keyExcel: ["ID", "CD Item Code"],
		keyApi: "name",
		fields: [
			{ excel: "Item Name (40 Char)", api: "item_name" },
			{ excel: "Item Group", api: "item_group" },
			{ excel: "Default Unit of Measure", api: "stock_uom", ignoreCase: true },
			{ excel: "Maintain Stock", api: "is_stock_item", booleanField: true },
			{ excel: "Disabled", api: "disabled", booleanField: true },
			{
				excel: "Has Batch No",
				api: "has_batch_no",
				booleanField: true,
				skipWhen: (rec) => !rec.is_stock_item,
			},
			{
				excel: "Has Serial No",
				api: "has_serial_no",
				booleanField: true,
				skipWhen: (rec) => !rec.is_stock_item,
			},
			{ excel: "Brand", api: "brand" },
		],
	},
	{
		sheetName: "Employees",
		doctype: "Employee",
		label: "Employees",
		keyExcel: "EmployeeID",
		keyApi: "name",
		fields: [
			{
				excel: ["EmployeeNameEN", "EmployeeSurnameEN"],
				api: "employee_name",
				firstNameOnly: true,
			},
			{ excel: "Department", api: "department", fuzzyMatch: "strip-cd" },
			{ excel: "Employment Type", api: "employment_type" },
			{ excel: "Company", api: "company" },
			{ excel: "Gender", api: "gender" },
		],
	},
	{
		sheetName: "Warehouses",
		doctype: "Warehouse",
		label: "Warehouses",
		keyExcel: "Warehouse Name",
		keyApi: "warehouse_name",
		fields: [
			{ excel: "Warehouse Name", api: "warehouse_name" },
			{ excel: "Company", api: "company" },
			{ excel: "Warehouse Type", api: "warehouse_type" },
		],
	},
	{
		sheetName: "Accounts New",
		doctype: "Account",
		label: "Accounts",
		keyExcel: ["Account Number", "Account Name"],
		keyApi: "name",
		keyExtractor: (val) => val.split(" - ")[0].trim(),
		filters: { company: "Connect Diagnostics" },
		fields: [
			{ excel: "Account Name", api: "account_name" },
			{ excel: "Root Type", api: "root_type" },
			{ excel: "Is Group", api: "is_group", booleanField: true },
			{ excel: "Account Type", api: "account_type" },
			{ excel: "Company", api: "company" },
		],
	},
];

/** เปรียบเทียบค่าจาก Excel กับ API ตาม field mapping rules */
function compareValues(excelVal, apiVal, mapping) {
	const normEx = normalize(excelVal);
	const normAp = normalize(apiVal);
	if (normEx === "" && normAp === "") return true;
	if (normEx === "" || normAp === "") return normEx === normAp;
	if (mapping.booleanField) {
		const exBool = toBool(excelVal);
		const apBool = toBool(apiVal);
		if (exBool !== null && apBool !== null) return exBool === apBool;
	}
	if (mapping.countryAlias) {
		const aliases = COUNTRY_ALIASES[normEx] || COUNTRY_ALIASES[normAp];
		if (aliases) return aliases.includes(normEx) && aliases.includes(normAp);
	}
	if (mapping.fuzzyMatch === "strip-cd")
		return stripCdSuffix(normEx).toLowerCase() === stripCdSuffix(normAp).toLowerCase();
	if (mapping.firstNameOnly) return normAp.toLowerCase().startsWith(normEx.toLowerCase());
	if (mapping.ignoreCase) return normEx.toLowerCase() === normAp.toLowerCase();
	return normEx === normAp;
}

/** ดึงค่าจาก Excel row รองรับ single หรือ array column names */
function getExcelValue(row, excelCol) {
	if (Array.isArray(excelCol)) {
		for (const col of excelCol) {
			const v = row[col];
			if (v !== null && v !== undefined && v !== "") return v;
		}
		return "";
	}
	return row[excelCol];
}

/** Validate Excel sheet กับ ERP API doctype แล้วรวบรวม mismatches */
async function validateAndCollect(sid, excelData, config) {
	const excelRows = xlsx.utils.sheet_to_json(excelData.Sheets[config.sheetName], {
		defval: "",
		raw: false,
	});

	const apiFields = ["name", ...new Set(config.fields.map((f) => f.api))];
	if (config.keyApi !== "name" && !apiFields.includes(config.keyApi))
		apiFields.push(config.keyApi);

	const params = new URLSearchParams();
	params.set("doctype", config.doctype);
	params.set("fields", JSON.stringify(apiFields));
	params.set("limit_page_length", "0");
	if (config.filters) params.set("filters", JSON.stringify(config.filters));
	const res = await apiGet("/api/method/frappe.client.get_list?" + params.toString(), sid);
	const apiRecords = res.message || [];

	const apiMap = new Map();
	for (const rec of apiRecords) {
		let key = normalize(rec[config.keyApi]);
		if (config.keyExtractor) key = config.keyExtractor(key);
		if (config.keyIgnoreCase) key = key.toLowerCase();
		apiMap.set(key, rec);
	}

	const results = [];
	for (const row of excelRows) {
		const keyCols = Array.isArray(config.keyExcel) ? config.keyExcel : [config.keyExcel];
		let excelKey = "";
		for (const k of keyCols) {
			const v = normalize(row[k]);
			if (v) {
				excelKey = v;
				break;
			}
		}

		const nonKeyValues = Object.entries(row)
			.filter(([k]) => !keyCols.includes(k))
			.map(([, v]) => v);
		const allNonKeyEmpty = nonKeyValues.every(
			(v) => v === null || v === undefined || v === ""
		);
		if (allNonKeyEmpty) continue;
		if (!excelKey) continue;

		let lookupKey = excelKey;
		if (config.keyExtractor) lookupKey = config.keyExtractor(lookupKey);
		if (config.keyIgnoreCase) lookupKey = lookupKey.toLowerCase();

		let apiRec = apiMap.get(lookupKey);
		if (!apiRec && !config.keyIgnoreCase) {
			for (const [k, v] of apiMap) {
				if (k.toLowerCase() === lookupKey.toLowerCase()) {
					apiRec = v;
					break;
				}
			}
		}
		if (!apiRec) {
			results.push({
				key: excelKey,
				field: "-",
				excel_val: "-",
				api_val: "-",
				status: "MISSING_IN_API",
			});
			continue;
		}

		for (const fm of config.fields) {
			if (fm.skipWhen && fm.skipWhen(apiRec)) continue;
			const exVal = getExcelValue(row, fm.excel);
			if (normalize(exVal) === "") continue;
			const apVal = apiRec[fm.api];
			if (!compareValues(exVal, apVal, fm)) {
				results.push({
					key: excelKey,
					field: fm.api,
					excel_val: String(exVal),
					api_val: String(apVal ?? "null"),
					status: "MISMATCH",
				});
			}
		}
	}

	return {
		label: config.label,
		doctype: config.doctype,
		excelCount: excelRows.length,
		apiCount: apiRecords.length,
		mismatches: results,
	};
}

/** Entry point หลัก: รัน validation ทุก sheet ที่ config ไว้แล้ว export ผลลัพธ์ไปเป็น Excel */
(async () => {
	const sid = await login();

	const dirs = [
		process.env.EXCEL_DIR,
		path.join(__dirname, "..", "data"),
		path.join(os.homedir(), "Desktop"),
	].filter(Boolean);
	let dir, match;
	for (const d of dirs) {
		try {
			const f = fs
				.readdirSync(d)
				.find(
					(f) => f.startsWith("CD-ERPNext") && f.includes("v.3") && f.endsWith(".xlsx")
				);
			if (f) {
				dir = d;
				match = f;
				break;
			}
		} catch (e) {
			/* ignore */
		}
	}
	if (!match) {
		console.error("Excel not found");
		process.exit(1);
	}
	const wb = xlsx.readFile(path.join(dir, match));
	console.log("Excel:", match);

	const wbOut = xlsx.utils.book_new();

	const summaryRows = [];

	for (const config of SHEET_CONFIGS) {
		console.log("Checking:", config.label, "...");
		const result = await validateAndCollect(sid, wb, config);
		const pass = result.mismatches.length === 0;
		const icon = pass ? "PASS" : "FAIL";
		console.log("  " + icon + " - " + result.mismatches.length + " issues");
		if (result.mismatches.length > 0 && result.mismatches.length < 200) {
			for (const m of result.mismatches.slice(0, 5)) {
				console.log(
					"    " +
						m.key +
						" . " +
						m.field +
						": Excel=" +
						JSON.stringify(m.excel_val) +
						" API=" +
						JSON.stringify(m.api_val)
				);
			}
		}

		summaryRows.push({
			Sheet: config.label,
			Doctype: config.doctype,
			Status: pass ? "PASS" : "FAIL",
			Excel_Count: result.excelCount,
			API_Count: result.apiCount,
			Issues: result.mismatches.length,
		});

		if (result.mismatches.length > 0) {
			const detailRows = result.mismatches.map((m) => ({
				Key: m.key,
				Field: m.field,
				Excel_Value: m.excel_val,
				API_Value: m.api_val,
				Status: m.status,
			}));
			const ws = xlsx.utils.json_to_sheet(detailRows);
			xlsx.utils.book_append_sheet(wbOut, ws, config.label);
		}
	}

	const wsSummary = xlsx.utils.json_to_sheet(summaryRows);
	xlsx.utils.book_append_sheet(wbOut, wsSummary, "Summary");

	const outFile = path.join(dir, "CD-ERPNext Validation Results.xlsx");
	xlsx.writeFile(wbOut, outFile);
	console.log("\nExported to:", outFile);
	process.exit(0);
})();
