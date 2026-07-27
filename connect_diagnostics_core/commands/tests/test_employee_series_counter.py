from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import Mock, patch

from click.testing import CliRunner
from frappe.tests import UnitTestCase

from connect_diagnostics_core.commands.employee_series_counter import (
    EmployeeSeriesCounterResult,
    _get_employee_counter,
    sync_employee_series_counters,
    sync_employee_series_counters_command,
)


class TestEmployeeSeriesCounterCommand(UnitTestCase):
    def test_get_employee_counter_uses_suffix_length_from_naming_series(self) -> None:
        self.assertEqual(_get_employee_counter("6807009", "YY-BE.MM.###"), ("6807", 9))
        self.assertEqual(_get_employee_counter("C6807009", "C.YY-BE.MM.###"), ("C6807", 9))
        self.assertIsNone(_get_employee_counter("EMP-09", "YY-BE.MM.###"))

    @patch("connect_diagnostics_core.commands.employee_series_counter.frappe")
    def test_preview_reports_stale_counter_without_writing(self, frappe: Mock) -> None:
        frappe.get_all.return_value = [
            SimpleNamespace(name="6807009", naming_series="YY-BE.MM.###"),
            SimpleNamespace(name="6807004", naming_series="YY-BE.MM.###"),
        ]
        frappe.db.get_value.return_value = 4

        results = sync_employee_series_counters(apply=False)

        self.assertEqual(
            results,
            [
                EmployeeSeriesCounterResult(
                    prefix="6807",
                    employee_count=2,
                    highest_counter=9,
                    current_counter=4,
                    action="would-update",
                )
            ],
        )
        frappe.db.set_value.assert_not_called()
        frappe.get_doc.assert_not_called()
        frappe.db.get_value.assert_called_once_with(
            "Series", "6807", "current", order_by="name", for_update=False
        )

    @patch("connect_diagnostics_core.commands.employee_series_counter.frappe")
    def test_apply_updates_only_counter_below_highest_employee_number(self, frappe: Mock) -> None:
        frappe.get_all.return_value = [
            SimpleNamespace(name="C6807009", naming_series="C.YY-BE.MM.###"),
            SimpleNamespace(name="6807011", naming_series="YY-BE.MM.###"),
        ]
        frappe.db.get_value.side_effect = [12, 4]

        results = sync_employee_series_counters(apply=True)

        self.assertEqual([result.action for result in results], ["unchanged", "updated"])
        self.assertEqual(frappe.db.sql.call_count, 1)
        self.assertIn("GREATEST(`current`, VALUES(`current`))", frappe.db.sql.call_args.args[0])
        self.assertEqual(frappe.db.sql.call_args.args[1], ("C6807", 9))

    @patch("connect_diagnostics_core.commands.employee_series_counter.frappe")
    def test_force_can_lower_counter_to_highest_employee_number(self, frappe: Mock) -> None:
        frappe.get_all.return_value = [SimpleNamespace(name="6807009", naming_series="YY-BE.MM.###")]
        frappe.db.get_value.return_value = 12

        results = sync_employee_series_counters(apply=True, force=True)

        self.assertEqual(results[0].action, "updated")
        self.assertIn("`current` = VALUES(`current`)", frappe.db.sql.call_args.args[0])
        self.assertEqual(frappe.db.sql.call_args.args[1], ("6807", 9))

    @patch("connect_diagnostics_core.commands.employee_series_counter.sync_employee_series_counters")
    @patch("connect_diagnostics_core.commands.employee_series_counter.frappe")
    def test_apply_commits_and_prints_result(self, frappe: Mock, sync: Mock) -> None:
        sync.return_value = [
            EmployeeSeriesCounterResult(
                prefix="6807", employee_count=2, highest_counter=9, current_counter=4, action="updated"
            )
        ]

        result = CliRunner().invoke(
            sync_employee_series_counters_command,
            ["--apply"],
            obj=SimpleNamespace(sites=["dev.local"], profile=False),
        )

        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn("dev.local: updated prefix=6807 highest=9 current=4 employees=2", result.output)
        frappe.db.commit.assert_called_once_with()
        frappe.destroy.assert_called_once_with()

    def test_force_requires_apply(self) -> None:
        result = CliRunner().invoke(
            sync_employee_series_counters_command,
            ["--force"],
            obj=SimpleNamespace(sites=["dev.local"], profile=False),
        )

        self.assertEqual(result.exit_code, 2)
        self.assertIn("--force requires --apply", result.output)
