"""
Two-way (near-realtime) sync between a GitHub repo/Project board and Frappe Helpdesk.

Direction overview
------------------
GitHub -> Helpdesk  (pull, scheduled every 10 min)
  * new / updated issues          -> upsert HD Ticket (subject "#<n>: title")
  * issue comments                -> HD Ticket Comment (deduped by github_comment_id)
  * Project #6 board column        -> HD Ticket.status (reconciled for ALL tickets every run,
                                     because moving a card does NOT bump issue.updated_at)

Helpdesk -> GitHub  (push, on doc events)
  * new agent HD Ticket Comment   -> GitHub issue comment      (needs `repo` scope)
  * ticket status == "Closed"      -> close issue / reopen      (needs `repo` scope)
  * ticket status == board column  -> move card on the board    (needs `project` write scope)

Loop prevention
---------------
  * pull runs with frappe.flags.in_github_sync = True; push handlers no-op while it is set.
  * comments carry github_comment_id both ways, so neither side re-imports its own echo.

Config lives in site_config.json: github_token, github_owner, github_repo.
"""

import json
import os
import re
import shutil
import subprocess
from urllib.parse import urlencode

import frappe
import requests
from frappe.utils import get_datetime, md_to_html, now_datetime

API = "https://api.github.com"
GRAPHQL = "https://api.github.com/graphql"

# --- GitHub Project v2 (board) metadata for Shinonn23/connect_diagnostics_core #6 ---
PROJECT_ID = "PVT_kwHOB1tcMM4BLM7I"
STATUS_FIELD_ID = "PVTSSF_lAHOB1tcMM4BLM7Izg62NJg"
STATUS_OPTION_IDS = {
    "TODO": "f75ad846",
    "Dev In progress": "47fc9ee4",
    "Test In progress": "18955566",
    "Hold": "232c6587",
    "Dev review": "df73e18b",
    "DEV Ready": "61e4505c",
    "Test Review": "6c769416",
    "UAT Deploy": "98236657",
    "PROD Deploy": "dba9dd7f",
}
# board column -> HD Ticket Status category
BOARD_CATEGORY = {
    "TODO": "Open",
    "DEV Ready": "Open",
    "Dev In progress": "Open",
    "Test In progress": "Open",
    "Test Review": "Open",
    "Dev review": "Open",
    "UAT Deploy": "Resolved",
    "PROD Deploy": "Resolved",
    "Hold": "Paused",
}
BOARD_COLOR = {
    "TODO": "Gray",
    "DEV Ready": "Cyan",
    "Dev In progress": "Blue",
    "Test In progress": "Violet",
    "Test Review": "Amber",
    "Dev review": "Pink",
    "UAT Deploy": "Green",
    "PROD Deploy": "Teal",
    "Hold": "Orange",
}


# ----------------------------------------------------------------------------- helpers
SETTINGS = "GitHub Integration Settings"


def _settings():
    """Return the GitHub Integration Settings single doc, or None if not installed yet."""
    if not frappe.db.exists("DocType", SETTINGS):
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
    return bool(s.get(field))


def _owner_repo():
    return _cfg("github_owner", "Shinonn23"), _cfg("github_repo", "connect_diagnostics_core")


def _project_id():
    return _cfg("project_id", PROJECT_ID)


def _status_field_id():
    return _cfg("status_field_id", STATUS_FIELD_ID)


def _status_option_ids():
    """board_column -> option_id, from settings mappings if present else module constants."""
    s = _settings()
    if s is not None and s.status_mappings:
        m = {r.board_column: r.option_id for r in s.status_mappings if r.option_id}
        if m:
            return m
    return STATUS_OPTION_IDS


def _board_category(label):
    s = _settings()
    if s is not None and s.status_mappings:
        for r in s.status_mappings:
            if r.board_column == label and r.category:
                return r.category
    return BOARD_CATEGORY.get(label, "Open")


def _headers():
    return {
        "Authorization": f"Bearer {_cfg('github_token')}",
        "Accept": "application/vnd.github+json",
    }


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


