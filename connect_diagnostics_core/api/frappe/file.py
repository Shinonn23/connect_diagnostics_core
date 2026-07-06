# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

from typing import cast

import frappe
from frappe.core.doctype.file.file import File

from connect_diagnostics_core.utils.gcs_backup import (
    mirror_roots,
    object_name_for_path,
    upload_one_to_bucket,
)

logger = frappe.logger("backup", allow_site=True)


def mirror_file_on_upload(doc: File, method: str) -> None:
    """Push a newly uploaded file to the GCS mirror bucket (background job).

    Skips folders and does nothing unless backups are enabled with a mirror
    bucket configured. The upload runs in a deduplicated background job after the
    File record is committed, so the upload request is never blocked by GCS.
    """
    if doc.is_folder:
        return

    enabled, mirror_bucket, project = frappe.db.get_value(
        "Backup Settings", "Backup Settings", ["enabled", "mirror_bucket", "gcs_project"]
    )
    if not enabled or not mirror_bucket:
        return

    object_name = object_name_for_path(doc.get_full_path(), mirror_roots())
    if not object_name:
        return

    frappe.enqueue(
        "connect_diagnostics_core.api.frappe.file.upload_file_to_mirror",
        queue="long",
        timeout=600,
        job_id=f"gcs-mirror-{doc.name}",
        deduplicate=True,
        enqueue_after_commit=True,
        bucket=cast(str, mirror_bucket),
        object_name=object_name,
        local_path=doc.get_full_path(),
        project=cast("str | None", project) or None,
    )


def upload_file_to_mirror(
    bucket: str,
    object_name: str,
    local_path: str,
    project: str | None = None,
) -> None:
    """Background job: upload one file to the mirror bucket. Never deletes."""
    try:
        upload_one_to_bucket(bucket, object_name, local_path, project)
    except Exception as exc:
        frappe.log_error(title="Mirror file upload failed", message=frappe.get_traceback())
        logger.error(f"Mirror file upload failed for {object_name}: {exc}")
        raise
