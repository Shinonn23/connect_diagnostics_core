"""
One-way (near-realtime) sync from a GitHub repo/Project board into Frappe Helpdesk,
plus a single manual escalation handoff in the other direction.

Direction overview
------------------
GitHub -> Helpdesk  (pull, scheduled every 10 min) — the only automatic direction
  * updated issues that are ALREADY linked -> update the HD Ticket (subject, body,
                                     priority, type, assignees). New, unlinked issues
                                     are NOT turned into tickets — tickets originate
                                     in Helpdesk.
  * Project board column                    -> HD Ticket.status (reconciled for ALL
                                     linked tickets every run, because moving a card
                                     does NOT bump issue.updated_at)
  * issue closed (e.g. PR merged)           -> HD Ticket.status = the configured
                                     "Resolved" status (awaiting user confirmation).
                                     The final close stays a Helpdesk-side action.

Helpdesk -> GitHub  (manual only, no automatic sync)
  * escalate_to_github(ticket)              -> create one GitHub issue + add it to the
                                     board and link it back. A deliberate triage action
                                     (agent-only button); there is no comment push and
                                     no status push back to GitHub.

Internal dev discussion stays in GitHub and is never pulled into Helpdesk; the customer
conversation stays in Helpdesk and is never pushed to GitHub.

Loop prevention
---------------
  * pull runs with frappe.flags.in_github_sync = True so any doc events stay inert.

Configuration
-------------
All config lives in the "GitHub Helpdesk Sync Settings" single DocType: owner/repo,
auth, project board ids, the Board Column ↔ Status mapping table, and the "Resolved"
status used when a GitHub issue closes. Nothing is hardcoded here — run init_settings()
(or the doctype's "Fetch Board Metadata") to populate the board ids from GitHub.
github_token may still be read from site_config.json as a fallback.
"""

import json
import mimetypes
import os
import re
import shutil
import subprocess
from collections import Counter
from urllib.parse import urlencode

import frappe
import requests
from frappe import _
from frappe.utils import get_datetime, md_to_html, now_datetime

API = "https://api.github.com"
GRAPHQL = "https://api.github.com/graphql"


# ----------------------------------------------------------------------------- helpers
SETTINGS = "GitHub Helpdesk Sync Settings"
SYNC_LOG = "GitHub Helpdesk Sync Log"

REQUIRED_TICKET_CUSTOM_FIELDS = {
    "HD Ticket": (
        "github_section",
        "sync_to_github",
        "github_issue_number",
        "github_url",
        "github_col",
        "github_last_synced",
        "github_project_item_id",
    ),
}

DEFAULT_HELPDESK_TEMPLATE = "Default"
DEFAULT_HELPDESK_TEMPLATE_FIELDS = (
    {
        "fieldname": "sync_to_github",
        "placeholder": "Choose whether this ticket syncs with GitHub",
    },
    {
        "fieldname": "github_issue_number",
        "placeholder": "GitHub issue number",
    },
    {
        "fieldname": "github_url",
        "placeholder": "GitHub issue URL",
    },
    {
        "fieldname": "github_last_synced",
        "placeholder": "Last GitHub sync time",
    },
)


def _doctype_exists(doctype):
    return bool(frappe.db.exists("DocType", doctype))


def _settings():
    """Return the GitHub Helpdesk Sync Settings single doc, or None if not installed yet."""
    if not _doctype_exists(SETTINGS):
        return None
    return frappe.get_cached_doc(SETTINGS)


def _cfg(key, default=None):
    """Read a config value: DocType field first, then site_config, then default."""
    s = _settings()
    if s is not None:
        if key == "github_token":
            val = s.get_password("github_token", raise_exception=False) if s.github_token else None
            return val or frappe.conf.get(key) or default
        val = s.get(key)
        if val not in (None, ""):
            return val
    return frappe.conf.get(key, default)


def _enabled():
    s = _settings()
    return True if s is None else bool(s.enabled)


def _toggle(field, default=True):
    s = _settings()
    if s is None:
        return default
    value = s.get(field)
    if value in (None, ""):
        return default
    return bool(value)


def _owner_repo():
    return _cfg("github_owner"), _cfg("github_repo")


def _project_id():
    return _cfg("project_id")


def _status_field_id():
    return _cfg("status_field_id")


def _resolved_status():
    """HD Ticket Status applied when a linked GitHub issue is closed (awaiting confirmation)."""
    return _cfg("resolved_status") or "Resolved"


def _status_category(status):
    """Category for an HD Ticket Status: board mapping first, then the status doc, else Open."""
    if status in _status_option_ids():
        return _board_category(status)
    return frappe.db.get_value("HD Ticket Status", status, "category") or "Open"


def _status_option_ids():
    """board_column -> option_id, from the settings mapping table."""
    s = _settings()
    if s is None:
        return {}
    return {r.board_column: r.option_id for r in (s.status_mappings or []) if r.option_id}


def _board_category(label):
    """HD Ticket Status category for a board column, from the settings mapping table."""
    s = _settings()
    if s is not None:
        for r in s.status_mappings or []:
            if r.board_column == label and r.category:
                return r.category
    return "Open"


def _board_color(label):
    """HD Ticket Status color for a board column, from the settings mapping table."""
    s = _settings()
    if s is not None:
        for r in s.status_mappings or []:
            if r.board_column == label and r.get("color"):
                return r.color
    return "Gray"


def _headers():
    return {
        "Authorization": f"Bearer {_cfg('github_token')}",
        "Accept": "application/vnd.github+json",
    }


def _json_dumps(data):
    return json.dumps(data, indent=2, sort_keys=True, default=str)


def _duration_seconds(started_at, finished_at):
    return max((finished_at - started_at).total_seconds(), 0)


def _start_sync_log(run_type):
    if not _doctype_exists(SYNC_LOG):
        return None
    started_at = now_datetime()
    doc = frappe.get_doc(
        {
            "doctype": SYNC_LOG,
            "run_type": run_type,
            "status": "Running",
            "started_at": started_at,
            "summary": f"{run_type} started at {started_at:%Y-%m-%d %H:%M:%S}",
        }
    )
    doc.insert(ignore_permissions=True)
    return doc.name


