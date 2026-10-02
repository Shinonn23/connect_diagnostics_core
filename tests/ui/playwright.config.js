import { defineConfig } from "@playwright/test";
import path from "node:path";

const baseURL = globalThis.process.env.PLAYWRIGHT_BASE_URL ?? "http://dev.erp.connectdiagnostics.test";
const runId = globalThis.process.env.PLAYWRIGHT_RUN_ID ?? new Date().toISOString().replaceAll(/[:.]/g, "-");
if (!/^[A-Za-z0-9._-]+$/.test(runId))
	throw new Error("PLAYWRIGHT_RUN_ID may contain only letters, numbers, dot, underscore, and hyphen.");
const evidenceDir = path.resolve("test-results", "playwright", runId);

export default defineConfig({
	testDir: ".",
	testMatch: "workflow-journey.spec.js",
	timeout: 120_000,
	expect: { timeout: 20_000 },
	fullyParallel: false,
	workers: 1,
	retries: 0,
	forbidOnly: Boolean(globalThis.process.env.CI),
	outputDir: path.join(evidenceDir, "results"),
	reporter: [["list"], ["html", { outputFolder: path.join(evidenceDir, "report"), open: "never" }]],
	use: {
		baseURL,
		browserName: "chromium",
		headless: true,
		viewport: { width: 1440, height: 1000 },
		screenshot: "only-on-failure",
		video: "off",
		trace: "off",
		launchOptions: {
			args: ["--host-resolver-rules=MAP dev.erp.connectdiagnostics.test 127.0.0.1"],
		},
	},
});
