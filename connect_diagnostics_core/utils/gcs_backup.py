# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

import base64
import hashlib
import os
from datetime import date, datetime
from typing import TYPE_CHECKING

import frappe

if TYPE_CHECKING:
    from google.cloud.storage import Client

logger = frappe.logger("backup", allow_site=True)

# Read files in chunks so large attachments are never loaded fully into memory.
_HASH_CHUNK = 1024 * 1024


def buckets_due(
    now: datetime,
    frequent_bucket: str | None,
    daily_bucket: str | None,
    monthly_bucket: str | None,
    last_daily_on: date | None,
    last_monthly_on: str | None,
) -> dict[str, str]:
    """Decide which database-backup tiers should receive the current snapshot.

    Retention is enforced by GCP Object Lifecycle Management on each bucket, so
    this function only decides *where* to upload, never what to delete:

    - ``frequent``: every run (short lifecycle on GCP, e.g. delete > 7 days)
    - ``daily``: first run of each calendar day (e.g. delete > 30 days)
    - ``monthly``: first run of each calendar month (no deletion = forever)

    Returns a mapping of ``tier -> bucket name`` for the tiers that are due.
    """
    due: dict[str, str] = {}
    today = now.date()
    this_month = now.strftime("%Y-%m")

    if frequent_bucket:
        due["frequent"] = frequent_bucket
    if daily_bucket and last_daily_on != today:
        due["daily"] = daily_bucket
    if monthly_bucket and last_monthly_on != this_month:
        due["monthly"] = monthly_bucket

    return due


def site_slug(site: str) -> str:
    """Match Frappe's backup slug: the site name with dots replaced by underscores.

    e.g. ``uat.erp.connectdiagnostics.net`` -> ``uat_erp_connectdiagnostics_net``.
    """
    return site.replace(".", "_")


def files_to_upload(
    local_index: dict[str, str],
    remote_index: dict[str, str],
    force: bool = False,
) -> list[str]:
    """Return object names to upload for an additive mirror.

    Both indexes map ``object name -> content hash`` (base64 md5). A file is
    uploaded when it is missing remotely or its hash differs; with ``force`` set,
    every local file is uploaded (overwriting the bucket copy). Nothing is ever
    deleted: objects already in the bucket stay there even if the local file is
    gone. The result is sorted for deterministic runs.
    """
    if force:
        return sorted(local_index)
    return sorted(name for name, local_hash in local_index.items() if remote_index.get(name) != local_hash)


def mirror_roots() -> dict[str, str]:
    """Map ``{site slug}/public`` and ``{site slug}/private`` to their local dirs."""
    slug = site_slug(frappe.local.site)
    return {
        f"{slug}/public": frappe.get_site_path("public", "files"),
        f"{slug}/private": frappe.get_site_path("private", "files"),
    }


def object_name_for_path(full_path: str, roots: dict[str, str]) -> str | None:
    """Resolve the mirror object name for a local file under one of ``roots``.

    Returns ``{prefix}/{relative path}`` for the matching root, or ``None`` when
    the file is not inside any configured root.
    """
    abs_path = os.path.abspath(full_path)
    for prefix, root in roots.items():
        if not root:
            continue
        root_abs = os.path.abspath(root)
        if abs_path.startswith(root_abs + os.sep):
            rel = os.path.relpath(abs_path, root_abs).replace(os.sep, "/")
            return f"{prefix}/{rel}"
    return None


def file_md5_base64(path: str) -> str:
    """Return the base64-encoded md5 of a file, matching GCS ``blob.md5_hash``."""
    digest = hashlib.md5()
    # path is a server-side file discovered by walking the site's own files
    # directory (build_local_index), never user-supplied input.
    with open(path, "rb") as handle:  # nosemgrep
        for chunk in iter(lambda: handle.read(_HASH_CHUNK), b""):
            digest.update(chunk)
    return base64.b64encode(digest.digest()).decode("ascii")


def build_local_index(roots: dict[str, str]) -> dict[str, tuple[str, str]]:
    """Index files under each root as ``object name -> (local path, md5)``.

    ``roots`` maps an object-name prefix to a local directory. Only existing
    directories are walked; missing ones are skipped.
    """
    index: dict[str, tuple[str, str]] = {}
    for prefix, root in roots.items():
        if not root or not os.path.isdir(root):
            continue
        for dirpath, _dirs, filenames in os.walk(root):
            for filename in filenames:
                local_path = os.path.join(dirpath, filename)
                rel = os.path.relpath(local_path, root).replace(os.sep, "/")
                object_name = f"{prefix}/{rel}"
                index[object_name] = (local_path, file_md5_base64(local_path))
    return index


def _client(project: str | None) -> Client:
    """Build a GCS client using Application Default Credentials.

    On a GCP VM the credentials and token are fetched from the Compute Engine
    metadata server automatically, so no service account key is stored.
    """
    from google.cloud import storage

    return storage.Client(project=project) if project else storage.Client()


def check_bucket_access(bucket_name: str, project: str | None = None) -> None:
    """Raise if the bucket does not exist or the credentials cannot access it."""
    client = _client(project)
    # get_bucket raises google.cloud.exceptions.NotFound / Forbidden on failure.
    client.get_bucket(bucket_name)


def upload_files_to_bucket(
    bucket_name: str,
    object_prefix: str,
    file_paths: list[str],
    project: str | None = None,
) -> list[str]:
    """Upload local files to ``{object_prefix}/{basename}`` in the bucket.

    Returns the list of blob names written.
    """
    client = _client(project)
    bucket = client.bucket(bucket_name)

    uploaded: list[str] = []
    for path in file_paths:
        if not path or not os.path.exists(path):
            continue
        blob_name = f"{object_prefix}/{os.path.basename(path)}"
        bucket.blob(blob_name).upload_from_filename(path)
        uploaded.append(blob_name)

    return uploaded


def upload_one_to_bucket(
    bucket_name: str,
    object_name: str,
    local_path: str,
    project: str | None = None,
) -> bool:
    """Upload a single local file to ``object_name`` in the bucket.

    Overwrites the existing object (kept recoverable when Object Versioning is
    enabled). Returns ``False`` without uploading if the local file is missing.
    """
    if not local_path or not os.path.exists(local_path):
        return False
    client = _client(project)
    client.bucket(bucket_name).blob(object_name).upload_from_filename(local_path)
    return True


def mirror_files_to_bucket(
    bucket_name: str,
    roots: dict[str, str],
    project: str | None = None,
    force: bool = False,
) -> list[str]:
    """Additively mirror local file trees into a bucket, uploading only deltas.

    ``roots`` maps an object-name prefix (e.g. ``files/public``) to a local
    directory. The remote listing is fetched once, diffed against the local
    index, then new or changed files are uploaded (or every file when ``force``
    is set). Files are **never** deleted from the bucket. Returns the list of
    object names uploaded.
    """
    client = _client(project)
    bucket = client.bucket(bucket_name)

    local = build_local_index(roots)
    remote_index: dict[str, str] = {}
    if not force:
        prefixes = tuple(f"{prefix}/" for prefix in roots)
        remote_index = {
            blob.name: (blob.md5_hash or "")
            for blob in client.list_blobs(bucket_name)
            if blob.name.startswith(prefixes)
        }

    local_hashes = {name: md5 for name, (_path, md5) in local.items()}
    uploads = files_to_upload(local_hashes, remote_index, force=force)
    for object_name in uploads:
        bucket.blob(object_name).upload_from_filename(local[object_name][0])

    logger.info(f"Mirror to {bucket_name}: uploaded {len(uploads)} file(s), deleted 0 (force={force})")
    return uploads
