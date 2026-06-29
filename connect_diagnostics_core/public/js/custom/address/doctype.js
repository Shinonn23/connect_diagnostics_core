// Copyright (c) 2026, Siwat Sroisuwan and contributors
// For license information, please see license.txt

frappe.ui.form.on("Address", {
	validate(frm) {
		if (frm.skip_party_tax_mismatch_check) {
			frm.skip_party_tax_mismatch_check = false;
			return;
		}

		if (!frm.events.should_check_party_tax_mismatch(frm)) {
			return;
		}

		frappe.validated = false;
		frm.events.confirm_party_tax_mismatch_before_save(frm);
	},

	refresh(frm) {
		if (frm.doc.__islocal) {
			return;
		}

		frm.add_custom_button(
			__("Get Tax From Linked Party"),
			() => frm.events.get_tax_from_linked_party(frm),
			__("Get Address"),
		);
	},

	should_check_party_tax_mismatch(frm) {
		const party_links = (frm.doc.links || []).filter((link) =>
			["Customer", "Supplier"].includes(link.link_doctype),
		);
		return party_links.length && (frm.doc.tax_id || frm.doc.branch_code);
	},

	confirm_party_tax_mismatch_before_save(frm) {
		frappe.call({
			method: "connect_diagnostics_core.utils.address.get_party_tax_mismatches_for_links",
			args: {
				links: frm.doc.links || [],
				tax_id: frm.doc.tax_id || "",
				branch_code: frm.doc.branch_code || "",
			},
			callback(r) {
				const mismatches = r.message || [];
				if (!mismatches.length) {
					frm.skip_party_tax_mismatch_check = true;
					frm.save();
					return;
				}

				frm.events.show_party_tax_mismatch_dialog(frm, mismatches);
			},
		});
	},

	show_party_tax_mismatch_dialog(frm, mismatches) {
		const rows = mismatches.map((mismatch) => {
			const details = [
				mismatch.address_tax_id !== mismatch.party_tax_id
					? __("Tax ID: Address {0}, linked party {1}", [
						mismatch.address_tax_id || __("blank"),
						mismatch.party_tax_id || __("blank"),
					])
					: null,
				mismatch.address_branch_code !== mismatch.party_branch_code
					? __("Branch: Address {0}, linked party {1}", [
						mismatch.address_branch_code || __("blank"),
						mismatch.party_branch_code || __("blank"),
					])
					: null,
			]
				.filter(Boolean)
				.join("<br>");

			return `<li><strong>${frappe.utils.escape_html(mismatch.label)}</strong><br>${details}</li>`;
		});

		const dialog = new frappe.ui.Dialog({
			title: __("Tax Details Do Not Match Linked Party"),
			fields: [
				{
					fieldtype: "HTML",
					fieldname: "message",
					options:
						__(
							"The Address tax details do not match one or more linked Customer/Supplier records.",
						) + `<ul>${rows.join("")}</ul>`,
				},
			],
			primary_action_label: __("Save Anyway"),
			primary_action() {
				dialog.hide();
				frm.skip_party_tax_mismatch_check = true;
				frm.save();
			},
			secondary_action_label: __("Cancel"),
			secondary_action() {
				dialog.hide();
			},
		});

		dialog.show();
	},

	get_tax_from_linked_party(frm) {
		frappe.call({
			method: "connect_diagnostics_core.utils.address.get_linked_party_tax_candidates",
			args: {
				address_name: frm.doc.name,
			},
			callback(r) {
				const candidates = r.message || [];
				if (!candidates.length) {
					frappe.msgprint(__("No linked Customer or Supplier with tax details was found."));
					return;
				}

				if (candidates.length === 1) {
					frm.events.set_party_tax_values(frm, candidates[0]);
					return;
				}

				frm.events.prompt_party_tax_source(frm, candidates);
			},
		});
	},

	prompt_party_tax_source(frm, candidates) {
		const options = candidates.map((candidate, index) => ({
			label: [
				candidate.label,
				candidate.tax_id ? __("Tax ID: {0}", [candidate.tax_id]) : null,
				candidate.branch_code ? __("Branch: {0}", [candidate.branch_code]) : null,
			]
				.filter(Boolean)
				.join(" | "),
			value: String(index),
		}));

		frappe.prompt(
			[
				{
					fieldtype: "Select",
					fieldname: "source",
					label: __("Source"),
					options,
					reqd: 1,
				},
			],
			(values) => {
				frm.events.set_party_tax_values(frm, candidates[Number(values.source)]);
			},
			__("Select Tax Source"),
			__("Use"),
		);
	},

	set_party_tax_values(frm, candidate) {
		frm.set_value("tax_id", candidate.tax_id || "");
		frm.set_value("branch_code", candidate.branch_code || "");
		frm.refresh_field("tax_id");
		frm.refresh_field("branch_code");
		frappe.show_alert({
			message: __("Tax details copied from {0}. Save the Address to keep the changes.", [
				candidate.label,
			]),
			indicator: "green",
		});
	},
});
