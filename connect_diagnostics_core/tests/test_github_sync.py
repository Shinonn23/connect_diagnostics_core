# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from unittest import TestCase
from unittest.mock import Mock, patch

from connect_diagnostics_core import github_sync


class TestGitHubSync(TestCase):
    def test_toggle_uses_default_when_setting_field_is_missing(self):
        settings = Mock()
        settings.get.return_value = None

        with patch.object(github_sync, "_settings", return_value=settings):
            self.assertTrue(github_sync._toggle("pull_enabled", True))
            self.assertFalse(github_sync._toggle("pull_enabled", False))

    def test_count_outcome_groups_created_updated_skipped_and_failed(self):
        stats = github_sync._empty_sync_stats()

        for outcome in ("created", "updated", "status_updated", "skipped_no_ticket", "failed"):
            github_sync._count_outcome(stats, outcome)

        self.assertEqual(stats["created_count"], 1)
        self.assertEqual(stats["updated_count"], 2)
        self.assertEqual(stats["skipped_count"], 1)
        self.assertEqual(stats["error_count"], 1)

    def test_missing_ticket_template_fields_reports_fields_not_in_default_template(self):
        frappe_mock = Mock()
        frappe_mock.db.exists.return_value = True
        frappe_mock.get_all.return_value = ["sync_to_github"]

        with (
            patch.object(github_sync, "_doctype_exists", return_value=True),
            patch.object(github_sync, "frappe", frappe_mock),
        ):
            missing = github_sync.missing_ticket_template_fields()

        self.assertEqual(missing, ["github_issue_number", "github_url", "github_last_synced"])

    def test_apply_issue_skips_when_no_linked_ticket(self):
        """Pull is update-only: an issue with no linked ticket is never turned into one."""
        issue = {"number": 99, "state": "open"}

        with patch.object(github_sync, "_ticket_for_issue", return_value=None):
            result = github_sync._apply_issue(issue, {})

        self.assertEqual(result["outcome"], "skipped_no_ticket")
        self.assertEqual(result["issue_number"], 99)

    def test_apply_issue_skips_linked_ticket_when_sync_is_off(self):
        issue = {"number": 42, "state": "open"}

        def get_value(doctype, name, fieldname=None, **kwargs):
            if doctype == "HD Ticket" and fieldname == "sync_to_github":
                return 0
            return None

        frappe_mock = Mock()
        frappe_mock.db.get_value.side_effect = get_value

        with (
            patch.object(github_sync, "_ticket_for_issue", return_value="HD-0001"),
            patch.object(github_sync, "frappe", frappe_mock),
        ):
            result = github_sync._apply_issue(issue, {})

        self.assertEqual(result["outcome"], "skipped_opt_out")
        self.assertEqual(result["ticket"], "HD-0001")
        self.assertEqual(result["issue_number"], 42)

    def test_reconcile_resolves_closed_issue_regardless_of_column(self):
        """A closed issue resolves its ticket even if the card sits in an active column."""
        board = {7: {"state": "CLOSED", "status": "DEV Ready", "item_id": "I7"}}

        frappe_mock = Mock()
        frappe_mock.db.get_value.return_value = Mock(status="Open", sync_to_github=1)

        with (
            patch.object(github_sync, "_ticket_for_issue", return_value="HD-0007"),
            patch.object(github_sync, "_resolved_status", return_value="Resolved"),
            patch.object(github_sync, "_status_category", return_value="Resolved"),
            patch.object(github_sync, "ensure_board_status"),
            patch.object(github_sync, "frappe", frappe_mock),
        ):
            result = github_sync._reconcile_board_status(board)

        self.assertEqual(result["counts"].get("status_updated"), 1)
        self.assertEqual(result["details"][0]["to"], "Resolved")

    def test_import_from_github_dry_run_counts_unlinked_non_pr_only(self):
        """Bootstrap dry-run: counts issues that would be created (unlinked, non-PR)."""
        page = [
            {"number": 1, "state": "open"},
            {"number": 2, "state": "open"},
            {"number": 3, "state": "open", "pull_request": {"url": "https://api.github/pr/3"}},
        ]
        rest_pages = [page, []]

        def fake_rest(method, path, params=None, json=None):
            return rest_pages.pop(0) if rest_pages else []

        def fake_ticket_for_issue(n):
            return "HD-0002" if n == 2 else None

        with (
            patch.object(github_sync, "_has_auth", return_value=True),
            patch.object(github_sync, "_owner_repo", return_value=("o", "r")),
            patch.object(github_sync, "fetch_board", return_value={}),
            patch.object(github_sync, "_rest", side_effect=fake_rest),
            patch.object(github_sync, "_ticket_for_issue", side_effect=fake_ticket_for_issue),
            patch.object(github_sync, "frappe", Mock()),
        ):
            res = github_sync.import_from_github(commit=False)

        self.assertFalse(res["commit"])
        self.assertEqual(res["created"], 1)  # #1 only: #2 already linked, #3 is a PR
        self.assertEqual(res["skipped"], 1)  # #2
        self.assertEqual(res["errors"], 0)

    def test_rehost_noop_when_no_github_images(self):
        html = "<p>no images here</p>"
        out, count = github_sync._rehost_github_images(html, "HD-0001")
        self.assertEqual(out, html)
        self.assertEqual(count, 0)

    def test_rehost_reuses_existing_file_without_redownloading(self):
        html = '<p><img alt="x" src="https://github.com/user-attachments/assets/abc-123"></p>'
        frappe_mock = Mock()
        frappe_mock.db.get_value.return_value = "/private/files/gh-abc-123.png"

        with (
            patch.object(github_sync, "frappe", frappe_mock),
            patch.object(github_sync, "_download_github_asset") as download,
        ):
            out, count = github_sync._rehost_github_images(html, "HD-0001")

        self.assertIn("/private/files/gh-abc-123.png", out)
        self.assertNotIn("user-attachments", out)
        self.assertEqual(count, 0)  # reused an existing File, nothing newly hosted
        download.assert_not_called()

    def test_reconcile_skips_frozen_ticket(self):
        """A ticket with Sync to GitHub off is never realigned by the board reconcile."""
        board = {8: {"state": "OPEN", "status": "Dev review", "item_id": "I8"}}

        frappe_mock = Mock()
        frappe_mock.db.get_value.return_value = Mock(status="Open", sync_to_github=0)

        with (
            patch.object(github_sync, "_ticket_for_issue", return_value="HD-0008"),
            patch.object(github_sync, "_status_category", return_value="Open"),
            patch.object(github_sync, "ensure_board_status"),
            patch.object(github_sync, "frappe", frappe_mock),
        ):
            result = github_sync._reconcile_board_status(board)

        self.assertEqual(result["counts"], {})
        frappe_mock.db.set_value.assert_not_called()
