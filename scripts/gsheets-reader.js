const { google } = require("googleapis");
const path = require("path");
const fs = require("fs");

const SHEET_ID = process.env.GOOGLE_SHEET_ID || "1P40NXIF72wm4YVLfqN0l3-W3GXLt2GVraVLY9bKZXFQ";

async function getAuth() {
	if (process.env.GOOGLE_APPLICATION_CREDENTIALS) {
		const auth = new google.auth.GoogleAuth({
			keyFile: process.env.GOOGLE_APPLICATION_CREDENTIALS,
			scopes: ["https://www.googleapis.com/auth/spreadsheets.readonly"],
		});
		return auth;
	}
	const auth = new google.auth.GoogleAuth({
		scopes: ["https://www.googleapis.com/auth/spreadsheets.readonly"],
	});
	return auth;
}

async function getSheetClient() {
	const auth = await getAuth();
	return google.sheets({ version: "v4", auth });
}

async function listSheets() {
	const sheets = await getSheetClient();
	const res = await sheets.spreadsheets.get({ spreadsheetId: SHEET_ID });
	console.log("Google Sheets tabs:");
	for (const s of res.data.sheets) {
		console.log(`  - ${s.properties.title} (gid=${s.properties.sheetId})`);
	}
	return res.data.sheets.map((s) => ({
		title: s.properties.title,
		gid: s.properties.sheetId,
	}));
}

async function getSheetData(sheetName) {
	const sheets = await getSheetClient();
	const res = await sheets.spreadsheets.values.get({
		spreadsheetId: SHEET_ID,
		range: sheetName,
	});
	const rows = res.data.values;
	if (!rows || rows.length === 0) {
		console.log(`  Sheet "${sheetName}": empty`);
		return [];
	}
	const headers = rows[0];
	const data = [];
	for (let i = 1; i < rows.length; i++) {
		const row = {};
		for (let j = 0; j < headers.length; j++) {
			row[headers[j]] = rows[i][j] || "";
		}
		data.push(row);
	}
	console.log(`  Sheet "${sheetName}": ${data.length} rows, ${headers.length} columns`);
	return data;
}

async function loadAllSheets() {
	console.log(`Loading Google Sheet: ${SHEET_ID}`);
	const tabs = await listSheets();
	const result = new Map();
	for (const tab of tabs) {
		const data = await getSheetData(tab.title);
		result.set(tab.title, data);
	}
	console.log(`\nLoaded ${result.size} sheets from Google Sheets`);
	return result;
}

module.exports = { listSheets, getSheetData, loadAllSheets, SHEET_ID };

if (require.main === module) {
	(async () => {
		const sheets = await loadAllSheets();
		console.log("\nSheet names:", [...sheets.keys()]);
		for (const [name, rows] of sheets) {
			if (rows.length > 0) {
				console.log(`  ${name}: ${rows.length} rows, columns: ${Object.keys(rows[0]).join(", ")}`);
			}
		}
	})();
}
