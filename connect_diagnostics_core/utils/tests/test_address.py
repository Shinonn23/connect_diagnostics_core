from __future__ import annotations

from unittest import TestCase
from unittest.mock import Mock, patch

from frappe import _dict

from connect_diagnostics_core.utils.address import (
    _ensure_rendered_address,
    _refresh_linked_address_display,
    get_display_field,
    refresh_address_display_values,
    validate_refresh_address_display_selectors,
)


class TestGetDisplayField(TestCase):
    def test_uses_known_field_mapping(self) -> None:
        meta = Mock()
        meta.get_field.side_effect = lambda fieldname: fieldname == "address_display"

        self.assertEqual(get_display_field(meta, "customer_address"), "address_display")

    def test_uses_name_suffix_fallback(self) -> None:
        meta = Mock()
        meta.get_field.side_effect = lambda fieldname: fieldname == "custom_shipping_address"

        self.assertEqual(get_display_field(meta, "custom_shipping_address_name"), "custom_shipping_address")


class TestValidateSelectors(TestCase):
    def test_requires_explicit_scope(self) -> None:
        with self.assertRaisesRegex(ValueError, "--all, --doctype, or --address"):
            validate_refresh_address_display_selectors(all=False, doctypes=(), names=(), addresses=())

    def test_name_requires_exactly_one_doctype(self) -> None:
        with self.assertRaisesRegex(ValueError, "exactly one --doctype"):
            validate_refresh_address_display_selectors(
                all=False,
                doctypes=("Sales Invoice", "Delivery Note"),
                names=("SINV-0001",),
                addresses=(),
            )

    def test_all_cannot_be_combined_with_other_selectors(self) -> None:
        with self.assertRaisesRegex(ValueError, "--all cannot be combined"):
            validate_refresh_address_display_selectors(
                all=True,
                doctypes=(),
                names=(),
                addresses=("Customer-Billing",),
            )


class TestRefreshLinkedAddressDisplay(TestCase):
    @patch("connect_diagnostics_core.utils.address.frappe")
    def test_preview_counts_without_writing(self, frappe: Mock) -> None:
        frappe.get_all.return_value = [
            _dict(name="SINV-0001", customer_address="Customer-Billing", address_display="Old"),
            _dict(name="SINV-0002", customer_address="Customer-Billing", address_display="New"),
            _dict(name="SINV-0003", customer_address="Missing-Billing", address_display="Old"),
        ]

        result = _refresh_linked_address_display(
            "Sales Invoice",
            "customer_address",
            "address_display",
            {"Customer-Billing": "New"},
            names=("SINV-0001", "SINV-0002", "SINV-0003"),
            addresses=(),
            apply=False,
        )

        self.assertEqual((result.changed, result.unchanged, result.dangling), (1, 1, 1))
        frappe.db.set_value.assert_not_called()

    @patch("connect_diagnostics_core.utils.address.frappe")
    def test_apply_writes_only_changed_snapshot_without_touching_modified(self, frappe: Mock) -> None:
        frappe.get_all.return_value = [
            _dict(name="SINV-0001", customer_address="Customer-Billing", address_display="Old"),
            _dict(name="SINV-0002", customer_address="Customer-Billing", address_display="New"),
        ]

        result = _refresh_linked_address_display(
            "Sales Invoice",
            "customer_address",
            "address_display",
            {"Customer-Billing": "New"},
            names=(),
            addresses=("Customer-Billing",),
            apply=True,
        )

        self.assertEqual((result.changed, result.unchanged, result.dangling), (1, 1, 0))
        frappe.db.set_value.assert_called_once_with(
            "Sales Invoice",
            "SINV-0001",
            "address_display",
            "New",
            update_modified=False,
        )
        frappe.get_all.assert_called_once_with(
            "Sales Invoice",
            filters={"customer_address": ("in", ("Customer-Billing",))},
            fields=["name", "customer_address", "address_display"],
            order_by=None,
        )

    @patch("connect_diagnostics_core.utils.address.render_address", return_value="Rendered")
    @patch("connect_diagnostics_core.utils.address.frappe")
    def test_lazy_render_loads_linked_address_only_when_needed(
        self, frappe: Mock, render_address: Mock
    ) -> None:
        frappe.db.exists.return_value = True
        rendered_addresses = {}

        self.assertTrue(
            _ensure_rendered_address(
                "Customer-Billing",
                rendered_addresses,
                lazy_render=True,
            )
        )
        self.assertEqual(rendered_addresses, {"Customer-Billing": "Rendered"})
        render_address.assert_called_once_with("Customer-Billing", check_permissions=False)


class TestRefreshAddressDisplayValues(TestCase):
    @patch("connect_diagnostics_core.utils.address._get_selected_doctypes", return_value=())
    @patch("connect_diagnostics_core.utils.address._refresh_party_primary_addresses")
    @patch("connect_diagnostics_core.utils.address._render_addresses", return_value={})
    def test_include_party_primary_renders_all_addresses(
        self,
        render_addresses: Mock,
        refresh_party_primary_addresses: Mock,
        _get_selected_doctypes: Mock,
    ) -> None:
        refresh_party_primary_addresses.return_value = Mock(changed=0, unchanged=0, dangling=0)

        refresh_address_display_values(
            addresses=("Customer-Billing",),
            include_party_primary=True,
        )

        render_addresses.assert_called_once_with(None)
        refresh_party_primary_addresses.assert_called_once_with({}, apply=False)