def _finish_sync_log(log_name, status, summary, stats=None, details=None, traceback=None):
    if not log_name:
        return None
    finished_at = now_datetime()
    doc = frappe.get_doc(SYNC_LOG, log_name)
    started_at = get_datetime(doc.started_at) if doc.started_at else finished_at
    stats = stats or {}
    doc.status = status
    doc.finished_at = finished_at
    doc.duration_seconds = _duration_seconds(started_at, finished_at)
    doc.changed_issues = stats.get("changed_issues", 0)
    doc.board_items = stats.get("board_items", 0)
    doc.created_count = stats.get("created_count", 0)
    doc.updated_count = stats.get("updated_count", 0)
    doc.skipped_count = stats.get("skipped_count", 0)
    doc.error_count = stats.get("error_count", 0)
    doc.summary = summary
    doc.details_json = _json_dumps(details or {})
    doc.traceback = traceback or ""
    doc.save(ignore_permissions=True)
    return doc.name


def _empty_sync_stats():
    return {
        "changed_issues": 0,
        "board_items": 0,
        "created_count": 0,
        "updated_count": 0,
        "skipped_count": 0,
        "error_count": 0,
    }


def _count_outcome(stats, outcome):
    if outcome == "created":
        stats["created_count"] += 1
    elif outcome in ("updated", "status_updated"):
        stats["updated_count"] += 1
    elif outcome and outcome.startswith("skipped"):
        stats["skipped_count"] += 1
    elif outcome == "failed":
        stats["error_count"] += 1


# --------------------------------------------------------------------- transport (gh / token)
def _transport():
    """'gh' (GitHub CLI, default) or 'token' (PAT via requests)."""
    s = _settings()
    if s is not None and s.auth_method == "Personal Access Token":
        return "token"
    return "gh"


def _gh_bin():
    return _cfg("gh_path") or shutil.which("gh") or "/usr/bin/gh"


def _has_auth():
    """gh transport relies on the server's gh login; token transport needs a token."""
    if _transport() == "gh":
        return bool(_gh_bin())
    return bool(_cfg("github_token"))


def _gh_env():
    env = os.environ.copy()
    env.setdefault("HOME", os.path.expanduser("~") or "/home/frappe")
    # make sure common bin dirs are reachable for the scheduler/worker
    env["PATH"] = (env.get("PATH", "") or "") + ":/usr/bin:/usr/local/bin:/bin"
    return env


def _run_gh(args, input_text=None):
    proc = subprocess.run(
        [_gh_bin(), *args], input=input_text, capture_output=True, text=True, env=_gh_env(), timeout=90
    )
    if proc.returncode != 0:
        raise Exception(f"gh {' '.join(args[:2])} failed: {proc.stderr.strip() or proc.stdout.strip()}")
    return proc.stdout


def _rest(method, path, params=None, json=None):
    if _transport() == "gh":
        full = path + ("?" + urlencode(params) if params else "")
        args = ["api", "-X", method, full, "-H", "Accept: application/vnd.github+json"]
        input_text = None
        if json is not None:
            import json as _j

            args += ["--input", "-"]
            input_text = _j.dumps(json)
        out = _run_gh(args, input_text)
        return frappe.parse_json(out) if out.strip() else {}
    # token transport
    kw = {}
    if params:
        kw["params"] = params
    if json is not None:
        kw["json"] = json
    r = requests.request(method, f"{API}{path}", headers=_headers(), timeout=30, **kw)
    r.raise_for_status()
    return r.json() if r.text else {}


def _graphql(query, variables):
    if _transport() == "gh":
        args = ["api", "graphql", "-f", f"query={query}"]
        for k, v in variables.items():
            if v is None:
                continue
            if isinstance(v, bool):
                args += ["-F", f"{k}={'true' if v else 'false'}"]
            elif isinstance(v, int):
                args += ["-F", f"{k}={v}"]
            else:
                args += ["-f", f"{k}={v}"]
        data = frappe.parse_json(_run_gh(args))
    else:
        r = requests.post(
            GRAPHQL, headers=_headers(), json={"query": query, "variables": variables}, timeout=30
        )
        r.raise_for_status()
        data = r.json()
    if data.get("errors"):
        raise Exception("GitHub GraphQL: " + json.dumps(data["errors"]))
    return data["data"]


def connection_info():
    """Verify access and report granted scopes, transport-aware."""
    owner, repo = _owner_repo()
    transport = _transport()
    full_name = _rest("GET", f"/repos/{owner}/{repo}").get("full_name")
    if transport == "gh":
        try:
            status = subprocess.run(
                [_gh_bin(), "auth", "status"], capture_output=True, text=True, env=_gh_env(), timeout=30
            )
            blob = status.stdout + status.stderr
            m = re.search(r"Token scopes:\s*(.+)", blob)
            scopes = m.group(1).replace("'", "").strip() if m else ""
        except Exception:
            scopes = ""
    else:
        r = requests.get(f"{API}/repos/{owner}/{repo}", headers=_headers(), timeout=30)
        scopes = r.headers.get("x-oauth-scopes", "")
    scope_list = [s.strip() for s in scopes.split(",")]
    return {
        "ok": bool(full_name),
        "transport": transport,
        "target": full_name,
        "scopes": scopes,
        "can_push_board": "project" in scope_list,
    }


def missing_ticket_fields():
    """Return required GitHub custom fields not present on Helpdesk doctypes."""
    missing = {}
    for doctype, fieldnames in REQUIRED_TICKET_CUSTOM_FIELDS.items():
        if not _doctype_exists(doctype):
            missing[doctype] = list(fieldnames)
            continue
        for fieldname in fieldnames:
            if not frappe.db.exists("Custom Field", f"{doctype}-{fieldname}"):
                missing.setdefault(doctype, []).append(fieldname)
    return missing


def missing_ticket_template_fields():
    """Return GitHub fields missing from the Helpdesk Default ticket template."""
    if not _doctype_exists("HD Ticket Template") or not _doctype_exists("HD Ticket Template Field"):
        return [row["fieldname"] for row in DEFAULT_HELPDESK_TEMPLATE_FIELDS]
    if not frappe.db.exists("HD Ticket Template", DEFAULT_HELPDESK_TEMPLATE):
        return [row["fieldname"] for row in DEFAULT_HELPDESK_TEMPLATE_FIELDS]
    existing = set(
        frappe.get_all(
            "HD Ticket Template Field",
            filters={"parent": DEFAULT_HELPDESK_TEMPLATE},
            pluck="fieldname",
        )
    )
    return [row["fieldname"] for row in DEFAULT_HELPDESK_TEMPLATE_FIELDS if row["fieldname"] not in existing]


