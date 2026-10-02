import { mkdir, readFile } from "node:fs/promises";
import path from "node:path";

import { expect, test } from "@playwright/test";

import { DeskSession } from "./support/desk.js";

function loadScenario() {
	const file = globalThis.process.env.PLAYWRIGHT_SCENARIO_FILE;
	if (!file) {
		throw new Error("Set PLAYWRIGHT_SCENARIO_FILE to an approved disposable Desk journey JSON file.");
	}
	return readFile(path.resolve(file), "utf8").then((source) => JSON.parse(source));
}

function validateScenario(scenario) {
	if (
		!scenario.id ||
		!scenario.title ||
		!scenario.doctype ||
		!scenario.document ||
		!scenario.initialState
	) {
		throw new Error("Scenario must define id, title, doctype, document, and initialState.");
	}
	if (!scenario.actors || !Array.isArray(scenario.steps) || scenario.steps.length === 0) {
		throw new Error("Scenario must define actors and at least one ordered workflow action.");
	}
	const emails = Object.values(scenario.actors).map((actor) =>
		typeof actor.email === "string" ? actor.email.toLowerCase() : "",
	);
	if (emails.some((email) => !email) || new Set(emails).size !== emails.length) {
		throw new Error("Each scenario actor must have a distinct, valid email identity.");
	}
	for (const [key, actor] of Object.entries(scenario.actors)) {
		const roles = actor.roles ?? (actor.role ? [actor.role] : []);
		if (!/^[a-z0-9_-]+$/i.test(key) || !roles.length || roles.some((role) => typeof role !== "string")) {
			throw new Error(`Actor ${key} needs a safe actor key and at least one expected role.`);
		}
		actor.key = key;
	}
	for (const [index, step] of scenario.steps.entries()) {
		if (
			!scenario.actors[step.actor] ||
			!step.action ||
			(step.kind === "assert-unavailable" ? !step.expectedBefore : !step.expectedState)
		) {
			throw new Error(`Scenario step ${index + 1} needs a known actor, action, and expected state.`);
		}
	}
}

test("configured workflow journey uses real Desk sessions and captures evidence", async ({
	browser,
	baseURL,
}, info) => {
	const scenario = await loadScenario();
	validateScenario(scenario);
	const sessions = new Map();
	const manifest = {
		scenario: scenario.id,
		title: scenario.title,
		doctype: scenario.doctype,
		document: scenario.document,
		route: DeskSession.documentRoute(scenario.doctype, scenario.document),
		steps: [],
		actorRecordings: [],
	};

	async function sessionFor(actorKey) {
		if (sessions.has(actorKey)) return sessions.get(actorKey);
		const actor = scenario.actors[actorKey];
		const recordingDir = info.outputPath("recordings", actorKey);
		await mkdir(recordingDir, { recursive: true });
		const context = await browser.newContext({
			baseURL,
			viewport: { width: 1440, height: 1000 },
			recordVideo: { dir: recordingDir, size: { width: 1440, height: 1000 } },
		});
		const page = await context.newPage();
		const desk = new DeskSession(page, baseURL);
		const session = { actor, context, page, desk, identity: null, video: page.video() };
		sessions.set(actorKey, session);
		session.identity = await desk.login(actor);
		return session;
	}

	try {
		const first = await sessionFor(scenario.steps[0].actor);
		await first.desk.openDocument(scenario.doctype, scenario.document);
		await first.desk.expectState(scenario.initialState);

		for (const [index, step] of scenario.steps.entries()) {
			const current = await sessionFor(step.actor);
			await current.desk.openDocument(scenario.doctype, scenario.document);
			if (step.expectedBefore) await current.desk.expectState(step.expectedBefore);
			if (step.kind === "assert-unavailable") {
				await current.desk.expectActionUnavailable(step.action);
			} else {
				await current.desk.clickWorkflowAction(step.action);
				await current.desk.expectState(step.expectedState);
			}

			const screenshotPath = info.outputPath(
				"screenshots",
				`${String(index + 1).padStart(2, "0")}-${step.actor}.png`,
			);
			await mkdir(path.dirname(screenshotPath), { recursive: true });
			await current.page.screenshot({ path: screenshotPath, fullPage: true });
			manifest.steps.push({
				sequence: index + 1,
				actor: step.actor,
				email: current.actor.email,
				roles: current.actor.roles ?? [current.actor.role],
				doctype: scenario.doctype,
				document: scenario.document,
				route: DeskSession.documentRoute(scenario.doctype, scenario.document),
				action: step.action,
				result: step.kind === "assert-unavailable" ? "action unavailable" : "transition completed",
				expectedState: step.expectedState ?? step.expectedBefore,
				observedStates: await current.desk.visibleWorkflowStates(),
				screenshot: screenshotPath,
			});
			await info.attach(`step-${index + 1}-${step.actor}`, {
				path: screenshotPath,
				contentType: "image/png",
			});
		}

		for (const [actorKey, current] of sessions) {
			await current.context.close();
			const videoPath = await current.video.path();
			manifest.actorRecordings.push({
				actor: actorKey,
				email: current.actor.email,
				roles: current.actor.roles ?? [current.actor.role],
				video: videoPath,
			});
			await info.attach(`recording-${actorKey}`, { path: videoPath, contentType: "video/webm" });
		}
		sessions.clear();
		await info.attach("workflow-journey-manifest", {
			body: JSON.stringify(manifest, null, 2),
			contentType: "application/json",
		});
	} finally {
		for (const current of sessions.values()) await current.context.close().catch(() => {});
	}
});
