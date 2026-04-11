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

/** Entry point หลัก: ตรวจสอบ item prices และ chart of accounts โดยเปรียบเทียบ API กับ Excel */
(async () => {
	const sid = await login();

	// ========================================
	// 1. NEW ITEM PRICES (API has, Excel doesn't)
	// ========================================
	console.log("╔══════════════════════════════════════════════════════╗");
	console.log("║  NEW ITEM PRICES CHECK (API extra vs Excel)          ║");
	console.log("╚══════════════════════════════════════════════════════╝\n");

	const ipParams = new URLSearchParams();
	ipParams.set("doctype", "Item Price");
	ipParams.set(
		"fields",
		JSON.stringify([
			"name",
			"item_code",
			"item_name",
			"price_list",
			"price_list_rate",
			"buying",
			"selling",
			"currency",
			"valid_from",
			"valid_upto",
			"creation",
		])
	);
	ipParams.set("limit_page_length", "0");
	const ipRes = await apiGet("/api/method/frappe.client.get_list?" + ipParams.toString(), sid);
	const apiPrices = (ipRes.message || []).sort((a, b) =>
		(b.creation || "").localeCompare(a.creation || "")
	);

	const dir = process.env.EXCEL_DIR || path.join(os.homedir(), "Desktop");
	const files = fs.readdirSync(dir);
	const match = files.find(
		(f) => f.startsWith("CD-ERPNext") && f.includes("v.3") && f.endsWith(".xlsx")
	);
	const wb = xlsx.readFile(path.join(dir, match));
	const ipExcel = xlsx.utils.sheet_to_json(wb.Sheets["Item_Prices"], { defval: "" });

	// Excel lookup
	const excelItemPL = new Set();
	const excelItemPLMap = new Map();
	for (const r of ipExcel) {
		const key = r["Item Code"] + "|" + r["Price List"];
		excelItemPL.add(key);
		excelItemPLMap.set(key, r);
	}

	// Separate: matched vs new
	const newPrices = apiPrices.filter((r) => !excelItemPL.has(r.item_code + "|" + r.price_list));
	const matchedPrices = apiPrices.filter((r) =>
		excelItemPL.has(r.item_code + "|" + r.price_list)
	);

	console.log("API total:", apiPrices.length);
	console.log("Excel total:", ipExcel.length);
	console.log("Matched (Excel + API):", matchedPrices.length);
	console.log("NEW (API only, not in Excel):", newPrices.length);

	// New by price list
	const newByPL = {};
	for (const r of newPrices) {
		const pl = r.price_list || "(empty)";
		if (!newByPL[pl]) newByPL[pl] = [];
		newByPL[pl].push(r);
	}
	console.log("\nNew Item Prices by Price List:");
	for (const [pl, items] of Object.entries(newByPL).sort((a, b) => b[1].length - a[1].length)) {
		console.log("  " + pl + ": " + items.length + " items");
	}

	// New Standard Buying detail (first 30)
	const newSB = newPrices.filter((r) => r.price_list === "Standard Buying");
	console.log("\nNEW Standard Buying (" + newSB.length + " items):");
	for (const r of newSB.slice(0, 30)) {
		console.log(
			"  " +
				r.item_code +
				" | " +
				(r.item_name || "").substring(0, 30) +
				" | rate=" +
				r.price_list_rate +
				" | created=" +
				(r.creation || "").substring(0, 10)
		);
	}
	if (newSB.length > 30) console.log("  ... and " + (newSB.length - 30) + " more");

	// New Standard Selling detail
	const newSS = newPrices.filter((r) => r.price_list === "Standard Selling");
	console.log("\nNEW Standard Selling (" + newSS.length + " items):");
	for (const r of newSS) {
		console.log(
			"  " +
				r.item_code +
				" | " +
				(r.item_name || "").substring(0, 30) +
				" | rate=" +
				r.price_list_rate +
				" | created=" +
				(r.creation || "").substring(0, 10)
		);
	}

	// Rate comparison for matched items
	console.log("\nRate comparison (matched items):");
	let rateMatch = 0,
		rateDiff = 0;
	const rateDiffItems = [];
	for (const r of matchedPrices) {
		const key = r.item_code + "|" + r.price_list;
		const excelRow = excelItemPLMap.get(key);
		if (!excelRow) continue;
		const excelRate = parseFloat(excelRow["Price List Rate"] || excelRow["Rate"] || 0);
		const apiRate = parseFloat(r.price_list_rate || 0);
		if (Math.abs(excelRate - apiRate) > 0.01) {
			rateDiff++;
			rateDiffItems.push({
				code: r.item_code,
				pl: r.price_list,
				excel: excelRate,
				api: apiRate,
			});
		} else {
			rateMatch++;
		}
	}
	console.log("  Rate matched:", rateMatch);
	console.log("  Rate different:", rateDiff);
	if (rateDiff > 0) {
		for (const r of rateDiffItems.slice(0, 20)) {
			console.log("    " + r.code + " | " + r.pl + " | Excel=" + r.excel + " API=" + r.api);
		}
		if (rateDiff > 20) console.log("    ... and " + (rateDiff - 20) + " more");
	}

	// ========================================
	// 2. COA (Chart of Accounts) FULL CHECK
	// ========================================
	console.log("\n╔══════════════════════════════════════════════════════╗");
	console.log("║  COA - CHART OF ACCOUNTS FULL CHECK                 ║");
	console.log("╚══════════════════════════════════════════════════════╝\n");

	const accParams = new URLSearchParams();
	accParams.set("doctype", "Account");
	accParams.set(
		"fields",
		JSON.stringify([
			"name",
			"account_name",
			"account_number",
			"account_type",
			"root_type",
			"is_group",
			"parent_account",
			"company",
			"disabled",
		])
	);
	accParams.set("filters", JSON.stringify({ company: "Connect Diagnostics" }));
	accParams.set("limit_page_length", "0");
	const accRes = await apiGet("/api/method/frappe.client.get_list?" + accParams.toString(), sid);
	const apiAccounts = accRes.message || [];

	const accExcel = xlsx.utils.sheet_to_json(wb.Sheets["Accounts New"], { defval: "" });

	// API map
	const apiAccByNum = new Map();
	const apiAccByName = new Map();
	for (const r of apiAccounts) {
		const num = (r.account_number || r.name.split(" - ")[0]).trim();
		apiAccByNum.set(num, r);
		apiAccByName.set(r.name, r);
	}

	console.log("Excel accounts:", accExcel.length);
	console.log("API accounts:", apiAccounts.length);

	// 2a. Missing in API
	const missing = accExcel.filter((r) => !apiAccByNum.has(r["Account Number"]));
	console.log("\n1) Missing in API:", missing.length);
	for (const r of missing) console.log("  " + r["Account Number"] + " | " + r["Account Name"]);

	// 2b. Extra in API
	const excelAccNums = new Set(accExcel.map((r) => r["Account Number"]));
	const extra = apiAccounts.filter((r) => {
		const num = (r.account_number || r.name.split(" - ")[0]).trim();
		return !excelAccNums.has(num);
	});
	console.log("\n2) Extra in API (not in Excel):", extra.length);
	for (const r of extra)
		console.log(
			"  " +
				r.name +
				" | type=" +
				(r.account_type || "(empty)") +
				" | root=" +
				r.root_type +
				" | group=" +
				r.is_group
		);

	// 2c. account_type issues
	console.log("\n3) account_type issues:");
	let emptyType = 0,
		typeMismatch = 0,
		namingDiff = 0;
	const realEmpty = [];
	const realMismatch = [];

	for (const r of accExcel) {
		const apiAcc = apiAccByNum.get(r["Account Number"]);
		if (!apiAcc) continue;
		const excelType = (r["Account Type"] || "").trim();
		const apiType = (apiAcc.account_type || "").trim();

		if (excelType && !apiType) {
			emptyType++;
			realEmpty.push({
				num: r["Account Number"],
				name: r["Account Name"],
				should: excelType,
			});
		} else if (excelType && apiType && excelType !== apiType) {
			const isNaming =
				apiType.toLowerCase().includes(excelType.toLowerCase()) ||
				excelType.toLowerCase().includes(apiType.toLowerCase()) ||
				excelType.toLowerCase().replace(/ /g, "") ===
					apiType.toLowerCase().replace(/ /g, "");
			if (isNaming) {
				namingDiff++;
			} else {
				typeMismatch++;
				realMismatch.push({
					num: r["Account Number"],
					name: r["Account Name"],
					excel: excelType,
					api: apiType,
				});
			}
		}
	}
	console.log("  account_type empty (should have value):", emptyType);
	for (const r of realEmpty)
		console.log("    [EMPTY] " + r.num + " | " + r.name + ' | should be="' + r.should + '"');
	console.log(
		"  account_type naming convention diff:",
		namingDiff,
		"(Expense vs Expense Account - OK)"
	);
	console.log("  account_type real mismatch:", typeMismatch);
	for (const r of realMismatch)
		console.log(
			"    [MISMATCH] " +
				r.num +
				" | " +
				r.name +
				' | Excel="' +
				r.excel +
				'" API="' +
				r.api +
				'"'
		);

	// 2d. Root type check
	console.log("\n4) Root type validation:");
	for (const r of accExcel) {
		const apiAcc = apiAccByNum.get(r["Account Number"]);
		if (!apiAcc) continue;
		const excelRoot = (r["Root Type"] || "").trim();
		const apiRoot = (apiAcc.root_type || "").trim();
		if (excelRoot && apiRoot && excelRoot !== apiRoot) {
			console.log(
				"  [ROOT DIFF] " +
					r["Account Number"] +
					" | " +
					r["Account Name"] +
					' | Excel="' +
					excelRoot +
					'" API="' +
					apiRoot +
					'"'
			);
		}
	}

	// 2e. is_group check
	console.log("\n5) is_group validation:");
	for (const r of accExcel) {
		const apiAcc = apiAccByNum.get(r["Account Number"]);
		if (!apiAcc) continue;
		const excelGroup = (r["Is Group"] || "").toString().trim().toLowerCase();
		const apiGroup = apiAcc.is_group ? "1" : "0";
		if (excelGroup && excelGroup !== apiGroup) {
			console.log(
				"  [GROUP DIFF] " +
					r["Account Number"] +
					" | " +
					r["Account Name"] +
					" | Excel=" +
					excelGroup +
					" API=" +
					apiGroup
			);
		}
	}

	// 2f. Disabled accounts
	const disabledAcc = apiAccounts.filter((r) => r.disabled);
	console.log("\n6) Disabled accounts:", disabledAcc.length);
	for (const r of disabledAcc)
		console.log("  " + r.name + " | type=" + (r.account_type || "(empty)"));

	// 2g. Full tree summary
	console.log("\n7) Account Tree Summary:");
	const rootAcc = apiAccounts.filter((r) => !r.parent_account || r.parent_account === "");
	for (const root of rootAcc) {
		const children = apiAccounts.filter((a) => {
			let p = a.parent_account || "";
			while (p) {
				if (p === root.name) return true;
				const parent = apiAccounts.find((x) => x.name === p);
				p = parent ? parent.parent_account || "" : "";
			}
			return false;
		});
		console.log(
			"  " + root.name + " (" + root.root_type + "): " + (children.length + 1) + " accounts"
		);
	}

	process.exit(0);
})();