def refresh_project_metadata():
    """Fetch live Project v2 metadata and preserve admin mapping choices."""
    meta = fetch_project_metadata()
    s = frappe.get_single(SETTINGS)
    s.project_id = meta["project_id"]
    s.status_field_id = meta["status_field_id"]
    prior = {r.board_column: r for r in (s.status_mappings or [])}
    s.status_mappings = []
    for name, option_id in meta["options"].items():
        existing = prior.get(name)
        hd = (
            frappe.db.get_value("HD Ticket Status", name, ["category", "color"], as_dict=True)
            if _doctype_exists("HD Ticket Status") and frappe.db.exists("HD Ticket Status", name)
            else None
        )
        s.append(
            "status_mappings",
            {
                "board_column": name,
                "option_id": option_id,
                "hd_status": (existing and existing.hd_status) or (name if hd else None),
                "category": (existing and existing.category) or (hd and hd.category) or "Open",
                "color": (existing and existing.get("color")) or (hd and hd.color) or "Gray",
            },
        )
    s.save(ignore_permissions=True)
    return {"options": len(meta["options"]), "project_id": s.project_id, "status_field_id": s.status_field_id}


def preflight_check():
    """Validate configuration without mutating GitHub or Helpdesk business data."""
    log_name = _start_sync_log("Preflight Check")
    checks = []

    def add(name, status, message):
        checks.append({"name": name, "status": status, "message": message})

    try:
        settings_ok = _doctype_exists(SETTINGS) and _settings() is not None
        add(
            "Settings DocType",
            "pass" if settings_ok else "fail",
            "GitHub Helpdesk Sync Settings is installed.",
        )

        owner, repo = _owner_repo()
        add(
            "Repository",
            "pass" if owner and repo else "fail",
            f"{owner or '(missing)'}/{repo or '(missing)'}",
        )

        auth_ok = _has_auth()
        add("Authentication", "pass" if auth_ok else "fail", f"Transport: {_transport()}")

        if auth_ok and owner and repo:
            try:
                info = connection_info()
                add("GitHub API", "pass" if info.get("ok") else "fail", info.get("target") or "No target.")
            except Exception as exc:
                add("GitHub API", "fail", str(exc))

        if _cfg("project_number"):
            add("Project Number", "pass", str(_cfg("project_number")))
        else:
            add("Project Number", "fail", "Project Number is not set.")

        if _project_id() and _status_field_id():
            add("Cached Project Metadata", "pass", "Project and Status field IDs are set.")
        else:
            add("Cached Project Metadata", "fail", "Fetch board metadata or run Repair Setup.")

        mappings = _status_option_ids()
        add("Status Mappings", "pass" if mappings else "fail", f"{len(mappings)} mapped status option(s).")

        missing = missing_ticket_fields()
        add(
            "Helpdesk Custom Fields",
            "pass" if not missing else "fail",
            "All required custom fields exist." if not missing else _json_dumps(missing),
        )

        missing_template_fields = missing_ticket_template_fields()
        add(
            "Helpdesk Ticket UI",
            "pass" if not missing_template_fields else "fail",
            "GitHub fields are present in the Default ticket template."
            if not missing_template_fields
            else f"Missing from Default template: {', '.join(missing_template_fields)}",
        )

        failures = [c for c in checks if c["status"] == "fail"]
        warnings = [c for c in checks if c["status"] == "warn"]
        status = "Failed" if failures else "Partial Failure" if warnings else "Success"
        summary = f"{len(checks) - len(failures)} of {len(checks)} preflight checks passed."
        details = {"checks": checks}
        _finish_sync_log(log_name, status, summary, details=details)
        return {"ok": not failures, "checks": checks, "log_name": log_name}
    except Exception:
        tb = frappe.get_traceback()
        _finish_sync_log(
            log_name, "Failed", "Preflight check failed.", details={"checks": checks}, traceback=tb
        )
        frappe.log_error(tb, "github_sync.preflight_check")
        return {"ok": False, "checks": checks, "error": tb, "log_name": log_name}


def repair_setup():
    """Repair local setup and refresh project metadata while preserving mappings."""
    log_name = _start_sync_log("Repair Setup")
    details = {}
    try:
        details["missing_fields_before"] = missing_ticket_fields()
        details["custom_fields"] = ensure_ticket_fields()
        details["missing_fields_after"] = missing_ticket_fields()
        details["missing_template_fields_before"] = missing_ticket_template_fields()
        details["template_fields"] = ensure_ticket_template_fields()
        details["missing_template_fields_after"] = missing_ticket_template_fields()
        if _has_auth() and _cfg("project_number"):
            details["project_metadata"] = refresh_project_metadata()
        else:
            details["project_metadata"] = {"skipped": "Missing GitHub authentication or project number."}
        status = (
            "Success"
            if not details["missing_fields_after"] and not details["missing_template_fields_after"]
            else "Partial Failure"
        )
        summary = "Repair setup completed."
        _finish_sync_log(log_name, status, summary, details=details)
        return {"ok": status == "Success", "log_name": log_name, **details}
    except Exception:
        tb = frappe.get_traceback()
        _finish_sync_log(log_name, "Failed", "Repair setup failed.", details=details, traceback=tb)
        frappe.log_error(tb, "github_sync.repair_setup")
        return {"ok": False, "log_name": log_name, "error": tb, **details}


def _html_to_text(html):
    """Best-effort HTML -> plain text for outgoing GitHub comments (no html2text dep)."""
    try:
        from bs4 import BeautifulSoup

        return BeautifulSoup(html or "", "html.parser").get_text("\n").strip()
    except Exception:
        return html or ""


# ------------------------------------------------------- private GitHub image re-hosting
# Issue bodies in a PRIVATE repo embed attachments as
# <img ... src="https://github.com/user-attachments/assets/<uuid>"> which 404 without a
# GitHub session, so the ticket can't render them. We download each via the authenticated
# transport, store it as a Frappe File attached to the ticket, and rewrite the src.
_GH_ASSET_MARKER = "user-attachments/assets"
_GH_IMG_SRC_RE = re.compile(
    r'(<img\b[^>]*?\bsrc=")(https://github\.com/user-attachments/assets/[^"]+)(")', re.I
)


def _auth_token():
    """A GitHub token for authenticated asset downloads (token transport or gh login)."""
    if _transport() == "token":
        return _cfg("github_token")
    try:
        return _run_gh(["auth", "token"]).strip()
    except Exception:
        return None


