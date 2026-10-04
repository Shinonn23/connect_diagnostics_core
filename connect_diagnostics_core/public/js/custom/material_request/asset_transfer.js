// Copyright (c) 2026, Siwat Sroisuwan and contributors
// For license information, please see license.txt

frappe.ui.form.on("Material Request", {
	setup(frm) {
		set_customer_demo_queries(frm);
		frm.set_query("demo_target_location", () => ({
			filters: {
				custom_party_type: "Customer",
				custom_party_name: frm.doc.demo_customer || "",
				is_group: 0,
			},
		}));
		frm.set_query("asset", "demo_candidates", (doc, cdt, cdn) => {
			const candidate = locals[cdt][cdn];
			const requestItem = (doc.items || []).find((row) => row.name === candidate.material_request_item);
			return {
				query: "connect_diagnostics_core.api.erpnext.customer_demo.customer_demo_candidate_asset_query",
				filters: {
					company: doc.company,
					item_code: requestItem?.item_code || "",
					exclude_customer: doc.demo_customer || "",
				},
			};
		});
		frm.set_query("set_warehouse", (doc) => ({
			filters: { company: doc.company, disabled: 0, is_group: 0 },
		}));
		frm.set_query("asset", "asset_transfer_assets", () => ({
			filters: {
				company: frm.doc.company,
				location: frm.doc.asset_source_location,
				docstatus: 1,
				status: ["not in", ["Draft", "Scrapped", "Sold"]],
			},
		}));
		frm.set_query("to_employee", "asset_transfer_assets", (doc, cdt, cdn) => ({
			query: "connect_diagnostics_core.api.erpnext.material_request_asset_transfer.asset_transfer_employee_query",
			filters: {
				company: doc.company,
				preferred_department: locals[cdt][cdn].department || "",
			},
		}));
	},

	onload_post_render(frm) {
		set_customer_demo_queries(frm);
	},

	refresh(frm) {
		set_customer_demo_queries(frm);
		refresh_asset_transfer_ui(frm);
		sync_asset_target_location(frm);
		refresh_customer_demo_ui(frm);
		if (frm.doc.docstatus === 1 && frm.doc.material_request_type === "Asset Transfer") {
			frm.add_custom_button(__("Asset Movement"), () => open_asset_movement(frm), __("Create"));
			frm.page.set_inner_btn_group_as_primary(__("Create"));
		}
	},

	material_request_type(frm) {
		refresh_asset_transfer_ui(frm);
		refresh_customer_demo_ui(frm);
		if (frm.doc.material_request_type !== "Asset Transfer") {
			frm.events.make_custom_buttons(frm);
			refresh_customer_demo_ui(frm);
		}
	},

	demo_customer(frm) {
		frm.set_value("demo_target_location", "");
	},

	asset_target_location(frm) {
		sync_asset_target_location(frm);
	},
});

function refresh_customer_demo_ui(frm) {
	set_standard_warehouse_visibility(frm);
	const isCustomerDemo = frm.doc.material_request_type === "Customer Demo";
	frm.set_df_property("set_warehouse", "label", isCustomerDemo ? __("Source Warehouse") : __("Set Warehouse"));
	frm.toggle_reqd("set_warehouse", isCustomerDemo);
	if (!isCustomerDemo) return;
	for (const button of [
		"Bill of Materials",
		"Sales Order",
		"Pick List",
		"Issue Material",
		"Material Transfer",
		"Material Transfer (In Transit)",
		"Material Receipt",
		"Purchase Order",
		"Request for Quotation",
		"Supplier Quotation",
		"Work Order",
		"Subcontracted Purchase Order",
	]) {
		frm.remove_custom_button(
			__(button),
			button === "Bill of Materials" || button === "Sales Order" ? __("Get Items From") : __("Create"),
		);
	}
	frm.remove_custom_button(__("Stop"));
	frm.remove_custom_button(__("Re-open"));
	if (frm.doc.docstatus !== 1) return;

	frm.add_custom_button(__(frm.doc.demo_status === "Hold" ? "Change Hold" : "Hold"), () => {
		open_customer_demo_hold_dialog(frm);
	});
	frm.add_custom_button(
		__("Asset Capitalization"),
		() => create_customer_demo_capitalizations(frm),
		__("Create"),
	);
	frm.add_custom_button(
		__("Submit Capitalized Assets"),
		() => submit_customer_demo_assets(frm),
		__("Create"),
	);
	frm.add_custom_button(__("Asset Movement"), () => open_customer_demo_movement(frm), __("Create"));
	frm.add_custom_button(__("Return Asset Movement"), () => open_customer_demo_return(frm), __("Create"));
	frm.page.set_inner_btn_group_as_primary(__("Create"));
}

