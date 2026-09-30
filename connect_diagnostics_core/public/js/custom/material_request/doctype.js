// Copyright (c) 2026, Siwat Sroisuwan and contributors
// For license information, please see license.txt

frappe.ui.form.on("Material Request", {
	setup(frm) {
		frm.set_query("destination_address", () => ({
			filters: [["Dynamic Link", "link_name", "=", frm.doc.destination_customer]],
		}));
		frm.set_query("allocated_asset", "items", (doc, cdt, cdn) => {
			const row = locals[cdt][cdn];
			return {
				filters: {
					company: doc.company,
					item_code: row.item_code,
					docstatus: 1,
					status: [
						"not in",
						["Cancelled", "Sold", "Scrapped", "Capitalized", "In Maintenance", "Out of Order"],
					],
				},
			};
		});
	},
	refresh(frm) {
		if (can_manage_fulfillment(frm)) {
			frm.add_custom_button(__("Refresh Unit Cost"), () => refresh_unit_cost(frm), __("Fulfillment"));
		}
		if (can_prepare_transit(frm)) {
			frm.add_custom_button(
				__("Prepare Outward Transit"),
				() => prepare_outward_transit(frm),
				__("Fulfillment"),
			);
		}
		refresh_route_options(frm);
	},
	onload_post_render(frm) {
		install_demo_item_query(frm);
		refresh_demo_eligible_items(frm);
	},
	company(frm) {
		refresh_demo_eligible_items(frm);
	},
	request_usage(frm) {
		refresh_route_options(frm);
		refresh_demo_eligible_items(frm);
	},
	validate(frm) {
		validate_schedule_date(frm);
	},
});

function install_demo_item_query(frm) {
	const field = frm.fields_dict.items?.grid?.get_field("item_code");
	if (!field) return;

	if (!frm.__native_material_request_item_query) {
		frm.__native_material_request_item_query = field.get_query;
	}
	if (!frm.__native_material_request_item_query || field.get_query === frm.__demo_item_query) return;

	frm.__demo_item_query = (doc, cdt, cdn) =>
		build_demo_item_query(
			frm.__native_material_request_item_query(doc, cdt, cdn),
			doc.request_usage,
			frm.__demo_eligible_items || [],
		);
	field.get_query = frm.__demo_item_query;
}

function build_demo_item_query(native_query, request_usage, eligible_items) {
	if (request_usage !== "Customer Demo") return native_query;

	return {
		...(native_query || {}),
		filters: {
			...(native_query?.filters || {}),
			name: ["in", eligible_items],
		},
	};
}

async function refresh_demo_eligible_items(frm) {
	install_demo_item_query(frm);
	frm.__demo_eligible_items = [];
	if (frm.doc.request_usage !== "Customer Demo" || !frm.doc.company) {
		frm.fields_dict.items?.grid?.refresh();
		return;
	}

	const requested_company = frm.doc.company;
	const response = await frappe.call({
		method: "connect_diagnostics_core.api.erpnext.material_request.get_demo_eligible_items",
		type: "GET",
		args: { company: requested_company },
	});
	if (frm.doc.request_usage === "Customer Demo" && frm.doc.company === requested_company) {
		frm.__demo_eligible_items = response.message?.data || [];
		frm.fields_dict.items?.grid?.refresh();
	}
}

frappe.ui.form.on("Material Request Item", {
	items_form_render(frm, cdt, cdn) {
		set_route_options(frm, locals[cdt][cdn]);
	},
	fulfillment_route(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		if (["Stock Entry", "Purchase"].includes(row.fulfillment_route) && row.allocated_asset) {
			frappe.model.set_value(cdt, cdn, "allocated_asset", null);
		}
		set_route_options(frm, row);
	},
	unit_cost_ex_vat(frm, cdt, cdn) {
		set_route_options(frm, locals[cdt][cdn]);
	},
});

function can_manage_fulfillment(frm) {
	const roles = frappe.user_roles || [];
	return (
		!frm.is_new() &&
		frm.doc.docstatus !== 2 &&
		(frappe.session.user === "Administrator" ||
			roles.includes("Accounts User") ||
			roles.includes("System Manager"))
	);
}

function refresh_unit_cost(frm) {
	const selected = (frm.get_selected().items || []).filter(Boolean);
	frappe.call({
		method: "connect_diagnostics_core.api.erpnext.material_request.refresh_unit_cost",
		type: "POST",
		freeze: true,
		freeze_message: __("Refreshing unit cost..."),
		args: {
			material_request: frm.doc.name,
			material_request_items: selected.length ? selected : null,
		},
		callback: () => frm.reload_doc(),
	});
}

function can_prepare_transit(frm) {
	const roles = frappe.user_roles || [];
	return (
		frm.doc.docstatus === 1 &&
		["Employee Borrow", "Customer Demo", "Customer Loan"].includes(frm.doc.request_usage) &&
		(frappe.session.user === "Administrator" ||
			roles.includes("Stock User") ||
			roles.includes("Stock Manager"))
	);
}

function prepare_outward_transit(frm) {
	frappe.call({
		method: "connect_diagnostics_core.api.erpnext.material_request.create_outbound_transit_stock_entry",
		type: "POST",
		freeze: true,
		freeze_message: __("Preparing outward transit..."),
		args: { material_request: frm.doc.name, company: frm.doc.company },
		callback: () => frm.reload_doc(),
	});
}

function refresh_route_options(frm) {
	(frm.doc.items || []).forEach((row) => set_route_options(frm, row));
}

function set_route_options(frm, row) {
	let options = ["", "Stock Entry", "Existing Asset", "Purchase", "Stock Capitalization"];
	if (frm.doc.request_usage === "Customer Demo") {
		options = ["", "Existing Asset"];
		if (row.cost_source) {
			options.push(Number(row.unit_cost_ex_vat || 0) > 10000 ? "Stock Capitalization" : "Stock Entry");
		}
	}
	const gridRow = frm.fields_dict.items.grid.grid_rows_by_docname[row.name];
	const field = gridRow?.on_grid_fields_dict?.fulfillment_route;
	if (field) {
		field.df.options = options.join("\n");
		field.refresh();
	}
}

function validate_schedule_date(frm) {
	if (!frm.doc.schedule_date) return;

	const today = new Date();
	const scheduleDate = new Date(frm.doc.schedule_date);

	today.setHours(0, 0, 0, 0);
	scheduleDate.setHours(0, 0, 0, 0);

	const diffDays = (scheduleDate - today) / (1000 * 60 * 60 * 24);

	if (diffDays < 0) {
		frappe.throw(frappe._("Schedule date cannot be in the past."));
	}
	if (diffDays > 180) {
		frappe.throw(frappe._("Schedule date cannot be more than 6 months in the future."));
	}
}