def _download_github_asset(url):
    """Download a (private) GitHub attachment; return (bytes, content_type) or (None, None)."""
    token = _auth_token()
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    try:
        r = requests.get(url, headers=headers, timeout=60, allow_redirects=True)
        r.raise_for_status()
        return r.content, (r.headers.get("Content-Type") or "").split(";")[0].strip()
    except Exception:
        frappe.log_error(frappe.get_traceback(), "github_sync.download_asset")
        return None, None


def _rehost_github_images(html, ticket):
    """Rewrite private GitHub <img> attachments in `html` to Frappe Files on `ticket`.

    Idempotent: a File whose name encodes the asset uuid is reused, so repeated pulls do
    not re-download or duplicate. Returns (html, rehosted_count). A failed download leaves
    the original <img> untouched so a later run can retry.
    """
    if not html or _GH_ASSET_MARKER not in html:
        return html, 0
    count = 0

    def repl(m):
        nonlocal count
        url = m.group(2)
        uuid = url.rstrip("/").rsplit("/", 1)[-1]
        existing = frappe.db.get_value(
            "File",
            {
                "attached_to_doctype": "HD Ticket",
                "attached_to_name": ticket,
                "file_name": ["like", f"gh-{uuid}%"],
            },
            "file_url",
        )
        if existing:
            return m.group(1) + existing + m.group(3)
        content, ctype = _download_github_asset(url)
        if not content:
            return m.group(0)
        ext = mimetypes.guess_extension(ctype or "") or ".png"
        f = frappe.get_doc(
            {
                "doctype": "File",
                "file_name": f"gh-{uuid}{ext}",
                "attached_to_doctype": "HD Ticket",
                "attached_to_name": ticket,
                "is_private": 1,
                "content": content,
            }
        ).insert(ignore_permissions=True)
        count += 1
        return m.group(1) + f.file_url + m.group(3)

    return _GH_IMG_SRC_RE.sub(repl, html), count


def ensure_board_status(label):
    """Create an HD Ticket Status that mirrors a board column, if missing."""
    if not label or frappe.db.exists("HD Ticket Status", label):
        return
    frappe.get_doc(
        {
            "doctype": "HD Ticket Status",
            "label_agent": label,
            "label_customer": label,
            "category": _board_category(label),
            "color": _board_color(label),
            "enabled": 1,
        }
    ).insert(ignore_permissions=True)


def _label_priority(labels):
    for l in labels:
        n = l.lower()
        if "urgent" in n or n.startswith("p0"):
            return "Urgent"
        if "high" in n or n.startswith("p1"):
            return "High"
        if "medium" in n or n.startswith("p2"):
            return "Medium"
        if "low" in n or n.startswith("p3"):
            return "Low"
    return None


# board "Issue Type" single-select -> HD Ticket Type (dev vocabulary, kept 1:1 both sides)
DEV_TICKET_TYPES = ["Bug", "Enhancement", "New Requirement", "Question", "Task"]
# board-only Issue Types that predate the shared vocabulary -> nearest dev type
BOARD_TYPE_ALIAS = {"Configuration Issue": "Task", "UAT Execution": "Task"}


def _ticket_type(board_type, labels):
    """Prefer the board's Issue Type; fall back to label heuristics, else Question."""
    if board_type in DEV_TICKET_TYPES:
        return board_type
    if board_type in BOARD_TYPE_ALIAS:
        return BOARD_TYPE_ALIAS[board_type]
    low = [l.lower() for l in labels]
    if any("bug" in l for l in low):
        return "Bug"
    if any("enhancement" in l or "feature" in l for l in low):
        return "Enhancement"
    return "Question"


def _user_map():
    """{github_login_lower: user_email} from GitHub Helpdesk Sync Settings child table."""
    s = _settings()
    if s is None:
        return {}
    return {
        (r.github_login or "").lower(): r.user
        for r in (s.get("github_user_map") or [])
        if r.github_login and r.user
    }


def _users_for_logins(logins):
    m = _user_map()
    seen, out = set(), []
    for login in logins or []:
        user = m.get((login or "").lower())
        if user and user not in seen:
            seen.add(user)
            out.append(user)
    return out


# ------------------------------------------------------------------- board (Project v2)
def fetch_board():
    """Return {issue_number: {status, priority, module, item_id}} for every card."""
    q = """
    query($pid:ID!, $cursor:String){
      node(id:$pid){ ... on ProjectV2 {
        items(first:100, after:$cursor){
          pageInfo{ hasNextPage endCursor }
          nodes{
            id
            content{ ... on Issue {
              number
              state
              assignees(first:10){ nodes{ login } }
            } }
            status:    fieldValueByName(name:"Status"){    ... on ProjectV2ItemFieldSingleSelectValue { name } }
            priority:  fieldValueByName(name:"Priority"){  ... on ProjectV2ItemFieldSingleSelectValue { name } }
            module:    fieldValueByName(name:"Module"){    ... on ProjectV2ItemFieldSingleSelectValue { name } }
            issueType: fieldValueByName(name:"Issue Type"){... on ProjectV2ItemFieldSingleSelectValue { name } }
          }
        }
      }}
    }"""
    out, cursor = {}, None
    while True:
        d = _graphql(q, {"pid": _project_id(), "cursor": cursor})
        items = d["node"]["items"]
        for it in items["nodes"]:
            c = it.get("content") or {}
            n = c.get("number")
            if n is None:
                continue
            out[n] = {
                "item_id": it["id"],
                "state": c.get("state"),
                "status": (it.get("status") or {}).get("name"),
                "priority": (it.get("priority") or {}).get("name"),
                "module": (it.get("module") or {}).get("name"),
                "issue_type": (it.get("issueType") or {}).get("name"),
                "assignees": [a["login"] for a in ((c.get("assignees") or {}).get("nodes") or [])],
            }
        if not items["pageInfo"]["hasNextPage"]:
            break
        cursor = items["pageInfo"]["endCursor"]
    return out


def fetch_project_metadata():
    """Resolve project node id, Status field id and its option ids from project_number."""
    owner, _ = _owner_repo()
    number = int(_cfg("project_number") or 0)
    if not number:
        raise Exception("GitHub Helpdesk Sync Settings: Project Number is not set")
    q = """
    query($owner:String!, $number:Int!){
      user(login:$owner){
        projectV2(number:$number){
          id
          field(name:"Status"){
            ... on ProjectV2SingleSelectField { id options{ id name } }
          }
        }
      }
    }"""
    d = _graphql(q, {"owner": owner, "number": number})
    proj = d["user"]["projectV2"]
    field = proj["field"] or {}
    return {
        "project_id": proj["id"],
        "status_field_id": field.get("id"),
        "options": {o["name"]: o["id"] for o in (field.get("options") or [])},
    }


