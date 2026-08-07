# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

from typing import cast

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import getdate, now_datetime, time_diff_in_hours
from frappe.utils.backups import new_backup

from connect_diagnostics_core.utils.gcs_backup import (
    buckets_due,
    check_bucket_access,
    mirror_files_to_bucket,
    mirror_roots,
    site_slug,
    upload_files_to_bucket,
)

logger = frappe.logger("backup", allow_site=True)


class BackupSettings(Document):
    # begin: auto-generated types
    # This code is auto-generated. Do not modify anything in this block.

    from typing import TYPE_CHECKING

    if TYPE_CHECKING:
        from frappe.types import DF

        backup_interval_hours: DF.Int
        daily_bucket: DF.Data | None
        enabled: DF.Check
        frequent_bucket: DF.Data | None
        gcs_project: DF.Data | None
        last_backup_on: DF.Datetime | None
        last_backup_status: DF.Literal["", "Success", "Failed"]
        last_daily_on: DF.Date | None
        last_error: DF.SmallText | None
        last_mirror_on: DF.Datetime | None
        last_monthly_on: DF.Data | None
        mirror_bucket: DF.Data | None
        monthly_bucket: DF.Data | None
    # end: auto-generated types

    def validate(self) -> None:
        if not self.enabled:
            return
        if not self.frequent_bucket:
            frappe.throw(_("Frequent Bucket is required when backups are enabled."))
        if self.backup_interval_hours < 1:
            frappe.throw(_("Backup Interval (Hours) must be at least 1."))

    @frappe.whitelist()
    def run_backup_now(self) -> dict:
        """Manually back up the database to the frequent bucket only. Raises on failure.

        Unlike the scheduled run, this does not touch the daily/monthly tiers or
        the file mirror -- it is a quick on-demand database snapshot.
        """
        if not frappe.has_permission(self.doctype, "write"):
            frappe.throw(_("Not permitted to run a backup."), frappe.PermissionError)
        if not self.frequent_bucket:
            frappe.throw(_("Set a Frequent Bucket before running a backup."))
        result = _run_backup(self, throw_on_error=True, only_frequent=True, publish=True)
        return {
            "data": result,
            "message": _("Backup uploaded to: {0}").format(", ".join(result["tiers"]) or _("no buckets")),
        }

    @frappe.whitelist()
    def backup_files_now(self) -> dict:
        """Queue a full, force-overwrite mirror of every file to the mirror bucket."""
        if not frappe.has_permission(self.doctype, "write"):
            frappe.throw(_("Not permitted to run a backup."), frappe.PermissionError)
        if not self.mirror_bucket:
            frappe.throw(_("Set a File Mirror Bucket before backing up files."))
        frappe.enqueue(
            "connect_diagnostics_core.connect_diagnostics_core.doctype.backup_settings.backup_settings.run_full_file_mirror",
            queue="long",
            timeout=3600,
            job_id="gcs-mirror-full",
            deduplicate=True,
            force=True,
            enqueue_after_commit=True,
        )
        return {"data": None, "message": _("Full file mirror has been queued.")}

    @frappe.whitelist()
    def test_connection(self) -> dict:
        """Check access to every configured bucket without uploading anything."""
        if not frappe.has_permission(self.doctype, "read"):
            frappe.throw(_("Not permitted."), frappe.PermissionError)

        results: dict[str, str] = {}
        buckets = {
            "frequent": self.frequent_bucket,
            "daily": self.daily_bucket,
            "monthly": self.monthly_bucket,
            "mirror": self.mirror_bucket,
        }
        for tier, bucket in buckets.items():
            if not bucket:
                continue
            try:
                check_bucket_access(bucket, self.gcs_project or None)
                results[tier] = _("OK ({0})").format(bucket)
            except Exception as exc:
                results[tier] = _("Failed ({0}): {1}").format(bucket, str(exc))

        ok = bool(results) and all(value.startswith("OK") for value in results.values())
        return {
            "data": results,
            "message": _("All buckets reachable.") if ok else _("One or more buckets are not reachable."),
        }


def _collect_backup_files(odb: object) -> list[str]:
    """Gather the database + config artifact paths from a BackupGenerator run.

    Files are never included here; they are handled by the separate mirror.
    """
    paths = [
        cast("str | None", getattr(odb, "backup_path_db", None)),
        cast("str | None", getattr(odb, "backup_path_conf", None)),
    ]
    return [path for path in paths if path]