def _html_to_text(html):
    """Best-effort HTML -> plain text for outgoing GitHub comments (no html2text dep)."""
    try:
        from bs4 import BeautifulSoup

        return BeautifulSoup(html or "", "html.parser").get_text("\n").strip()
    except Exception:
        return html or ""


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
            "color": BOARD_COLOR.get(label, "Gray"),
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
            content{ ... on Issue { number } }
            status:  fieldValueByName(name:"Status"){   ... on ProjectV2ItemFieldSingleSelectValue { name } }
            priority:fieldValueByName(name:"Priority"){ ... on ProjectV2ItemFieldSingleSelectValue { name } }
            module:  fieldValueByName(name:"Module"){   ... on ProjectV2ItemFieldSingleSelectValue { name } }
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
                "status": (it.get("status") or {}).get("name"),
                "priority": (it.get("priority") or {}).get("name"),
                "module": (it.get("module") or {}).get("name"),
            }
        if not items["pageInfo"]["hasNextPage"]:
            break
        cursor = items["pageInfo"]["endCursor"]
    return out


def fetch_project_metadata():
    """Resolve project node id, Status field id and its option ids from project_number."""
    owner, _ = _owner_repo()
    number = int(_cfg("project_number", 6))
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
    """Create or update one HD Ticket from a GitHub issue dict (REST shape)."""
    n = issue["number"]
    labels = [l["name"] for l in issue.get("labels", [])]
    b = board.get(n) or {}
    bstatus = b.get("status")
    if bstatus:
        ensure_board_status(bstatus)
        status = bstatus
    else:
        status = "Open" if issue["state"] == "open" else "Closed"
    prio = b.get("priority") or _label_priority(labels) or "Medium"
    ttype = "Bug" if any("bug" in l.lower() for l in labels) else "Unspecified"
    author = (issue.get("user") or {}).get("login") or "ghost"
    subject = f"#{n}: {issue.get('title') or ''}"[:140]
    meta = f"GitHub Issue [#{n}]({issue['html_url']}) · author @{author}"
    if b.get("module"):
        meta += f" · module: {b['module']}"
    if labels:
        meta += f" · labels: {', '.join(labels)}"
    description = md_to_html(meta + "\n\n---\n\n" + (issue.get("body") or ""))
    cat = (
        _board_category(status)
        if status in _status_option_ids()
        else frappe.db.get_value("HD Ticket Status", status, "category")
    )

    name = _ticket_for_issue(n)
    if name:
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
            "HD Ticket", name, {"status": status, "status_category": cat}, update_modified=False
        )
    else:
        doc = frappe.new_doc("HD Ticket")
        doc.subject = subject
        doc.description = description
        doc.priority = prio
        doc.ticket_type = ttype
        doc.raised_by = f"{author}@users.noreply.github.com"
        doc.github_issue_number = n
        doc.github_url = issue["html_url"]
        doc.github_project_item_id = b.get("item_id")
        doc.github_last_synced = now_datetime()
        doc.insert(ignore_permissions=True)
        name = doc.name
        frappe.db.set_value(
            "HD Ticket",
            name,
            {"status": status, "status_category": cat, "creation": get_datetime(issue["created_at"])},
            update_modified=False,
        )
    _sync_comments(name, n)
    return name


def _sync_comments(ticket, number):
    owner, repo = _owner_repo()
    existing = set(
        frappe.get_all(
            "HD Ticket Comment",
            filters={"reference_ticket": ticket, "github_comment_id": ["is", "set"]},
            pluck="github_comment_id",
        )
    )
    page = 1
    while True:
        comments = _rest(
            "GET", f"/repos/{owner}/{repo}/issues/{number}/comments", params={"per_page": 100, "page": page}
        )
        if not comments:
            break
        for c in comments:
            cid = str(c["id"])
            if cid in existing:
                continue
            ca = (c.get("user") or {}).get("login") or "ghost"
            cm = frappe.new_doc("HD Ticket Comment")
            cm.reference_ticket = ticket
            cm.github_comment_id = cid
            cm.content = md_to_html(
                f"**@{ca}** · {(c.get('created_at') or '')[:10]}\n\n" + (c.get("body") or "")
            )
            cm.insert(ignore_permissions=True)
        if len(comments) < 100:
            break
        page += 1


def _reconcile_board_status(board):
    """Board moves don't touch issue.updated_at, so realign every ticket's status here."""
    for n, b in board.items():
        status = b.get("status")
        if not status:
            continue
        name = _ticket_for_issue(n)
        if not name:
            continue
        cur = frappe.db.get_value("HD Ticket", name, "status")
        if cur != status:
            ensure_board_status(status)
            frappe.db.set_value(
                "HD Ticket",
                name,
                {
                    "status": status,
                    "status_category": _board_category(status),
                    "github_project_item_id": b.get("item_id"),
                },
                update_modified=False,
            )


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