# --------------------------------------------------------------------------------- pull
def _ticket_for_issue(number):
    name = frappe.db.get_value("HD Ticket", {"github_issue_number": number}, "name")
    if name:
        return name
    # fall back to subject prefix (tickets created by the one-off importer)
    rows = frappe.get_all("HD Ticket", filters={"subject": ["like", f"#{number}:%"]}, pluck="name", limit=1)
    return rows[0] if rows else None


def _apply_issue(issue, board):
    """Update one already-linked HD Ticket from a GitHub issue dict (REST shape).

    Pull is one-way and update-only: an issue with no linked ticket is skipped, never
    created — tickets originate in Helpdesk and reach GitHub only via escalation.
    """
    n = issue["number"]
    name = _ticket_for_issue(n)
    if not name:
        return {"outcome": "skipped_no_ticket", "issue_number": n}
    # per-ticket opt-out: a ticket with "Sync to GitHub" off is frozen — pull won't overwrite it
    if not frappe.db.get_value("HD Ticket", name, "sync_to_github"):
        return {"outcome": "skipped_opt_out", "issue_number": n, "ticket": name}

    labels = [l["name"] for l in issue.get("labels", [])]
    b = board.get(n) or {}
    if issue["state"] == "closed":
        # dev work done (issue/PR closed) -> Resolved, awaiting user confirmation in Helpdesk
        status = _resolved_status()
    elif b.get("status"):
        status = b["status"]
        ensure_board_status(status)
    else:
        status = "Open"
    prio = b.get("priority") or _label_priority(labels) or "Medium"
    ttype = _ticket_type(b.get("issue_type"), labels)
    assignees = _users_for_logins(b.get("assignees"))
    author = (issue.get("user") or {}).get("login") or "ghost"
    subject = f"#{n}: {issue.get('title') or ''}"[:140]
    meta = f"GitHub Issue [#{n}]({issue['html_url']}) · author @{author}"
    if b.get("module"):
        meta += f" · module: {b['module']}"
    if labels:
        meta += f" · labels: {', '.join(labels)}"
    description = md_to_html(meta + "\n\n---\n\n" + (issue.get("body") or ""))
    description, _ = _rehost_github_images(description, name)

    doc = frappe.get_doc("HD Ticket", name)
    doc.subject = subject
    doc.description = description
    doc.priority = prio
    doc.ticket_type = ttype
    doc.github_issue_number = n
    doc.github_url = issue["html_url"]
    doc.github_project_item_id = b.get("item_id")
    doc.github_last_synced = now_datetime()
    doc.save(ignore_permissions=True)
    frappe.db.set_value(
        "HD Ticket",
        name,
        {"status": status, "status_category": _status_category(status)},
        update_modified=False,
    )
    _assign_ticket(name, assignees)
    return {"outcome": "updated", "issue_number": n, "ticket": name}


def _assign_ticket(ticket, users):
    """Add ToDo assignments from mapped GitHub assignees, without re-notifying each pull."""
    if not users:
        return
    current = set(frappe.parse_json(frappe.db.get_value("HD Ticket", ticket, "_assign") or "[]"))
    todo = [u for u in users if u not in current]
    if not todo:
        return
    from frappe.desk.form.assign_to import add as assign_add

    try:
        assign_add(
            {
                "assign_to": todo,
                "doctype": "HD Ticket",
                "name": ticket,
                "description": "Synced from GitHub assignees",
                "notify": 0,
            }
        )
    except Exception:
        frappe.log_error(frappe.get_traceback(), "github_sync.assign")


def _reconcile_board_status(board):
    """Board moves don't touch issue.updated_at, so realign every linked ticket here.

    A closed issue resolves its ticket regardless of the card's column; an open issue
    follows its board column. Frozen (sync off) tickets are left untouched.
    """
    counts = Counter()
    details = []
    for n, b in board.items():
        if b.get("state") == "CLOSED":
            target = _resolved_status()
        elif b.get("status"):
            target = b["status"]
        else:
            continue
        name = _ticket_for_issue(n)
        if not name:
            continue
        cur = frappe.db.get_value("HD Ticket", name, ["status", "sync_to_github"], as_dict=True)
        if not cur or not cur.sync_to_github or cur.status == target:
            continue
        ensure_board_status(target)
        frappe.db.set_value(
            "HD Ticket",
            name,
            {
                "status": target,
                "status_category": _status_category(target),
                "github_project_item_id": b.get("item_id"),
            },
            update_modified=False,
        )
        counts["status_updated"] += 1
        details.append({"issue_number": n, "ticket": name, "from": cur.status, "to": target})
    return {"counts": dict(counts), "details": details}


def _get_cursor():
    s = _settings()
    if s is not None and s.last_pull:
        return s.last_pull
    return frappe.db.get_default("github_last_pull")


def _set_cursor(value, status_text=None):
    s = _settings()
    if s is not None:
        frappe.db.set_single_value(
            SETTINGS, {"last_pull": value, "last_pull_status": status_text or ""}, update_modified=False
        )
    else:
        frappe.db.set_default("github_last_pull", value)


def _set_last_pull_status(status_text):
    s = _settings()
    if s is not None:
        frappe.db.set_single_value(SETTINGS, "last_pull_status", status_text or "", update_modified=False)


def _sync_summary(stats):
    return (
        f"{stats.get('changed_issues', 0)} changed issue(s), "
        f"{stats.get('board_items', 0)} board item(s), "
        f"{stats.get('created_count', 0)} created, "
        f"{stats.get('updated_count', 0)} updated, "
        f"{stats.get('skipped_count', 0)} skipped, "
        f"{stats.get('error_count', 0)} error(s)"
    )


