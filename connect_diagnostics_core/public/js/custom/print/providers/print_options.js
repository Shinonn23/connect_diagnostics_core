// Copyright (c) 2026, Siwat Sroisuwan and contributors
// For license information, please see license.txt

// Print sidebar provider: Print Options.
//
// Static registry-driven controls (language, show date, customer print name,
// per-copy-type counts, batch/serial, and the quotation validity/delivery fields)
// resolved by
// `connect_diagnostics_core.api.erpnext.print_configuration.get_print_options`.
// There is no per-Customer configuration: every print is chosen fresh here. The
// chosen values ride in `additional_settings` under the `cd_` prefix, which the
// server print context reads back. Registered on the print sidebar engine
// (see ../engine.js).

(() => {
	const PrintView = frappe.ui.form.PrintView;
	if (!PrintView) {
		return;
	}

	// Doctypes that resolve to a configured print document — mirrors
	// connect_diagnostics_core/setup/print_documents.py: PRINT_DOCUMENTS.
	// (Abbreviated Tax Invoice is a Sales Invoice format, already covered here.)
	const SUPPORTED_DOCTYPES = ["Quotation", "Sales Order", "Sales Invoice", "Payment Entry"];

	frappe.provide("connect_diagnostics.print").register({
		name: "print_options",
		applies_to: (view) => SUPPORTED_DOCTYPES.includes(view.frm.doc.doctype),
		load: (view) =>
			frappe.xcall("connect_diagnostics_core.api.erpnext.print_configuration.get_print_options", {
				doctype: view.frm.doc.doctype,
				docname: view.frm.doc.name,
				print_format: view.selected_format(),
			}),
		render: (view, options) => view.cd_render_print_options(options),
		on_error: (view, reason) => frappe.msgprint(__("Could not load print options."), reason),
	});

	PrintView.prototype.cd_render_print_options = function (options) {
		const data = options?.data;
		if (!data?.fields?.length) {
			return;
		}

		// Registry defaults, kept so Reset can restore them without another round trip.
		this.__cd_print_option_defaults = data.values || {};
		this.__cd_print_option_controls = {};

		this.sidebar_dynamic_section.append(`<h6 class="mt-4 mb-2">${__("Print Options")}</h6>`);

		for (const df of data.fields) {
			const value = data.values?.[df.fieldname] ?? "";
			const field = this.add_sidebar_item(
				{
					...df,
					fieldname: `cd_${df.fieldname}`,
					change: () => {
						this.additional_settings[field.df.fieldname] = field.get_value();
						this.preview();
					},
				},
				true,
			);
			field.set_input(value);
			this.additional_settings[field.df.fieldname] = value;
			this.__cd_print_option_controls[df.fieldname] = field;
		}

		this.cd_add_print_option_reset();
	};

	PrintView.prototype.cd_add_print_option_reset = function () {
		const $reset = $(
			`<button type="button" class="btn btn-xs btn-default mt-2">${__("Reset to default")}</button>`,
		).appendTo(this.sidebar_dynamic_section);

		$reset.on("click", () => {
			const defaults = this.__cd_print_option_defaults || {};
			for (const [fieldname, field] of Object.entries(this.__cd_print_option_controls || {})) {
				const value = defaults[fieldname] ?? "";
				field.set_input(value);
				this.additional_settings[field.df.fieldname] = value;
			}
			this.preview();
		});
	};
})();