def pull():
    """Scheduled entrypoint: pull GitHub -> Helpdesk."""
    if not _enabled() or not _toggle("pull_enabled", True):
        return {"skipped": "disabled"}
    if not _has_auth():
        frappe.log_error("github_sync: no GitHub auth (gh login or token)", "github_sync")
        return {"skipped": "no auth"}
    owner, repo = _owner_repo()
    frappe.flags.in_github_sync = True
    started = now_datetime()
    try:
        board = fetch_board()
        since = _get_cursor()
        params = {"state": "all", "per_page": 100, "sort": "updated", "direction": "asc"}
        if since:
            params["since"] = since
        page, changed = 1, 0
        while True:
            params["page"] = page
            issues = _rest("GET", f"/repos/{owner}/{repo}/issues", params=params)
            if not issues:
                break
            for issue in issues:
                if issue.get("pull_request"):
                    continue  # skip PRs
                _apply_issue(issue, board)
                changed += 1
            if len(issues) < 100:
                break
            page += 1
        _reconcile_board_status(board)
        _set_cursor(
            started.strftime("%Y-%m-%dT%H:%M:%SZ"),
            f"{now_datetime():%Y-%m-%d %H:%M} · {changed} changed issue(s), {len(board)} board items",
        )
        return {"changed_issues": changed, "board_items": len(board)}
    finally:
        frappe.flags.in_github_sync = False


# --------------------------------------------------------------------------------- push
def _push_enabled():
    return _enabled() and _has_auth() and not _cfg("github_sync_push_disabled")


def _agent_signature(doc):
    """'[Helpdesk] Full Name (email):' header for outgoing comments, per settings."""
    s = _settings()
    if s is not None and s.comment_attribution == "Token owner only":
        return ""
    user = getattr(doc, "commented_by", None) or doc.owner
    full_name = frappe.db.get_value("User", user, "full_name") or user
    label = full_name if not user or user == full_name else f"{full_name} ({user})"
    return f"**[Helpdesk] {label}:**\n\n"


def push_comment(doc, method=None):
    """HD Ticket Comment after_insert -> GitHub issue comment."""
    if frappe.flags.in_github_sync or not _push_enabled() or not _toggle("push_comments", True):
        return
    if getattr(doc, "github_comment_id", None):
        return
    number = frappe.db.get_value("HD Ticket", doc.reference_ticket, "github_issue_number")
    if not number:
        return
    owner, repo = _owner_repo()
    body = _agent_signature(doc) + _html_to_text(doc.content or "")
    body += f"\n\n_— synced from Helpdesk ticket {doc.reference_ticket}_"
    try:
        res = _rest("POST", f"/repos/{owner}/{repo}/issues/{number}/comments", json={"body": body})
        # store id so the next pull treats it as already-synced
        frappe.db.set_value(
            "HD Ticket Comment", doc.name, "github_comment_id", str(res["id"]), update_modified=False
        )
    except Exception:
        frappe.log_error(frappe.get_traceback(), "github_sync.push_comment")


def push_ticket(doc, method=None):
    """HD Ticket on_update -> push status (board column) and open/closed state."""
    if frappe.flags.in_github_sync or not _push_enabled():
        return
    number = getattr(doc, "github_issue_number", None)
    if not number:
        return
    before = doc.get_doc_before_save()
    if before and before.status == doc.status:
        return  # only react to status changes
    owner, repo = _owner_repo()

    # 1) issue open/closed: only "Closed" closes the GitHub issue
    if _toggle("push_close_state", True):
        try:
            want_state = "closed" if doc.status == "Closed" else "open"
            cur = _rest("GET", f"/repos/{owner}/{repo}/issues/{number}").get("state")
            if cur != want_state:
                _rest("PATCH", f"/repos/{owner}/{repo}/issues/{number}", json={"state": want_state})
        except Exception:
            frappe.log_error(frappe.get_traceback(), "github_sync.push_ticket.state")

    # 2) board column: requires `project` (write) scope on the token
    option_id = _status_option_ids().get(doc.status)
    item_id = getattr(doc, "github_project_item_id", None)
    if _toggle("push_status_to_board", False) and option_id and item_id:
        mutation = """
        mutation($proj:ID!, $item:ID!, $field:ID!, $opt:String!){
          updateProjectV2ItemFieldValue(input:{
            projectId:$proj, itemId:$item, fieldId:$field,
            value:{ singleSelectOptionId:$opt }
          }){ projectV2Item { id } }
        }"""
        try:
            _graphql(
                mutation,
                {"proj": _project_id(), "item": item_id, "field": _status_field_id(), "opt": option_id},
            )
        except Exception:
            # most likely: token lacks `project` write scope — log once, don't raise
            frappe.log_error(frappe.get_traceback(), "github_sync.push_ticket.board")


