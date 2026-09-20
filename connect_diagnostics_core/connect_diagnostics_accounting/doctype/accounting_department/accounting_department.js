// Copyright (c) 2026, Siwat Sroisuwan and contributors
// For license information, please see license.txt

frappe.ui.form.on("Accounting Department", {
	onload: function (frm) {
		frm.set_query("parent_accounting_department", function () {
			return {
				filters: {
					company: frm.doc.company,
					is_group: 1,
				},
			};
		});
	},
	refresh: function (frm) {
		if (!frm.is_new()) {
			frm.add_custom_button(__("Update Department Name / Number"), function () {
				frm.trigger("update_department_number");
			});
		}

		let intro_txt = "";
		let doc = frm.doc;
		frm.toggle_display("department_name", doc.__islocal);
		frm.toggle_enable(["is_group", "company"], doc.__islocal);

		if (!doc.__islocal && doc.is_group == 1) {
			intro_txt += __(
				"Note: This Accounting Department is a Group. Cannot make accounting entries against groups.",
			);
		}

		frm.events.hide_unhide_group_ledger(frm);

		frm.set_intro(intro_txt);

		if (!frm.doc.__islocal) {
			frm.add_custom_button(__("Chart of Accounting Departments"), function () {
				frappe.set_route("Tree", "Accounting Department");
			});
		}
	},

	update_department_number: function (frm) {
		var d = new frappe.ui.Dialog({
			title: __("Update Department Name / Number"),
			fields: [
				{
					label: __("Department Name"),
					fieldname: "department_name",
					fieldtype: "Data",
					reqd: 1,
					default: frm.doc.department_name,
				},
				{
					label: __("Department Number"),
					fieldname: "department_number",
					fieldtype: "Data",
					default: frm.doc.department_number,
				},
				{
					label: __("Merge with existing"),
					fieldname: "merge",
					fieldtype: "Check",
					default: 0,
				},
			],
			primary_action: function () {
				let data = d.get_values();
				if (
					data.department_name === frm.doc.department_name &&
					data.department_number === frm.doc.department_number
				) {
					d.hide();
					return;
				}
				frappe.dom.freeze();
				frappe.call({
					method: "connect_diagnostics_core.connect_diagnostics_accounting.doctype.accounting_department.accounting_department.update_accounting_department",
					args: {
						docname: frm.doc.name,
						department_name: data.department_name,
						department_number: cstr(data.department_number),
						company: frm.doc.company,
						merge: data.merge,
					},
					callback: function (r) {
						frappe.dom.unfreeze();
						if (!r.exc) {
							if (r.message) {
								frappe.set_route("Form", "Accounting Department", r.message);
							} else {
								frm.set_value("department_name", data.department_name);
								frm.set_value("department_number", data.department_number);
							}
							d.hide();
						}
					},
				});
			},
			primary_action_label: __("Update"),
		});
		d.show();
	},

	parent_accounting_department(frm) {
		if (!frm.doc.company) {
			frappe.msgprint(__("Please enter company name first"));
		}
	},

	hide_unhide_group_ledger(frm) {
		let doc = frm.doc;
		if (doc.is_group == 1) {
			frm.add_custom_button(__("Convert to Non-Group"), () => frm.events.convert_to_ledger(frm));
		} else if (doc.is_group == 0) {
			frm.add_custom_button(__("Convert to Group"), () => frm.events.convert_to_group(frm));
		}
	},

	convert_to_group(frm) {
		frm.call("convert_ledger_to_group").then((r) => {
			if (r.message === 1) {
				frm.refresh();
			}
		});
	},

	convert_to_ledger(frm) {
		frm.call("convert_group_to_ledger").then((r) => {
			if (r.message === 1) {
				frm.refresh();
			}
		});
	},
});
