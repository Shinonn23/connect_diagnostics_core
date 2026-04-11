/**
 * @file รัน master-data-compare Playwright test suite พร้อม dataset JSON file ที่ config ได้
 * วิธีใช้: node run-master-test.js [configPath] [...playwrightArgs]
 */
const { spawnSync } = require("node:child_process");
const playwrightCli = require.resolve("@playwright/test/cli");

const [configPath = "master-data.datasets.v3.json", ...playwrightArgs] = process.argv.slice(2);

const result = spawnSync(
	process.execPath,
	[playwrightCli, "test", "tests/master-data-compare.spec.ts", ...playwrightArgs],
	{
		stdio: "inherit",
		env: {
			...process.env,
			MASTER_DATASETS_CONFIG: configPath,
		},
	}
);

if (typeof result.status === "number") {
	process.exit(result.status);
}

if (result.error) {
	throw result.error;
}

process.exit(1);