# -------------------------------------------------------------------------------- setup
def _custom_field(dt, fieldname, spec):
    if frappe.db.exists("Custom Field", f"{dt}-{fieldname}"):
        return
    frappe.get_doc(
        {
            "doctype": "Custom Field",
            "dt": dt,
            "fieldname": fieldname,
            "module": "Connect Diagnostics Core",
            **spec,
        }
    ).insert(ignore_permissions=True)


def ensure_ticket_fields():
    """Custom fields on HD Ticket / HD Ticket Comment (idempotent)."""
    _custom_field(
        "HD Ticket",
        "github_section",
        {"label": "GitHub", "fieldtype": "Section Break", "insert_after": "key", "collapsible": 1},
    )
    _custom_field(
        "HD Ticket",
        "github_issue_number",
        {
            "label": "GitHub Issue #",
            "fieldtype": "Int",
            "insert_after": "github_section",
            "read_only": 1,
            "no_copy": 1,
            "in_standard_filter": 1,
        },
    )
    _custom_field(
        "HD Ticket",
        "github_url",
        {
            "label": "GitHub URL",
            "fieldtype": "Data",
            "options": "URL",
            "insert_after": "github_issue_number",
            "read_only": 1,
            "no_copy": 1,
        },
    )
    _custom_field("HD Ticket", "github_col", {"fieldtype": "Column Break", "insert_after": "github_url"})
    _custom_field(
        "HD Ticket",
        "github_last_synced",
        {
            "label": "GitHub Last Synced",
            "fieldtype": "Datetime",
            "insert_after": "github_col",
            "read_only": 1,
            "no_copy": 1,
        },
    )
    _custom_field(
        "HD Ticket",
        "github_project_item_id",
        {
            "label": "GitHub Project Item ID",
            "fieldtype": "Data",
            "insert_after": "github_last_synced",
            "read_only": 1,
            "no_copy": 1,
            "hidden": 1,
        },
    )
    _custom_field(
        "HD Ticket Comment",
        "github_comment_id",
        {
            "label": "GitHub Comment ID",
            "fieldtype": "Data",
            "insert_after": "is_pinned",
            "read_only": 1,
            "no_copy": 1,
            "hidden": 1,
        },
    )
    frappe.clear_cache(doctype="HD Ticket")
    frappe.clear_cache(doctype="HD Ticket Comment")


def init_settings():
    """Populate the GitHub Integration Settings single from site_config + live board metadata."""
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
    # board metadata + status mappings
    meta = fetch_project_metadata()
    s.reload()
    s.project_id = meta["project_id"]
    s.status_field_id = meta["status_field_id"]
    s.status_mappings = []
    for name, option_id in meta["options"].items():
        s.append(
            "status_mappings",
            {
                "board_column": name,
                "option_id": option_id,
                "hd_status": name if frappe.db.exists("HD Ticket Status", name) else None,
                "category": BOARD_CATEGORY.get(name, "Open"),
            },
        )
    s.save(ignore_permissions=True)
    return {"options": len(meta["options"]), "owner": s.github_owner, "repo": s.github_repo}


def setup(backfill_comment_ids=True):
    """One-off: create custom fields, backfill links on the already-imported tickets,
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
                "github_issue_number": n,
                "github_url": f"https://github.com/{owner}/{repo}/issues/{n}",
                "github_project_item_id": (board.get(n) or {}).get("item_id"),
            },
            update_modified=False,
        )
        linked += 1

        if backfill_comment_ids:
            local = frappe.get_all(
                "HD Ticket Comment",
                filters={"reference_ticket": t.name},
                fields=["name"],
                order_by="creation asc",
            )
            if not local:
                continue
            gh = _rest("GET", f"/repos/{owner}/{repo}/issues/{n}/comments", params={"per_page": 100})
            for lc, gc in zip(local, gh, strict=False):
                frappe.db.set_value(
                    "HD Ticket Comment", lc.name, "github_comment_id", str(gc["id"]), update_modified=False
                )

    frappe.db.set_default("github_last_pull", now_datetime().strftime("%Y-%m-%dT%H:%M:%SZ"))
    return {"linked_tickets": linked, "board_items": len(board)}