function set_standard_warehouse_visibility(frm) {
	const grid = frm.fields_dict.items?.grid;
	if (!grid) return;

	const hidden = frm.doc.material_request_type === "Customer Demo" ? 1 : 0;
	const parentField = grid.docfields?.find((field) => field.fieldname === "warehouse");
	if (parentField) parentField.hidden = hidden;

	for (const row of grid.grid_rows || []) {
		const rowField = row.docfields?.find((field) => field.fieldname === "warehouse");
		if (rowField) rowField.hidden = hidden;
	}

	const userField = grid.user_defined_columns?.find((field) => field.fieldname === "warehouse");
	if (userField) userField.hidden = hidden;
	grid.refresh();
}

function set_customer_demo_queries(frm) {
	frm.set_query("item_code", "items", (doc) => {
		if (doc.material_request_type === "Customer Borrow") {
			return {
				query: "erpnext.controllers.queries.item_query",
				filters: { is_stock_item: 1, disabled: 0 },
			};
		}
		if (doc.material_request_type !== "Customer Demo") {
			return { query: "erpnext.controllers.queries.item_query" };
		}
		return {
			query: "connect_diagnostics_core.api.erpnext.customer_demo.customer_demo_fixed_asset_item_query",
		};
	});
}

function open_customer_demo_hold_dialog(frm) {
	const dialog = new frappe.ui.Dialog({
		title: __("Hold Customer Demo Request"),
		fields: [
			{
				fieldtype: "Small Text",
				fieldname: "reason",
				label: __("Why is this request on Hold?"),
				reqd: 1,
				default: frm.doc.demo_hold_reason || "",
			},
			{
				fieldtype: "Table",
				fieldname: "candidates",
				label: __("Candidate Assets to Wait For"),
				options: "Material Request Customer Demo Candidate",
				data: (frm.doc.demo_candidates || []).map((row) => ({
					material_request_item: row.material_request_item,
					asset: row.asset,
				})),
			},
		],
		primary_action_label: __("Hold"),
		primary_action: async (values) => {
			await frappe.call({
				method: "connect_diagnostics_core.api.erpnext.customer_demo.hold_customer_demo_request",
				args: {
					material_request: frm.doc.name,
					reason: values.reason,
					candidates: JSON.stringify(values.candidates || []),
				},
			});
			dialog.hide();
			await frm.reload_doc();
		},
	});
	const grid = dialog.fields_dict.candidates?.grid;
	if (grid) {
		grid.get_field("material_request_item").get_query = () => ({
			filters: { parent: frm.doc.name, parenttype: "Material Request", parentfield: "items" },
		});
		grid.get_field("asset").get_query = (_doc, cdt, cdn) => {
			const candidate = locals[cdt][cdn];
			const requestItem = (frm.doc.items || []).find(
				(row) => row.name === candidate.material_request_item,
			);
			return {
				query: "connect_diagnostics_core.api.erpnext.customer_demo.customer_demo_candidate_asset_query",
				filters: {
					company: frm.doc.company,
					item_code: requestItem?.item_code || "",
					exclude_customer: frm.doc.demo_customer || "",
				},
			};
		};
	}
	dialog.show();
}

async function create_customer_demo_capitalizations(frm) {
	const { message } = await frappe.call({
		method: "connect_diagnostics_core.api.erpnext.customer_demo.get_customer_demo_asset_capitalization_drafts",
		args: { material_request: frm.doc.name },
	});
	const drafts = message?.data?.drafts || [];
	if (drafts.length) await frappe.set_route("Form", "Asset Capitalization", drafts[0].asset_capitalization);
	else frappe.msgprint(message?.message || __("There are no stock units to capitalize."));
}

async function submit_customer_demo_assets(frm) {
	const { message } = await frappe.call({
		method: "connect_diagnostics_core.api.erpnext.customer_demo.submit_customer_demo_capitalized_assets",
		args: { material_request: frm.doc.name },
	});
	frappe.show_alert({ message: message?.message || __("Assets submitted.") });
	await frm.reload_doc();
}

async function open_customer_demo_movement(frm) {
	const { message } = await frappe.call({
		method: "connect_diagnostics_core.api.erpnext.customer_demo.get_customer_demo_asset_movement_draft",
		args: { material_request: frm.doc.name },
	});
	const data = message?.data;
	if (!data) return;
	if (data.existing_asset_movement) {
		await frappe.set_route("Form", "Asset Movement", data.existing_asset_movement);
		return;
	}
	const movement = await create_asset_movement_doc(data);
	await frappe.set_route("Form", "Asset Movement", movement.name);
}