def pull(run_type="Scheduled Pull"):
    """Scheduled entrypoint: pull GitHub -> Helpdesk."""
    log_name = _start_sync_log(run_type)
    if not _enabled() or not _toggle("pull_enabled", True):
        summary = "GitHub pull skipped because sync is disabled."
        _finish_sync_log(log_name, "Skipped", summary, details={"reason": "disabled"})
        return {"skipped": "disabled", "log_name": log_name}
    if not _has_auth():
        summary = "GitHub pull skipped because authentication is not configured."
        frappe.log_error("github_sync: no GitHub auth (gh login or token)", "github_sync")
        _finish_sync_log(log_name, "Skipped", summary, details={"reason": "no auth"})
        return {"skipped": "no auth", "log_name": log_name}
    owner, repo = _owner_repo()
    frappe.flags.in_github_sync = True
    started = now_datetime()
    stats = _empty_sync_stats()
    details = {"issues": [], "board_reconcile": []}
    try:
        board = fetch_board()
        stats["board_items"] = len(board)
        since = _get_cursor()
        params = {"state": "all", "per_page": 100, "sort": "updated", "direction": "asc"}
        if since:
            params["since"] = since
        page = 1
        while True:
            params["page"] = page
            issues = _rest("GET", f"/repos/{owner}/{repo}/issues", params=params)
            if not issues:
                break
            for issue in issues:
                if issue.get("pull_request"):
                    continue  # skip PRs
                stats["changed_issues"] += 1
                try:
                    result = _apply_issue(issue, board)
                    _count_outcome(stats, result.get("outcome"))
                    details["issues"].append(result)
                except Exception as exc:
                    stats["error_count"] += 1
                    tb = frappe.get_traceback()
                    details["issues"].append(
                        {
                            "outcome": "failed",
                            "issue_number": issue.get("number"),
                            "error": str(exc),
                            "traceback": tb,
                        }
                    )
                    frappe.log_error(tb, "github_sync.apply_issue")
            if len(issues) < 100:
                break
            page += 1
        reconcile = _reconcile_board_status(board)
        details["board_reconcile"] = reconcile["details"]
        stats["updated_count"] += reconcile["counts"].get("status_updated", 0)
        summary = f"{now_datetime():%Y-%m-%d %H:%M} · {_sync_summary(stats)}"
        status = "Partial Failure" if stats["error_count"] else "Success"
        if stats["error_count"]:
            _set_last_pull_status(summary)
        else:
            _set_cursor(started.strftime("%Y-%m-%dT%H:%M:%SZ"), summary)
        _finish_sync_log(log_name, status, summary, stats=stats, details=details)
        return {**stats, "status": status, "log_name": log_name}
    except Exception:
        tb = frappe.get_traceback()
        summary = "GitHub pull failed before issue processing completed."
        _finish_sync_log(log_name, "Failed", summary, stats=stats, details=details, traceback=tb)
        frappe.log_error(tb, "github_sync.pull")
        return {**stats, "status": "Failed", "log_name": log_name, "error": tb}
    finally:
        frappe.flags.in_github_sync = False


def retry_issue(issue_number):
    """Pull one GitHub issue into Helpdesk and write an audit log."""
    log_name = _start_sync_log("Retry Issue")
    stats = _empty_sync_stats()
    details = {"issues": []}
    if not _enabled():
        summary = "GitHub retry skipped because sync is disabled."
        _finish_sync_log(log_name, "Skipped", summary, details={"reason": "disabled"})
        return {"skipped": "disabled", "log_name": log_name}
    if not _has_auth():
        summary = "GitHub retry skipped because authentication is not configured."
        _finish_sync_log(log_name, "Skipped", summary, details={"reason": "no auth"})
        return {"skipped": "no auth", "log_name": log_name}

    owner, repo = _owner_repo()
    frappe.flags.in_github_sync = True
    try:
        board = fetch_board()
        stats["board_items"] = len(board)
        issue = _rest("GET", f"/repos/{owner}/{repo}/issues/{int(issue_number)}")
        if issue.get("pull_request"):
            result = {"outcome": "skipped_pull_request", "issue_number": issue.get("number")}
            stats["skipped_count"] += 1
        else:
            stats["changed_issues"] = 1
            result = _apply_issue(issue, board)
            _count_outcome(stats, result.get("outcome"))
        details["issues"].append(result)
        summary = _sync_summary(stats)
        status = "Success" if not stats["error_count"] else "Partial Failure"
        _finish_sync_log(log_name, status, summary, stats=stats, details=details)
        return {**stats, "status": status, "log_name": log_name, "result": result}
    except Exception:
        tb = frappe.get_traceback()
        stats["error_count"] += 1
        summary = f"Retry issue #{issue_number} failed."
        _finish_sync_log(log_name, "Failed", summary, stats=stats, details=details, traceback=tb)
        frappe.log_error(tb, "github_sync.retry_issue")
        return {**stats, "status": "Failed", "log_name": log_name, "error": tb}
    finally:
        frappe.flags.in_github_sync = False


# ------------------------------------------------------- escalation (Helpdesk -> GitHub, manual)
def _add_issue_to_board(content_node_id):
    """Add a freshly created issue to Project #6; return the new board item id."""
    if not content_node_id:
        return None
    mutation = """
    mutation($proj:ID!, $content:ID!){
      addProjectV2ItemById(input:{ projectId:$proj, contentId:$content }){ item { id } }
    }"""
    try:
        d = _graphql(mutation, {"proj": _project_id(), "content": content_node_id})
        return d["addProjectV2ItemById"]["item"]["id"]
    except Exception:
        frappe.log_error(frappe.get_traceback(), "github_sync.add_to_board")
        return None


@frappe.whitelist()
def escalate_to_github(ticket: str) -> dict:
    """Manually hand a Helpdesk ticket off to GitHub: create one issue, add it to the
    board, and link it back. Agent-only and one-shot — there is no further push; once
    linked, the issue tracks dev work and the result flows back via the scheduled pull.
    """
    if not frappe.db.exists("HD Ticket", ticket):
        frappe.throw(_("Ticket not found."))
    if not frappe.has_permission("HD Ticket", "write", doc=ticket):
        frappe.throw(_("You are not permitted to escalate this ticket to GitHub."))
    if not _enabled() or not _has_auth():
        frappe.throw(_("GitHub sync is disabled or not authenticated."))

    doc = frappe.get_doc("HD Ticket", ticket)
    if getattr(doc, "github_issue_number", None):
        return {
            "data": {"issue_number": doc.github_issue_number, "url": doc.github_url},
            "message": f"Ticket is already linked to GitHub issue #{doc.github_issue_number}.",
        }

    owner, repo = _owner_repo()
    title = (doc.subject or f"HD Ticket {doc.name}")[:250]
    body = _html_to_text(doc.description or "")
    body += f"\n\n_— escalated from Helpdesk ticket {doc.name}_"
    try:
        res = _rest("POST", f"/repos/{owner}/{repo}/issues", json={"title": title, "body": body})
    except Exception:
        frappe.log_error(frappe.get_traceback(), "github_sync.escalate_to_github")
        frappe.throw(_("Failed to create the GitHub issue. See the error log for details."))

    number = res.get("number")
    if not number:
        frappe.throw(_("GitHub did not return an issue number; nothing was linked."))
    item_id = _add_issue_to_board(res.get("node_id"))
    frappe.db.set_value(
        "HD Ticket",
        doc.name,
        {
            "sync_to_github": 1,
            "github_issue_number": number,
            "github_url": res.get("html_url"),
            "github_project_item_id": item_id,
            "github_last_synced": now_datetime(),
        },
        update_modified=False,
    )
    return {
        "data": {"issue_number": number, "url": res.get("html_url"), "ticket": doc.name},
        "message": f"Escalated to GitHub issue #{number}.",
    }


