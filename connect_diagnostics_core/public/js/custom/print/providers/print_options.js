// Copyright (c) 2026, Siwat Sroisuwan and contributors
// For license information, please see license.txt

// Print sidebar provider: Print Options.
//
// Static registry-driven controls (language, show date, customer print name,
// per-copy-type counts, batch/serial, and Quotation signatory fields)
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
		this.__cd_manager_signatories = data.manager_signatories || [];

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

		this.cd_prepare_manager_signatory_control();

		this.cd_add_print_option_reset();
	};

	PrintView.prototype.cd_prepare_manager_signatory_control = function () {
		const manager = this.__cd_print_option_controls?.manager_signatory_employee;
		const signatory = this.__cd_print_option_controls?.quotation_signatory_type;
		if (!manager || !signatory) {
			return;
		}

		const labelByEmployee = Object.fromEntries(
			(this.__cd_manager_signatories || []).map((row) => [row.employee, row.name || row.employee]),
		);
		manager.$input?.find("option").each(function () {
			const employee = this.value;
			if (employee && labelByEmployee[employee]) {
				$(this).text(labelByEmployee[employee]);
			}
		});

		const toggle = () => {
			const isManager = signatory.get_value() === "Managing Director";
			manager.$wrapper?.toggle(isManager);
			if (!isManager) {
				manager.set_input("");
				this.additional_settings[manager.df.fieldname] = "";
			}
		};
		signatory.$input?.off("change.cd_quotation_signatory").on("change.cd_quotation_signatory", toggle);
		toggle();
	};

	PrintView.prototype.cd_validate_quotation_signatory = function () {
		if (this.frm?.doc?.doctype !== "Quotation") {
			return true;
		}
		// Once the Workflow has recorded the action, the stored snapshot is the
		// source of truth. Missing Employee signature is intentionally non-blocking.
		if (this.frm.doc.signatory_by || this.frm.doc.signatory_at) {
			return true;
		}
		const signatory = this.__cd_print_option_controls?.quotation_signatory_type?.get_value?.();
		if (signatory === "Managing Director") {
			const manager = this.__cd_print_option_controls?.manager_signatory_employee?.get_value?.();
			if (!manager) {
				frappe.msgprint(__("Select a Manager Signatory before printing."));
				return false;
			}
		} else if (signatory === "Sales Representative" && !this.frm.doc.sales_representative_employee) {
			frappe.msgprint(__("Sales Representative is required before printing."));
			return false;
		}
		return true;
	};

	if (!PrintView.prototype.__cd_signatory_guard_ready) {
		const originalPrintit = PrintView.prototype.printit;
		const originalRenderPdf = PrintView.prototype.render_pdf;
		PrintView.prototype.printit = function (...args) {
			return this.cd_validate_quotation_signatory() ? originalPrintit.apply(this, args) : undefined;
		};
		PrintView.prototype.render_pdf = function (...args) {
			return this.cd_validate_quotation_signatory() ? originalRenderPdf.apply(this, args) : undefined;
		};
		PrintView.prototype.__cd_signatory_guard_ready = true;
	}

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
			this.cd_prepare_manager_signatory_control();
			this.preview();
		});
	};
})();
