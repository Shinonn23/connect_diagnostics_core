// Copyright (c) 2026, Siwat Sroisuwan and contributors
// For license information, please see license.txt

frappe.ui.form.on("Petty Cash Holder", {
	refresh(frm) {
		// Replace the Thailand buttons when this script is loaded after the native
		// controller; leave History/Enable/Disable untouched.
		frm.remove_custom_button(__("Top Up"));
		frm.remove_custom_button(__("Withdraw"));
		if (frm.is_new() || frm.doc.disabled) return;
		frm.add_custom_button(__("Top Up"), () => petty_cash_operation(frm, "topup"));
		frm.add_custom_button(__("Withdraw"), () => petty_cash_operation(frm, "withdraw"));
	},
});

function petty_cash_operation(frm, type) {
	if (frm.__petty_cash_operation_inflight) return;
	frappe.prompt(
		[
			{
				label: __("Posting Date"),
				fieldname: "posting_date",
				fieldtype: "Date",
				reqd: 1,
				default: frappe.datetime.get_today(),
			},
			{ label: __("Amount"), fieldname: "amount", fieldtype: "Float", precision: 2, reqd: 1 },
		],
		(value) => {
			if (Number(value.amount) <= 0) frappe.throw(__("Amount must be positive."));
			const operation_id = window.crypto?.randomUUID
				? window.crypto.randomUUID()
				: frappe.utils.get_random(32);
			const from_account =
				type === "topup"
					? frm.doc.cash_bank_account_for_petty_cash_top_up
					: frm.doc.petty_cash_account;
			const to_account =
				type === "topup"
					? frm.doc.petty_cash_account
					: frm.doc.cash_bank_account_for_petty_cash_withdraw;
			frm.__petty_cash_operation_inflight = true;
			frappe
				.call({
					method: "connect_diagnostics_core.api.erpnext.journal_entry_generators.create_petty_cash_journal_entry",
					args: {
						...value,
						petty_cash_holder: frm.doc.name,
						from_account,
						to_account,
						type,
						operation_id,
					},
				})
				.then((r) => {
					if (r.message?.pending_approval)
						frappe.msgprint(__("Journal Entry {0} is pending approval.", [r.message.name]));
				})
				.finally(() => {
					frm.__petty_cash_operation_inflight = false;
				});
		},
	);
}