function open_customer_demo_return(frm) {
	frappe.prompt(
		[
			{
				fieldtype: "Link",
				fieldname: "asset",
				label: __("Asset to Return"),
				options: "Asset",
				reqd: 1,
				get_query: () => ({
					filters: {
						company: frm.doc.company,
						location: frm.doc.demo_target_location,
						docstatus: 1,
						status: [
							"not in",
							["Draft", "Scrapped", "Sold", "Capitalized", "In Maintenance", "Out of Order"],
						],
					},
				}),
			},
		],
		async (values) => {
			const { message } = await frappe.call({
				method: "connect_diagnostics_core.api.erpnext.customer_demo.get_customer_demo_return_movement_draft",
				args: { material_request: frm.doc.name, assets: JSON.stringify([values.asset]) },
			});
			const movement = await create_asset_movement_doc(message.data);
			await frappe.set_route("Form", "Asset Movement", movement.name);
		},
		__("Return Customer Demo Asset"),
		__("Create Movement"),
	);
}

function sync_asset_target_location(frm) {
	if (frm.doc.docstatus !== 0) return;

	for (const row of frm.doc.asset_transfer_assets || []) {
		if (row.target_location !== frm.doc.asset_target_location) {
			frappe.model.set_value(row.doctype, row.name, "target_location", frm.doc.asset_target_location);
		}
	}
}

function refresh_asset_transfer_ui(frm) {
	const is_asset_transfer = frm.doc.material_request_type === "Asset Transfer";
	const stock_fields = [
		"auto_created_via_reorder",
		"buying_price_list",
		"items_section",
		"items",
		"last_scanned_warehouse",
		"per_ordered",
		"per_received",
		"scan_barcode",
		"set_from_warehouse",
		"set_warehouse",
		"status_section",
		"transfer_status",
		"warehouse_section",
		"job_card",
		"work_order",
	];
	const asset_fields = [
		"asset_transfer_section",
		"asset_source_location",
		"asset_target_location",
		"asset_transfer_assets",
	];

	frm.toggle_display(stock_fields, !is_asset_transfer);
	frm.toggle_display(asset_fields, is_asset_transfer);
	frm.toggle_reqd("items", !is_asset_transfer);
	frm.toggle_reqd("asset_source_location", is_asset_transfer);
	frm.toggle_reqd("asset_target_location", is_asset_transfer);
	frm.toggle_reqd("asset_transfer_assets", is_asset_transfer);

	if (is_asset_transfer) {
		frm.remove_custom_button(__("Bill of Materials"), __("Get Items From"));
		frm.remove_custom_button(__("Sales Order"), __("Get Items From"));
		frm.remove_custom_button(__("Stop"));
		frm.remove_custom_button(__("Re-open"));
		frm.remove_custom_button(__("Pick List"), __("Create"));
	}
}

async function open_asset_movement(frm) {
	const response = await frappe.call({
		method: "connect_diagnostics_core.api.erpnext.material_request_asset_transfer.get_asset_movement_draft",
		args: { material_request: frm.doc.name },
	});
	const data = response.message?.data;
	if (!data) return;

	if (data.existing_asset_movement) {
		await frappe.set_route("Form", "Asset Movement", data.existing_asset_movement);
		return;
	}

	const movement = await create_asset_movement_doc(data);
	await frappe.set_route("Form", "Asset Movement", movement.name);
}

async function create_asset_movement_doc(data) {
	await frappe.model.with_doctype("Asset Movement");
	const movement = frappe.model.get_new_doc("Asset Movement");
	movement.company = data.company;
	movement.purpose = data.purpose;
	if (data.reference_name) {
		movement.reference_doctype = "Material Request";
		movement.reference_name = data.reference_name;
	}
	if (data.demo_return_for_material_request) {
		movement.demo_return_for_material_request = data.demo_return_for_material_request;
	}

	for (const asset of data.assets || []) {
		const row = frappe.model.add_child(movement, "assets");
		row.asset = asset.asset;
		row.asset_name = asset.asset_name;
		row.source_location = asset.source_location;
		row.from_employee = asset.from_employee;
		row.target_location = asset.target_location;
		row.to_employee = asset.to_employee;
		row.department = asset.department;
		row.territory = asset.territory;
	}

	return movement;
}

frappe.ui.form.on("Material Request Asset Transfer Item", {
	async asset(frm, cdt, cdn) {
		const assetName = locals[cdt][cdn].asset;
		if (!assetName) return;

		await frappe.model.set_value(cdt, cdn, "target_location", frm.doc.asset_target_location || "");
		const { message } = await frappe.db.get_value("Asset", assetName, "custodian");
		if (locals[cdt][cdn].asset !== assetName) return;
		await frappe.model.set_value(cdt, cdn, "to_employee", message?.custodian || "");
	},
});
