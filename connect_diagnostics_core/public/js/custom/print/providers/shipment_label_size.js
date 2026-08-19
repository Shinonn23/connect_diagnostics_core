// Copyright (c) 2026, Siwat Sroisuwan and contributors
// For license information, please see license.txt

// Print sidebar provider: Shipment Label Size.
//
// Offers the paper size only while the Shipment Box Label is the selected
// format, so other Shipment formats keep an uncluttered sidebar. The format's
// Jinja reads `print_settings.custom_shipment_label_size`.

(() => {
	const SHIPMENT_DOCTYPE = "Shipment";
	const SHIPMENT_LABEL_FORMAT = "Shipment Box Label";
	const SIZE_OPTIONS = ["75 x 100 mm", "100 x 180 mm"];

	frappe.provide("connect_diagnostics.print").register({
		name: "shipment_label_size",
		applies_to: (view) =>
			view.frm.doc.doctype === SHIPMENT_DOCTYPE && view.selected_format() === SHIPMENT_LABEL_FORMAT,
		build: () => [
			{
				fieldname: "custom_shipment_label_size",
				label: __("Shipment Label Size"),
				fieldtype: "Select",
				options: SIZE_OPTIONS.join("\n"),
				default: SIZE_OPTIONS[0],
			},
		],
	});
})();