# -------------------------------------------------------------------------------- setup
def _custom_field(dt, fieldname, spec):
    if frappe.db.exists("Custom Field", f"{dt}-{fieldname}"):
        return False
    frappe.get_doc(
        {
            "doctype": "Custom Field",
            "dt": dt,
            "fieldname": fieldname,
            "module": "Connect Diagnostics Core",
            **spec,
        }
    ).insert(ignore_permissions=True)
    return True


def ensure_ticket_fields():
    """Custom fields on HD Ticket / HD Ticket Comment (idempotent)."""
    result = {"created": [], "existing": [], "skipped_doctypes": []}
    if not _doctype_exists("HD Ticket"):
        result["skipped_doctypes"].append("HD Ticket")
    else:
        specs = {
            "github_section": {
                "label": "GitHub",
                "fieldtype": "Section Break",
                "insert_after": "key",
                "collapsible": 1,
            },
            "sync_to_github": {
                "label": "Sync to GitHub",
                "fieldtype": "Check",
                "default": "0",
                "insert_after": "github_section",
                "description": "When on, this ticket syncs with GitHub. If it has no issue yet, "
                "the next save creates a GitHub issue and adds it to the board.",
            },
            "github_issue_number": {
                "label": "GitHub Issue #",
                "fieldtype": "Int",
                "insert_after": "sync_to_github",
                "read_only": 1,
                "no_copy": 1,
                "in_standard_filter": 1,
            },
            "github_url": {
                "label": "GitHub URL",
                "fieldtype": "Data",
                "options": "URL",
                "insert_after": "github_issue_number",
                "read_only": 1,
                "no_copy": 1,
            },
            "github_col": {"fieldtype": "Column Break", "insert_after": "github_url"},
            "github_last_synced": {
                "label": "GitHub Last Synced",
                "fieldtype": "Datetime",
                "insert_after": "github_col",
                "read_only": 1,
                "no_copy": 1,
            },
            "github_project_item_id": {
                "label": "GitHub Project Item ID",
                "fieldtype": "Data",
                "insert_after": "github_last_synced",
                "read_only": 1,
                "no_copy": 1,
                "hidden": 1,
            },
        }
        for fieldname, spec in specs.items():
            key = f"HD Ticket.{fieldname}"
            if _custom_field("HD Ticket", fieldname, spec):
                result["created"].append(key)
            else:
                result["existing"].append(key)
        frappe.clear_cache(doctype="HD Ticket")
    return result


def ensure_ticket_template_fields():
    """Expose GitHub fields in the Helpdesk agent UI's Default ticket template."""
    result = {"created": [], "existing": [], "skipped": []}
    required_doctypes = ("HD Ticket Template", "HD Ticket Template Field")
    missing_doctypes = [doctype for doctype in required_doctypes if not _doctype_exists(doctype)]
    if missing_doctypes:
        result["skipped"].extend(missing_doctypes)
        return result

    if not frappe.db.exists("HD Ticket Template", DEFAULT_HELPDESK_TEMPLATE):
        frappe.get_doc({"doctype": "HD Ticket Template", "template_name": DEFAULT_HELPDESK_TEMPLATE}).insert(
            ignore_permissions=True
        )

    doc = frappe.get_doc("HD Ticket Template", DEFAULT_HELPDESK_TEMPLATE)
    existing = {row.fieldname for row in (doc.get("fields") or [])}
    for row in DEFAULT_HELPDESK_TEMPLATE_FIELDS:
        fieldname = row["fieldname"]
        if fieldname in existing:
            result["existing"].append(fieldname)
            continue
        doc.append(
            "fields",
            {
                "fieldname": fieldname,
                "placeholder": row.get("placeholder"),
                "hide_from_customer": 1,
            },
        )
        result["created"].append(fieldname)
    if result["created"]:
        doc.save(ignore_permissions=True)
    return result


def init_settings():
    """Populate the GitHub Helpdesk Sync Settings single from site_config + live board metadata."""
    s = frappe.get_single(SETTINGS)
    if frappe.conf.get("github_owner"):
        s.github_owner = frappe.conf.get("github_owner")
    if frappe.conf.get("github_repo"):
        s.github_repo = frappe.conf.get("github_repo")
    if frappe.conf.get("github_token") and not s.github_token:
        s.github_token = frappe.conf.get("github_token")
    if not s.last_pull:
        s.last_pull = frappe.db.get_default("github_last_pull") or now_datetime().strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )
    s.save(ignore_permissions=True)
    meta = refresh_project_metadata()
    s.reload()
    return {"options": meta["options"], "owner": s.github_owner, "repo": s.github_repo}


def setup():
    """One-off: create custom fields, link (and mark synced) the already-imported tickets,
    and arm the incremental cursor so the first scheduled pull only sees new changes."""
    ensure_ticket_fields()

    board = fetch_board()
    owner, repo = _owner_repo()
    linked = 0
    for t in frappe.get_all("HD Ticket", fields=["name", "subject"], limit_page_length=0):
        m = re.match(r"#(\d+):", t.subject or "")
        if not m:
            continue
        n = int(m.group(1))
        frappe.db.set_value(
            "HD Ticket",
            t.name,
            {
                "sync_to_github": 1,
                "github_issue_number": n,
                "github_url": f"https://github.com/{owner}/{repo}/issues/{n}",
                "github_project_item_id": (board.get(n) or {}).get("item_id"),
            },
            update_modified=False,
        )
        linked += 1

    frappe.db.set_default("github_last_pull", now_datetime().strftime("%Y-%m-%dT%H:%M:%SZ"))
    return {"linked_tickets": linked, "board_items": len(board)}


