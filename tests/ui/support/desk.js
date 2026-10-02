import { expect } from "@playwright/test";

export class DeskSession {
	constructor(page, baseURL) {
		this.page = page;
		this.baseURL = baseURL;
	}

	async login(actor) {
		const passwordName = `PLAYWRIGHT_PASSWORD_${actor.key.toUpperCase().replaceAll(/[^A-Z0-9]/g, "_")}`;
		const password = globalThis.process.env[passwordName];
		if (!password) {
			throw new Error(`Missing password environment variable ${passwordName} for actor ${actor.key}.`);
		}

		await this.page.goto(new globalThis.URL("/login", this.baseURL).toString());
		await this.page.locator("#login_email").fill(actor.email);
		await this.page.locator("#login_password").fill(password);
		await this.page.getByRole("button", { name: /^continue$/i }).click();
		await expect(this.page).toHaveURL(/\/app(?:\/|$)/);

		const identity = await this.page.evaluate(() => ({
			user: frappe?.boot?.user?.name,
			roles: frappe?.boot?.user?.roles,
		}));
		if (identity.user !== actor.email) {
			throw new Error(
				`Desk authenticated ${identity.user ?? "an unknown user"}, expected ${actor.email}.`,
			);
		}
		const requiredRoles = actor.roles ?? [actor.role];
		const missingRoles = requiredRoles.filter((role) => !identity.roles?.includes(role));
		if (!Array.isArray(identity.roles) || missingRoles.length) {
			throw new Error(`Authenticated user is missing scenario roles: ${missingRoles.join(", ")}.`);
		}
		return identity;
	}

	async openDocument(doctype, name) {
		const route = DeskSession.documentRoute(doctype, name);
		await this.page.goto(new globalThis.URL(route, this.baseURL).toString());
		await expect(this.page.locator(".form-layout")).toBeVisible();
		await expect(this.page.locator(".page-title")).toContainText(name);
	}

	static documentRoute(doctype, name) {
		const route = doctype
			.toLowerCase()
			.replaceAll(/[^a-z0-9]+/g, "-")
			.replace(/^-|-$/g, "");
		return `/app/${route}/${encodeURIComponent(name)}`;
	}

	async visibleWorkflowStates() {
		const states = [];
		const indicator = this.page.locator(".title-area .indicator-pill:not(.hide)");
		if (await indicator.isVisible()) {
			const label = (await indicator.innerText()).trim();
			if (label) states.push(label);
		}

		const fieldValue = this.page.locator('[data-fieldname="workflow_state"] .control-value');
		if (await fieldValue.isVisible()) {
			const label = (await fieldValue.innerText()).trim();
			if (label) states.push(label);
		}
		return states;
	}

	async expectState(state) {
		await expect.poll(() => this.visibleWorkflowStates()).toContain(state);
	}

	async actionItem(action) {
		const item = this.page.getByRole("link", { name: action, exact: true });
		if (await item.isVisible().catch(() => false)) return item;

		const toggle = this.page.locator(".actions-btn-group .dropdown-toggle").first();
		await expect(toggle, `Workflow action menu should be available for ${action}.`).toBeVisible();
		await toggle.click();
		await expect(item, `Workflow action ${action} should be available to this actor.`).toBeVisible();
		return item;
	}

	async clickWorkflowAction(action) {
		await (await this.actionItem(action)).click();
		const confirmation = this.page.locator(".modal.show");
		if (await confirmation.isVisible().catch(() => false)) {
			await confirmation.getByRole("button", { name: /^(yes|confirm)$/i }).click();
		}
	}

	async expectActionUnavailable(action) {
		const item = this.page.getByRole("link", { name: action, exact: true });
		const toggle = this.page.locator(".actions-btn-group .dropdown-toggle").first();
		if ((await item.count()) === 0 && (await toggle.isVisible().catch(() => false))) await toggle.click();
		await expect(item).toHaveCount(0);
	}
}
