// Copyright (c) 2026, Siwat Sroisuwan and contributors
// For license information, please see license.txt

(() => {
	const PrintView = frappe.ui.form.PrintView;
	if (!PrintView || PrintView.prototype.__cd_print_configuration_ready) {
		return;
	}

	const originalRefreshPrintFormat = PrintView.prototype.refresh_print_format;
	const originalShow = PrintView.prototype.show;

	PrintView.prototype.setup_additional_settings = function () {
		const requestToken = (this.__cd_print_configuration_request_token || 0) + 1;
		this.__cd_print_configuration_request_token = requestToken;
		this.additional_settings = {};
		this.sidebar_dynamic_section.empty();

		Promise.allSettled([
			frappe.xcall("frappe.printing.page.print.print.get_print_settings_to_show", {
				doctype: this.frm.doc.doctype,
				docname: this.frm.doc.name,
			}),
			frappe.xcall(
				"connect_diagnostics_core.api.erpnext.print_configuration.get_sidebar_configuration",
				{
					doctype: this.frm.doc.doctype,
					docname: this.frm.doc.name,
					print_format: this.selected_format(),
				},
			),
		]).then(([standardResult, configurationResult]) => {
			if (requestToken !== this.__cd_print_configuration_request_token) {
				return;
			}
			if (standardResult.status === "fulfilled") {
				this.add_settings_to_sidebar(standardResult.value);
			}
			if (configurationResult.status === "fulfilled") {
				this.add_customer_print_settings(configurationResult.value);
			} else {
				frappe.msgprint(__("Could not load Customer print options."), configurationResult.reason);
			}
			this.preview();
		});
	};

	PrintView.prototype.add_customer_print_settings = function (configuration) {
		const data = configuration?.data;
		if (!data?.fields?.length) {
			return;
		}

		// Values are resolved server-side; keep them so Reset can restore them
		// without another round trip.
		this.__cd_print_configuration_defaults = data.values || {};
		this.__cd_print_configuration_sources = data.sources || {};
		this.__cd_print_configuration_controls = {};

		this.sidebar_dynamic_section.append(`<h6 class="mt-4 mb-2">${__("Customer Print Options")}</h6>`);

		for (const df of data.fields) {
			const value = data.values?.[df.fieldname] ?? "";
			const field = this.add_sidebar_item(
				{
					...df,
					fieldname: `cd_${df.fieldname}`,
					change: () => {
						this.additional_settings[field.df.fieldname] = field.get_value();
						this.cd_mark_configuration_source(df.fieldname, __("This print"));
						this.preview();
					},
				},
				true,
			);
			field.set_input(value);
			this.additional_settings[field.df.fieldname] = value;
			this.__cd_print_configuration_controls[df.fieldname] = field;
			this.cd_mark_configuration_source(df.fieldname, data.sources?.[df.fieldname]);
		}

		this.cd_add_configuration_reset();
	};

	// Show where each resolved value came from, so a user can tell an inherited
	// Template value apart from one set on this Customer or this print only.
	PrintView.prototype.cd_mark_configuration_source = function (fieldname, source) {
		const field = this.__cd_print_configuration_controls?.[fieldname];
		if (!field?.$wrapper || !source) {
			return;
		}
		let $hint = field.$wrapper.find(".cd-print-source");
		if (!$hint.length) {
			$hint = $('<div class="cd-print-source text-muted small mt-1"></div>').appendTo(field.$wrapper);
		}
		$hint.text(source);
	};

	PrintView.prototype.cd_add_configuration_reset = function () {
		const $reset = $(
			`<button type="button" class="btn btn-xs btn-default mt-2">${__("Reset to default")}</button>`,
		).appendTo(this.sidebar_dynamic_section);

		$reset.on("click", () => {
			const defaults = this.__cd_print_configuration_defaults || {};
			const sources = this.__cd_print_configuration_sources || {};
			for (const [fieldname, field] of Object.entries(this.__cd_print_configuration_controls || {})) {
				const value = defaults[fieldname] ?? "";
				field.set_input(value);
				this.additional_settings[field.df.fieldname] = value;
				this.cd_mark_configuration_source(fieldname, sources[fieldname]);
			}
			this.preview();
		});
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

	PrintView.prototype.__cd_print_configuration_ready = true;
})();