def _run_backup(
    settings: BackupSettings,
    *,
    throw_on_error: bool,
    only_frequent: bool = False,
    publish: bool = False,
) -> dict:
    """Back up the database to the due tiers and mirror files to the mirror bucket.

    The database backup (db + config, never files) goes to whichever retention
    tiers are due; public/private files are additively mirrored separately so the
    backups stay small and nothing is ever deleted from the buckets. With
    ``only_frequent`` the run targets just the frequent bucket and skips the
    daily/monthly tiers and the file mirror (used by the manual button). With
    ``publish`` a progress bar is streamed to the client. On failure the status
    is recorded; the error is re-raised only when ``throw_on_error`` is set
    (manual runs), otherwise logged (scheduler).
    """
    now = now_datetime()
    prefix = site_slug(cast(str, frappe.local.site))

    def _progress(percent: int, description: str) -> None:
        if publish:
            frappe.publish_progress(percent, title=_("Backing up"), description=description)

    try:
        _progress(10, _("Creating database backup…"))
        odb = new_backup(ignore_files=True, force=True)
        files = _collect_backup_files(odb)

        if only_frequent:
            due = {"frequent": settings.frequent_bucket} if settings.frequent_bucket else {}
        else:
            due = buckets_due(
                now=now,
                frequent_bucket=settings.frequent_bucket,
                daily_bucket=settings.daily_bucket,
                monthly_bucket=settings.monthly_bucket,
                last_daily_on=getdate(settings.last_daily_on) if settings.last_daily_on else None,
                last_monthly_on=settings.last_monthly_on,
            )

        _progress(50, _("Uploading database backup…"))
        uploaded_tiers: list[str] = []
        for tier, bucket in due.items():
            upload_files_to_bucket(bucket, prefix, files, settings.gcs_project or None)
            uploaded_tiers.append(tier)

        mirrored = False
        if not only_frequent and settings.mirror_bucket:
            _progress(75, _("Mirroring files…"))
            mirror_files_to_bucket(settings.mirror_bucket, mirror_roots(), settings.gcs_project or None)
            mirrored = True

        _progress(100, _("Backup complete."))
        settings.db_set(
            {
                "last_backup_on": now,
                "last_backup_status": "Success",
                "last_error": None,
            }
        )
        if "daily" in uploaded_tiers:
            settings.db_set("last_daily_on", now.date())
        if "monthly" in uploaded_tiers:
            settings.db_set("last_monthly_on", now.strftime("%Y-%m"))
        if mirrored:
            settings.db_set("last_mirror_on", now)
        frappe.db.commit()

        logger.info(f"Backup uploaded to tiers: {', '.join(uploaded_tiers) or 'none'}; mirrored={mirrored}")
        return {"tiers": uploaded_tiers, "mirrored": mirrored}

    except Exception as exc:
        settings.db_set(
            {
                "last_backup_on": now,
                "last_backup_status": "Failed",
                "last_error": str(exc),
            }
        )
        frappe.db.commit()
        frappe.log_error(title="Backup to GCS failed", message=frappe.get_traceback())
        logger.error(f"Backup to GCS failed: {exc}")
        if throw_on_error:
            raise
        return {"tiers": [], "mirrored": False}


def run_scheduled_backup() -> None:
    """Scheduler entry point. Runs hourly and self-throttles by interval."""
    settings = cast(BackupSettings, frappe.get_single("Backup Settings"))
    if not settings.enabled:
        return

    if settings.last_backup_on:
        elapsed = time_diff_in_hours(now_datetime(), settings.last_backup_on)
        if elapsed < settings.backup_interval_hours:
            return

    _run_backup(settings, throw_on_error=False)


def run_full_file_mirror(force: bool = False) -> None:
    """Background job: mirror every public/private file to the mirror bucket.

    Never deletes; with ``force`` it overwrites every object. Enqueued by the
    "Backup Files" button.
    """
    settings = cast(BackupSettings, frappe.get_single("Backup Settings"))
    if not settings.mirror_bucket:
        return
    try:
        mirror_files_to_bucket(
            settings.mirror_bucket, mirror_roots(), settings.gcs_project or None, force=force
        )
        settings.db_set("last_mirror_on", now_datetime())
        frappe.db.commit()
    except Exception as exc:
        settings.db_set("last_error", str(exc))
        frappe.db.commit()
        frappe.log_error(title="Full file mirror failed", message=frappe.get_traceback())
        logger.error(f"Full file mirror failed: {exc}")
        raise
