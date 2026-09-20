// Copyright (c) 2026, Siwat Sroisuwan and contributors
// For license information, please see license.txt

frappe.ui.form.on("Dispatch", {
	setup(frm) {
		frm.set_query("material_request", () => ({
			filters: { company: frm.doc.company, docstatus: 1 },
		}));
		frm.set_query("original_dispatch", () => ({
			filters: {
				company: frm.doc.company,
				material_request: frm.doc.material_request,
				dispatch_type: "Outbound",
				docstatus: 1,
			},
		}));
		frm.set_query("material_request_item", "transfers", () => ({
			filters: { parent: frm.doc.material_request },
		}));
		frm.set_query("reference_name", "transfers", (doc, cdt, cdn) => {
			const row = locals[cdt][cdn];
			if (!row.reference_doctype) return {};
			const filters = { company: doc.company, docstatus: 1 };
			if (row.reference_doctype === "Asset Movement") {
				filters.material_request = doc.material_request;
			}
			return { filters };
		});
		frm.set_query("against_dispatch_transfer", "transfers", () => ({
			filters: { parent: frm.doc.original_dispatch },
		}));
	},
	refresh(frm) {
		if (frm.doc.docstatus === 0 && frm.doc.dispatch_type === "Return" && can_manage_transit()) {
			frm.add_custom_button(__("Prepare Return Transit"), () => prepare_return_transit(frm));
		}
		if (frm.doc.docstatus !== 1) return;
		if (frm.doc.delivery_status === "Failed") {
			frm.add_custom_button(__("Return to Origin"), () => show_return_origin_dialog(frm));
			return;
		}
		if (frm.doc.delivery_status !== "Dispatched") return;

		frm.add_custom_button(__("Confirm Delivery"), () => show_delivery_dialog(frm));
		frm.add_custom_button(__("Override Delivered"), () => show_override_dialog(frm));
		frm.add_custom_button(__("Report Failure"), () => show_failure_dialog(frm));
	},
});

function can_manage_transit() {
	const roles = frappe.user_roles || [];
	return (
		frappe.session.user === "Administrator" ||
		roles.includes("Stock User") ||
		roles.includes("Stock Manager")
	);
}

function prepare_return_transit(frm) {
	const prepare = () =>
		frappe.call({
			method: "connect_diagnostics_core.api.erpnext.dispatch.prepare_return_transit",
			type: "POST",
			freeze: true,
			args: { dispatch: frm.doc.name, company: frm.doc.company },
			callback: () => frm.reload_doc(),
		});
	if (frm.is_dirty()) {
		frm.save().then(prepare);
	} else {
		prepare();
	}
}

function show_delivery_dialog(frm) {
	const dialog = new frappe.ui.Dialog({
		title: __("Confirm Delivery"),
		fields: [
			{ fieldname: "receiver_name", fieldtype: "Data", label: __("Receiver Name"), reqd: 1 },
			{ fieldname: "receiver_contact", fieldtype: "Data", label: __("Receiver Contact") },
			{
				fieldname: "receiver_signature",
				fieldtype: "Signature",
				label: __("Receiver Signature"),
				reqd: 1,
			},
			{ fieldname: "delivery_note", fieldtype: "Small Text", label: __("Delivery Note") },
		],
		primary_action_label: __("Confirm"),
		primary_action(values) {
			frappe.call({
				method: "connect_diagnostics_core.api.erpnext.dispatch.confirm_dispatch_delivery",
				type: "POST",
				args: { dispatch: frm.doc.name, company: frm.doc.company, ...values },
				callback() {
					dialog.hide();
					frm.reload_doc();
				},
			});
		},
	});
	dialog.show();
}

function show_override_dialog(frm) {
	const dialog = new frappe.ui.Dialog({
		title: __("Override Delivered"),
		fields: [
			{ fieldname: "override_reason", fieldtype: "Small Text", label: __("Reason"), reqd: 1 },
			{ fieldname: "receiver_name", fieldtype: "Data", label: __("Receiver Name") },
			{ fieldname: "receiver_contact", fieldtype: "Data", label: __("Receiver Contact") },
			{ fieldname: "override_attachment", fieldtype: "Attach", label: __("Attachment") },
			{ fieldname: "delivery_note", fieldtype: "Small Text", label: __("Delivery Note") },
		],
		primary_action_label: __("Confirm"),
		primary_action(values) {
			frappe.call({
				method: "connect_diagnostics_core.api.erpnext.dispatch.override_dispatch_delivery",
				type: "POST",
				args: { dispatch: frm.doc.name, company: frm.doc.company, ...values },
				callback() {
					dialog.hide();
					frm.reload_doc();
				},
			});
		},
	});
	dialog.show();
}

function show_return_origin_dialog(frm) {
	frappe.prompt(
		[{ fieldname: "reason", fieldtype: "Small Text", label: __("Reason"), reqd: 1 }],
		(values) => {
			frappe.call({
				method: "connect_diagnostics_core.api.erpnext.dispatch.return_dispatch_to_origin",
				type: "POST",
				args: { dispatch: frm.doc.name, company: frm.doc.company, ...values },
				callback: () => frm.reload_doc(),
			});
		},
		__("Return to Origin"),
		__("Confirm"),
	);
}

function show_failure_dialog(frm) {
	frappe.prompt(
		[{ fieldname: "failure_note", fieldtype: "Small Text", label: __("Failure Note"), reqd: 1 }],
		(values) => {
			frappe.call({
				method: "connect_diagnostics_core.api.erpnext.dispatch.report_dispatch_failure",
				type: "POST",
				args: { dispatch: frm.doc.name, company: frm.doc.company, ...values },
				callback: () => frm.reload_doc(),
			});
		},
		__("Report Dispatch Failure"),
		__("Report Failure"),
	);
}