def _create_ticket_from_issue(issue, board):
    """Create one HD Ticket from a GitHub issue (REST shape). Bootstrap only — the
    scheduled pull is update-only and never creates tickets."""
    n = issue["number"]
    labels = [l["name"] for l in issue.get("labels", [])]
    b = board.get(n) or {}
    if issue["state"] == "closed":
        status = _resolved_status()
    elif b.get("status"):
        status = b["status"]
        ensure_board_status(status)
    else:
        status = "Open"
    prio = b.get("priority") or _label_priority(labels) or "Medium"
    ttype = _ticket_type(b.get("issue_type"), labels)
    assignees = _users_for_logins(b.get("assignees"))
    author = (issue.get("user") or {}).get("login") or "ghost"
    subject = f"#{n}: {issue.get('title') or ''}"[:140]
    meta = f"GitHub Issue [#{n}]({issue['html_url']}) · author @{author}"
    if b.get("module"):
        meta += f" · module: {b['module']}"
    if labels:
        meta += f" · labels: {', '.join(labels)}"
    description = md_to_html(meta + "\n\n---\n\n" + (issue.get("body") or ""))

    doc = frappe.new_doc("HD Ticket")
    doc.subject = subject  # ty:ignore[unresolved-attribute] - Helpdesk doctype
    doc.description = description  # ty:ignore[unresolved-attribute] - Helpdesk doctype
    doc.priority = prio  # ty:ignore[unresolved-attribute] - Helpdesk doctype
    doc.ticket_type = ttype  # ty:ignore[unresolved-attribute] - Helpdesk doctype
    doc.sync_to_github = 1  # ty:ignore[unresolved-attribute] - custom field
    doc.raised_by = f"{author}@users.noreply.github.com"  # ty:ignore[unresolved-attribute] - Helpdesk doctype
    doc.github_issue_number = n  # ty:ignore[unresolved-attribute] - custom field
    doc.github_url = issue["html_url"]  # ty:ignore[unresolved-attribute] - custom field
    doc.github_project_item_id = b.get("item_id")  # ty:ignore[unresolved-attribute] - custom field
    doc.github_last_synced = now_datetime()  # ty:ignore[unresolved-attribute] - custom field
    doc.insert(ignore_permissions=True)
    name = doc.name
    # HD Ticket forces status=Open on insert (and the auto Communication re-triggers it),
    # so set the real status AFTER insert; backdate creation to the issue's createdAt.
    frappe.db.set_value(
        "HD Ticket",
        name,
        {
            "status": status,
            "status_category": _status_category(status),
            "creation": get_datetime(issue["created_at"]),
        },
        update_modified=False,
    )
    # private-repo image attachments only become re-hostable once the ticket exists
    new_desc, rehosted = _rehost_github_images(description, name)
    if rehosted:
        frappe.db.set_value("HD Ticket", name, "description", new_desc, update_modified=False)
    _assign_ticket(name, assignees)
    return name


def import_from_github(commit=False):
    """One-off bootstrap: create HD Tickets for GitHub issues that have none yet.

    The scheduled pull is update-only and never creates tickets; this seeds the
    historical backlog once. Idempotent — issues already linked to a ticket are skipped.
    Dry-run by default; pass commit=True to actually write.
    """
    if not _has_auth():
        return {"error": "GitHub authentication is not configured."}
    owner, repo = _owner_repo()
    board = fetch_board()
    created, skipped, errors = [], [], []
    frappe.flags.in_github_sync = True
    frappe.flags.initial_sync = True  # suppress acknowledgement emails to synthetic raised_by
    try:
        page = 1
        params = {"state": "all", "per_page": 100, "sort": "created", "direction": "asc"}
        while True:
            params["page"] = page
            issues = _rest("GET", f"/repos/{owner}/{repo}/issues", params=params)
            if not issues:
                break
            for issue in issues:
                if issue.get("pull_request"):
                    continue
                n = issue["number"]
                if _ticket_for_issue(n):
                    skipped.append(n)
                    continue
                if not commit:
                    created.append(n)
                    continue
                try:
                    name = _create_ticket_from_issue(issue, board)
                    created.append({"issue": n, "ticket": name})
                except Exception:
                    errors.append(n)
                    frappe.log_error(frappe.get_traceback(), "github_sync.import_from_github")
            if len(issues) < 100:
                break
            page += 1
        if commit:
            # arm the cursor so the next scheduled pull only reconciles changes after the seed
            _set_cursor(now_datetime().strftime("%Y-%m-%dT%H:%M:%SZ"), "bootstrap import")
            # one-off bootstrap run via bench execute: persist the seeded backlog + cursor so a
            # later failure does not roll back tickets already created
            frappe.db.commit()  # nosemgrep: frappe-manual-commit
    finally:
        frappe.flags.in_github_sync = False
        frappe.flags.initial_sync = False
    return {
        "commit": commit,
        "created": len(created),
        "skipped": len(skipped),
        "errors": len(errors),
        "board_items": len(board),
        "sample": created[:5],
        "error_issues": errors[:10],
    }


def rehost_images(commit=False):
    """Re-host private GitHub attachment images in existing ticket descriptions to Frappe.

    Covers tickets created before image re-hosting existed (or whose earlier download
    failed). Idempotent — already-rehosted images are reused, not re-downloaded.
    Dry-run by default; pass commit=True to write.
    """
    if not _has_auth():
        return {"error": "GitHub authentication is not configured."}
    tickets = frappe.get_all(
        "HD Ticket",
        filters={"description": ["like", f"%{_GH_ASSET_MARKER}%"]},
        fields=["name", "description"],
        limit_page_length=0,
    )
    updated, images = 0, 0
    frappe.flags.in_github_sync = True
    try:
        for t in tickets:
            if not commit:
                images += len(_GH_IMG_SRC_RE.findall(t.description or ""))
                updated += 1
                continue
            new_html, n = _rehost_github_images(t.description, t.name)
            if n:
                frappe.db.set_value("HD Ticket", t.name, "description", new_html, update_modified=False)
                updated += 1
                images += n
        if commit:
            # one-off backfill run via bench execute / settings button: persist rewritten bodies
            frappe.db.commit()  # nosemgrep: frappe-manual-commit
    finally:
        frappe.flags.in_github_sync = False
    return {"commit": commit, "tickets": updated, "images": images}
