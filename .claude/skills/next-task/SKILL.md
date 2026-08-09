---
name: next-task
description: Recommend which Notion Task Tracker task to work on next, ranked by priority and due date and reality-checked against the repo so already-delivered work is not handed back as new. Use when the user asks what to do next, what is left, or which task to pick up.
---

# Next Task

Read the Notion **Task Tracker** and recommend what to work on. Recommend only —
claiming a task is `/take-task`. Database and property IDs are in the Notion
Task Tracker reference below.

## Input

`/next-task [keyword|workstream]` — the optional argument narrows candidates by
Task title, Workstream, or Tags.

## Steps

1. **Resolve identity.** Call the Notion MCP `fetch` tool with the literal id
   `self` to get the authenticated user id. Use it only to mark which rows are
   already assigned to the user; do not filter the board down to them.
2. **Pull candidates — narrow columns first.** The board carries 260+ rows and
   umbrella tasks hold `Sub-item` arrays of 30-40 URLs, so never select the
   relation columns across the whole board. Scan light:
   ```sql
   SELECT "Task ID", "Task", "Status", "Priority", "date:Due Date:start",
          "Workstream", "Work Type", "Dependencies",
          ("Sub-item" IS NOT NULL) AS has_children,
          ("Assignee" IS NOT NULL) AS is_assigned, url
   FROM "collection://bcd5f7fa-c9c1-43dc-bfd7-c30272a1d100"
   WHERE "Status" NOT IN ('Done', 'Cancelled')
   ORDER BY "date:Due Date:start"
   ```
   Apply the argument as an extra `LIKE` filter on `Task`, `Workstream`, or
   `Tags`. `Task ID` is the auto-increment number shown as `TSK-<n>`. Only after
   shortlisting, pull `Assignee`, `Sub-item`, `Latest Update`, and
   `Acceptance Criteria` for those few rows.
3. **Rank.** In order:
   - **Finish before starting** — rows already `In progress` or `In review` outrank
     anything not started.
   - **Overdue**, then **due soonest**, using `date:Due Date:start` against today.
     Most rows have no due date — those sort *after* dated rows of the same
     priority, never first.
   - **Priority** `🔴 Critical` → `🟠 High` → `🟡 Medium` → `🟢 Low`.

   Push down, and say why in the report:
   - rows whose `Dependencies` name work that is not finished;
   - umbrella rows that still have open `Sub-item` children — recommend a child;
   - `Work Type` = `Testing` and any row whose Acceptance Criteria needs a human or
     physical step (printing on a real printer, a tester's sign-off). Code cannot
     advance those, so they are not "next" for a coding session.
4. **Reality-check the top five against the repo.** For each, search for the
   feature it names: `git log --oneline --all -- <path>`, `rg <term>`,
   `gh pr list --state all --search "<term>"`. The board goes stale optimistically
   — nine print formats sat at `Not started` while they had shipped releases
   earlier. Report any such row as **needs verification, not implementation**, and
   rank it below genuinely unstarted work.
5. **Report and stop.** Never write to Notion in this skill.

## Output

A ranked table of three to five rows — `TSK-<n>`, title, Priority, Due,
why it is next, what blocks it — with rows already assigned to the user marked.
Call out separately any row that looks already delivered, and any that needs a
human rather than code. End by pointing at `/take-task TSK-<n>`.

## Notion Task Tracker reference

- Database **Task Tracker** `4c1c5f86101c46d18557190f96aa9aab`, under the page
  *ERPNext Connect Diagnostics*; tasks are `TSK-<Task ID>`.
- Data source `collection://bcd5f7fa-c9c1-43dc-bfd7-c30272a1d100` — use this string as
  the SQL table name. All Tasks view `view://320d5160-c409-40a4-87e2-b0f6962bf6ae`.
- **Status**: `Not started` · `Backlog` · `In progress` · `In review` · `Done` · `Cancelled`
- **Priority**: `🔴 Critical` · `🟠 High` · `🟡 Medium` · `🟢 Low`
- **Work Type**: `Requirement` · `Design` · `Development` · `Configuration` · `Data Migration` · `Testing` · `Documentation`
- `Related User Tickets` relates to `collection://e73aded7-efef-4426-b312-0dc4d0e6047a`.
- Write quirks that silently fail if ignored: `Task ID` is `auto_increment_id` and
  read-only; dates split into `date:<Name>:start` / `:end` / `:is_datetime`; `Assignee`
  is an array of user IDs; checkboxes use `__YES__` / `__NO__`.
- Tools are the Notion MCP `fetch`, `query-data-sources`, and `update-page`
  (`command: update_properties`). Match them by name suffix — the server prefix is a
  per-install UUID and must never be hardcoded.
- Resolve the current user by calling `fetch` with the literal id `self`.
- Never set a task to `Done` on code evidence alone. Tasks whose Acceptance Criteria
  require a human step (real-printer test, tester's Pass/Fail record) close only when
  that human has certified them.
