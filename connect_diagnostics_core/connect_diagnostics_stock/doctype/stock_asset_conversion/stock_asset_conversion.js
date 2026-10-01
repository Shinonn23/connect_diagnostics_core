frappe.ui.form.on("Stock Asset Conversion", {
	refresh(frm) {
		if (
			frm.is_new() ||
			frm.doc.docstatus !== 0 ||
			!frm.doc.fulfillment_allocation ||
			!["Accounts Manager", "System Manager"].some((role) => frappe.user.has_role(role))
		)
			return;
		frm.add_custom_button(__("Approve Conversion Preview"), () => {
			frm.save().then(() =>
				frappe
					.call({
						method: "connect_diagnostics_core.api.erpnext.stock_asset_conversion.approve_preview",
						args: { conversion: frm.doc.name },
						freeze: true,
					})
					.then((r) => {
						if (!r.message?.data) return;
						const facts = r.message.data.facts;
						frappe.msgprint({
							title: __("Conversion Preview"),
							message: __(
								"Stock value: {0}<br>Recommended treatment: {1}<br>Conversion GL: {2}",
								[
									format_currency(facts.stock_value),
									facts.recommendation,
									facts.general_ledger
										.map(
											(row) =>
												`${frappe.utils.escape_html(row.account)}: ${format_currency(row.debit || row.credit)}`,
										)
										.join("<br>"),
								],
							),
						});
						frm.reload_doc();
					}),
			);
		});
	},
});
