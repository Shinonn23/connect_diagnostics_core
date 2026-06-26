// Copyright (c) 2026, Siwat Sroisuwan and contributors
// For license information, please see license.txt

frappe.ui.form.on("Department User Permission", {
	refresh: function (frm) {
		if (!frm.is_new()) {
			frm.add_custom_button(__("Apply Permissions"), function () {
				frappe.confirm(
					__("Are you sure you want to apply this permission to the selected users?"),
					function () {
						frappe.call({
							method: "connect_diagnostics_core.connect_diagnostics_core.doctype.department_user_permission.department_user_permission.apply_permissions",
							args: {
								docname: frm.doc.name,
							},
							freeze: true,
							freeze_message: __("Applying Permissions..."),
							callback: function (r) {
								if (!r.exc && r.message) {
									frappe.show_alert({
										message: __("Applied permissions to {0} users, updated {1} users.", [
											r.message.applied,
											r.message.updated,
										]),
										indicator: "green",
									});
								}
							},
						});
					},
				);
			}).addClass("btn-primary");

			frm.add_custom_button(__("Remove Permissions"), function () {
				frappe.confirm(
					__("Are you sure you want to remove this permission from the selected users?"),
					function () {
						frappe.call({
							method: "connect_diagnostics_core.connect_diagnostics_core.doctype.department_user_permission.department_user_permission.remove_permissions",
							args: {
								docname: frm.doc.name,
							},
							freeze: true,
							freeze_message: __("Removing Permissions..."),
							callback: function (r) {
								if (!r.exc && r.message) {
									frappe.show_alert({
										message: __("Removed permissions from {0} users.", [
											r.message.removed,
										]),
										indicator: "orange",
									});
								}
							},
						});
					},
				);
			});
		}
	},
	department: function (frm) {
		if (frm.doc.department) {
			frappe.call({
				method: "connect_diagnostics_core.connect_diagnostics_core.doctype.department_user_permission.department_user_permission.get_employees_in_department",
				args: {
					department: frm.doc.department,
				},
				callback: function (r) {
					frm.clear_table("users");
					if (r.message && r.message.length > 0) {
						$.each(r.message, function (i, emp) {
							var row = frm.add_child("users");
							row.user = emp.user_id;
							row.employee = emp.name;
							row.employee_name = emp.employee_name;
							row.apply = 1;
						});
					}
					frm.refresh_field("users");
				},
			});
		} else {
			frm.clear_table("users");
			frm.refresh_field("users");
		}
	},
});
