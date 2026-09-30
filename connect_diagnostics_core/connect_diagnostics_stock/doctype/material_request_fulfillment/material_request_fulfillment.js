frappe.ui.form.on("Material Request Fulfillment", {
	refresh(frm) {
		if (frm.is_new() || frm.doc.status !== "Planned") return;
		const accounts_access = ["Accounts User", "Accounts Manager", "System Manager"].some((role) =>
			frappe.user.has_role(role),
		);
		const sale_allocations = (frm.doc.allocations || []).filter(
			(row) => row.lifecycle_state === "Delivered" && !row.current_sales_invoice,
		);
		if (accounts_access && sale_allocations.length) {
			frm.add_custom_button(__("Create Demo Sales Invoice"), () => {
				frappe.prompt(
					[
						{
							fieldname: "allocation",
							fieldtype: "Select",
							label: __("Delivered Allocation"),
							options: sale_allocations.map((row) => row.name),
							reqd: 1,
						},
						{
							fieldname: "customer",
							fieldtype: "Link",
							label: __("Customer"),
							options: "Customer",
							reqd: 1,
						},
					],
					(values) => {
						frappe
							.call({
								method: "connect_diagnostics_core.api.erpnext.sales_invoice.create_demo_sales_invoice",
								args: values,
								freeze: true,
							})
							.then((r) => {
								if (r.message?.data)
									frappe.set_route("Form", "Sales Invoice", r.message.data);
							});
					},
					__("Create Demo Sales Invoice"),
				);
			});
		}
		if (!["Stock User", "Stock Manager", "System Manager"].some((role) => frappe.user.has_role(role)))
			return;
		[
			["Use Available Assets", "use_available_assets"],
			["Wait for Returning Assets", "wait_for_returning_assets"],
			["Use Stock Now", "use_stock_now"],
		].forEach(([label, method]) => {
			frm.add_custom_button(__(label), () => {
				frappe
					.call({
						method: `connect_diagnostics_core.api.erpnext.material_request_fulfillment.${method}`,
						args: { fulfillment: frm.doc.name },
						freeze: true,
					})
					.then((r) => {
						if (r.message && r.message.data)
							frappe.set_route("Form", "Material Request Fulfillment", r.message.data);
					});
			});
		});
		frm.add_custom_button(__("Create Stock Conversion Draft"), () => {
			const row = (frm.doc.allocations || []).find(
				(item) => item.source_type === "Stock Conversion" && !item.conversion_state,
			);
			if (!row) return frappe.msgprint(__("No active Stock Conversion allocation is available."));
			frappe.prompt(
				{
					fieldname: "warehouse",
					fieldtype: "Link",
					label: __("Source Warehouse"),
					options: "Warehouse",
					reqd: 1,
				},
				(values) => {
					frappe
						.call({
							method: "connect_diagnostics_core.api.erpnext.material_request_fulfillment.create_stock_asset_conversion",
							args: {
								fulfillment: frm.doc.name,
								allocation: row.name,
								warehouse: values.warehouse,
							},
							freeze: true,
						})
						.then((r) => {
							if (r.message?.data)
								frappe.set_route("Form", "Stock Asset Conversion", r.message.data);
						});
				},
			);
		});
		frm.add_custom_button(__("Prepare Outbound Asset Movement"), () => {
			frappe
				.call({
					method: "connect_diagnostics_core.api.erpnext.material_request_fulfillment.prepare_demo_outbound_movement",
					args: { fulfillment: frm.doc.name },
					freeze: true,
				})
				.then((r) => {
					if (r.message?.data) frappe.set_route("Form", "Asset Movement", r.message.data);
				});
		});
		frm.add_custom_button(__("Prepare Outbound Dispatch"), () => {
			frappe.prompt(
				{
					fieldname: "delivery_address",
					fieldtype: "Small Text",
					label: __("Delivery Address"),
					reqd: 1,
				},
				(values) => {
					frappe
						.call({
							method: "connect_diagnostics_core.api.erpnext.material_request_fulfillment.prepare_demo_outbound_dispatch",
							args: {
								fulfillment: frm.doc.name,
								delivery_address: values.delivery_address,
							},
							freeze: true,
						})
						.then((r) => {
							if (r.message?.data) frappe.set_route("Form", "Dispatch", r.message.data);
						});
				},
				__("Prepare Outbound Dispatch"),
			);
		});
		frm.add_custom_button(__("Release Asset Reservation"), () => {
			frappe.prompt(
				{
					fieldname: "reservation",
					fieldtype: "Link",
					label: __("Reservation"),
					options: "Demo Asset Reservation",
					reqd: 1,
					get_query: () => ({ filters: { status: "Active" } }),
				},
				(values) => {
					frappe
						.call({
							method: "connect_diagnostics_core.api.erpnext.material_request_fulfillment.release_asset_reservation",
							args: { fulfillment: frm.doc.name, reservation: values.reservation },
							freeze: true,
						})
						.then((r) => {
							if (r.message?.data)
								frappe.set_route("Form", "Material Request Fulfillment", r.message.data);
						});
				},
				__("Release Asset Reservation"),
			);
		});
	},
});
