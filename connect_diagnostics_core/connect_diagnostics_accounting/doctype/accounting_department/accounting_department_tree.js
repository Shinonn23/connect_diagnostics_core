frappe.treeview_settings["Accounting Department"] = {
	breadcrumb: "Connect Diagnostics Accounting",
	get_tree_root: false,
	filters: [
		{
			fieldname: "company",
			fieldtype: "Select",

			options: erpnext.utils.get_tree_options("company"),
			label: __("Company"),

			default: erpnext.utils.get_tree_default("company"),
		},
	],
	root_label: "Accounting Departments",
	get_tree_nodes: "erpnext.accounts.utils.get_children",
	add_tree_node:
		"connect_diagnostics_core.connect_diagnostics_accounting.doctype.accounting_department.accounting_department.add_node",
	menu_items: [
		{
			label: __("New Company"),
			action: function () {
				frappe.new_doc("Company", true);
			},
			condition: 'frappe.boot.user.can_create.indexOf("Company") !== -1',
		},
	],
	fields: [
		{
			fieldtype: "Data",
			fieldname: "department_name",
			label: __("New Department Name"),
			reqd: true,
		},
		{
			fieldtype: "Check",
			fieldname: "is_group",
			label: __("Is Group"),
			description: __(
				"Further accounting departments can be made under Groups but entries can be made against non-Groups",
			),
		},
		{
			fieldtype: "Data",
			fieldname: "department_number",
			label: __("Department Number"),
			description: __(
				"Number of new Accounting Department, it will be included in the department name as a prefix",
			),
		},
	],
	ignore_fields: ["parent_accounting_department"],
	onload: function (treeview) {
		function get_company() {
			return treeview.page.fields_dict.company.get_value();
		}

		treeview.page.add_inner_button(
			__("Chart of Accounts"),
			function () {
				frappe.set_route("Tree", "Account", { company: get_company() });
			},
			__("View"),
		);
	},
};
