// Copyright (c) 2026, Siwat Sroisuwan and contributors
// For license information, please see license.txt

// Print sidebar engine.
//
// Owns Frappe's print `PrintView` sidebar so that app-specific settings register
// as small self-contained providers instead of accumulating `if doctype/format`
// branches in the core override. When at least one provider applies to the
// current doctype/format, the engine takes over the dynamic sidebar section:
// it hides the Letter Head selector (button only — the default letterhead still
// applies) and skips Frappe's native `get_print_settings` controls, rendering
// the providers instead. When no provider applies, the sidebar is handed back to
// Frappe untouched.
//
// Value transport is Frappe's own: a provider's control writes into
// `additional_settings`, which Frappe merges into `print_settings` for both the
// preview and the printed/PDF output, so a Jinja format reads `print_settings.<field>`.

(() => {
	const CDP = frappe.provide("connect_diagnostics.print");
	CDP.providers = CDP.providers || [];
	// Idempotent by name so re-running the concatenated page script never
	// registers a provider twice.
	CDP.register =
		CDP.register ||
		function (provider) {
			CDP.providers = CDP.providers.filter((existing) => existing.name !== provider.name);
			CDP.providers.push(provider);
		};

	const PrintView = frappe.ui.form.PrintView;
	if (!PrintView || PrintView.prototype.__cd_print_engine_ready) {
		return;
	}

	const originalSetup = PrintView.prototype.setup_additional_settings;
	const originalRefreshPrintFormat = PrintView.prototype.refresh_print_format;
	const originalShow = PrintView.prototype.show;

	PrintView.prototype.setup_additional_settings = function () {
		const applicable = CDP.providers.filter((provider) => {
			try {
				return provider.applies_to(this);
			} catch (error) {
				return false;
			}
		});

		if (!applicable.length) {
			// No provider — restore and hand the sidebar back to Frappe as-is.
			this.letterhead_selector?.$wrapper?.show();
			return originalSetup.call(this);
		}

		const requestToken = (this.__cd_print_engine_token || 0) + 1;
		this.__cd_print_engine_token = requestToken;
		this.additional_settings = {};
		this.sidebar_dynamic_section.empty();
		this.letterhead_selector?.$wrapper?.hide();

		Promise.allSettled(
			applicable.map((provider) =>
				provider.load ? Promise.resolve(provider.load(this)) : Promise.resolve(null),
			),
		).then((results) => {
			if (requestToken !== this.__cd_print_engine_token) {
				return;
			}
			applicable.forEach((provider, index) => {
				const result = results[index];
				if (result.status === "rejected") {
					provider.on_error?.(this, result.reason);
					return;
				}
				this.cd_render_provider(provider, result.value);
			});
			this.preview();
		});
	};

	// Render one provider: imperative providers own their DOM, declarative ones
	// return field descriptors the engine turns into sidebar controls.
	PrintView.prototype.cd_render_provider = function (provider, data) {
		if (provider.render) {
			provider.render(this, data);
			return;
		}
		const fields = provider.build?.(this, data) || [];
		if (!fields.length) {
			return;
		}
		if (provider.section_label) {
			this.sidebar_dynamic_section.append(`<h6 class="mt-4 mb-2">${__(provider.section_label)}</h6>`);
		}
		for (const df of fields) {
			this.cd_add_setting(df, provider.prefix || "");
		}
	};

	// Add one sidebar control and wire its value into `additional_settings` under
	// the provider's prefix, re-previewing on change.
	PrintView.prototype.cd_add_setting = function (df, prefix) {
		const fieldname = `${prefix || ""}${df.fieldname}`;
		const field = this.add_sidebar_item(
			{
				...df,
				fieldname,
				change: () => {
					this.additional_settings[fieldname] = field.get_value();
					this.preview();
				},
			},
			true,
		);
		this.additional_settings[fieldname] = field.get_value();
		return field;
	};

	PrintView.prototype.refresh_print_format = function () {
		originalRefreshPrintFormat.call(this);
		this.setup_additional_settings();
	};

	PrintView.prototype.show = function (frm) {
		return Promise.resolve(originalShow.call(this, frm)).then(() => {
			this.setup_additional_settings();
		});
	};

	PrintView.prototype.__cd_print_engine_ready = true;
})();
