// Copyright (c) 2026, Siwat Sroisuwan and contributors
// For license information, please see license.txt

frappe.ui.form.on("Delivery Note", {
	refresh(frm) {
		frm.set_query("item_code", "items", function (doc, cdt, cdn) {
			const row = frappe.get_doc(cdt, cdn);
			return {
				query: "connect_diagnostics_core.api.erpnext.item.get_item_with_stock",
				filters: { warehouse: row.warehouse || "" },
			};
		});

		render_serial_no_summary(frm);
	},
});

function render_serial_no_summary(frm) {
	const field = frm.get_field("cd_serial_no_summary");
	if (!field) {
		return;
	}

	if (frm.is_new()) {
		set_summary_text(
			field,
			__("Save the document to see the serial number summary.")
		);
		return;
	}

	frappe.call({
		method: "connect_diagnostics_core.api.erpnext.delivery_note.get_serial_no_summary",
		args: { delivery_note: frm.doc.name },
		callback(r) {
			set_summary_text(field, build_summary_text(r.message || []));
		},
	});
}

function build_summary_text(items) {
	if (!items.length) {
		return __("No serial-tracked items.");
	}

	const blocks = items.map((item) => {
		const serial_nos = item.serial_nos || [];
		const count = serial_nos.length;
		const qty = flt(item.qty);

		const header = `${item.item_code} — ${
			item.item_name || ""
		}  (${count})`;
		const lines = count
			? serial_nos.map((sn) => `    ${sn}`)
			: [`    ${__("No serial no")}`];

		return [header, ...lines].join("\n");
	});

	return blocks.join("\n\n");
}

// Render plain text into the HTML field using DOM APIs (no HTML markup authored);
// `white-space: pre-wrap` preserves the line breaks / indentation.
function set_summary_text(field, text) {
	const $wrapper = field.$wrapper;
	$wrapper.empty();

	const block = document.createElement("div");
	block.style.whiteSpace = "pre-wrap";
	block.textContent = text;
	$wrapper.append(block);
}
