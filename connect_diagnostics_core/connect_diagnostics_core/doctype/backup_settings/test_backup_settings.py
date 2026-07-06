# Copyright (c) 2026, Siwat Sroisuwan and Contributors
# See license.txt

from __future__ import annotations

import os
from datetime import date, datetime

import frappe
from frappe.tests import IntegrationTestCase, UnitTestCase

from connect_diagnostics_core.utils.gcs_backup import (
    buckets_due,
    files_to_upload,
    object_name_for_path,
    site_slug,
)

NOW = datetime(2026, 7, 7, 12, 0, 0)


class UnitTestBackupRetention(UnitTestCase):
    """Pure-logic tests for tier selection, key building and the additive mirror."""

    def test_frequent_bucket_always_due(self):
        due = buckets_due(NOW, "freq", None, None, None, None)
        self.assertEqual(due, {"frequent": "freq"})

    def test_daily_due_when_not_uploaded_today(self):
        due = buckets_due(NOW, "freq", "day", None, date(2026, 7, 6), None)
        self.assertEqual(due["daily"], "day")

    def test_daily_skipped_when_already_uploaded_today(self):
        due = buckets_due(NOW, "freq", "day", None, date(2026, 7, 7), None)
        self.assertNotIn("daily", due)

    def test_monthly_due_when_not_uploaded_this_month(self):
        due = buckets_due(NOW, "freq", None, "mon", None, "2026-06")
        self.assertEqual(due["monthly"], "mon")

    def test_monthly_skipped_when_already_uploaded_this_month(self):
        due = buckets_due(NOW, "freq", None, "mon", None, "2026-07")
        self.assertNotIn("monthly", due)

    def test_unconfigured_buckets_are_never_due(self):
        self.assertEqual(buckets_due(NOW, None, None, None, None, None), {})

    def test_all_tiers_due_on_first_run_of_month(self):
        due = buckets_due(NOW, "freq", "day", "mon", None, None)
        self.assertEqual(set(due), {"frequent", "daily", "monthly"})

    def test_site_slug_replaces_dots(self):
        self.assertEqual(site_slug("uat.erp.connectdiagnostics.net"), "uat_erp_connectdiagnostics_net")

    def test_object_name_maps_public_and_private(self):
        roots = {"site_net/public": "/sites/x/public/files", "site_net/private": "/sites/x/private/files"}
        self.assertEqual(
            object_name_for_path("/sites/x/public/files/a/b.png", roots),
            "site_net/public/a/b.png",
        )
        self.assertEqual(
            object_name_for_path(os.path.join("/sites/x/private/files", "c.pdf"), roots),
            "site_net/private/c.pdf",
        )

    def test_object_name_outside_roots_is_none(self):
        roots = {"site_net/public": "/sites/x/public/files"}
        self.assertIsNone(object_name_for_path("/etc/passwd", roots))

    def test_mirror_uploads_new_and_changed_only(self):
        local = {"a.png": "h1", "b.png": "h2", "c.png": "h3"}
        remote = {"a.png": "h1", "b.png": "OLD"}
        # a unchanged -> skip; b changed -> upload; c new -> upload.
        self.assertEqual(files_to_upload(local, remote), ["b.png", "c.png"])

    def test_mirror_never_deletes_remote_only_files(self):
        local = {"a.png": "h1"}
        remote = {"a.png": "h1", "gone.png": "h9"}
        # gone.png exists only remotely: an additive mirror must leave it alone.
        self.assertEqual(files_to_upload(local, remote), [])

    def test_force_uploads_every_local_file(self):
        local = {"a.png": "h1", "b.png": "h2"}
        remote = {"a.png": "h1", "b.png": "h2"}
        # Even when nothing changed, force re-uploads all local files.
        self.assertEqual(files_to_upload(local, remote, force=True), ["a.png", "b.png"])


class IntegrationTestBackupSettings(IntegrationTestCase):
    """Validation tests against the Single Backup Settings document."""

    def test_enabled_requires_frequent_bucket(self):
        settings = frappe.get_single("Backup Settings")
        settings.enabled = 1
        settings.frequent_bucket = None
        settings.backup_interval_hours = 6
        with self.assertRaises(frappe.ValidationError):
            settings.validate()

    def test_interval_must_be_positive(self):
        settings = frappe.get_single("Backup Settings")
        settings.enabled = 1
        settings.frequent_bucket = "freq"
        settings.backup_interval_hours = 0
        with self.assertRaises(frappe.ValidationError):
            settings.validate()

    def test_disabled_skips_validation(self):
        settings = frappe.get_single("Backup Settings")
        settings.enabled = 0
        settings.frequent_bucket = None
        settings.validate()
