---
name: update-task
description: Record progress on a Notion Task Tracker task — write a dated Latest Update and move Status only as far as the evidence supports, never declaring Done on work a human must certify. Use when the user reports what happened on a task.
---

# Update Task

Record what happened on a task and move its Status honestly. Database and
property IDs are in the Notion Task Tracker reference below.

## Input

`/update-task <TSK-n> [note]` — accepts `TSK-12`, `12`, or a Notion page URL. The
note is the user's headline; the evidence gathered below is what justifies a
Status change.

## Steps

1. **Resolve and read.** Same lookup as `/take-task` step 1-2, plus the current
   `Latest Update` and `Status` so the new note extends the history instead of
   erasing it. STOP on an ambiguous or missing match.
2. **Gather evidence.** For the related work: `git log --oneline`,
   `gh pr view <PR#> --json state,mergedAt,url`, `gh pr checks <PR#>`. Match the
   task against real repo state before writing anything — a task can be further
   along, or further behind, than the person reporting it believes.
3. **Pick the transition, and justify it out loud.**
   - `Not started` → `In progress` — work has actually begun.
   - `In progress` → `In review` — the PR is open and CI is green. Not merely
     "code written".
   - `In review` → `Done` — **only** when the Acceptance Criteria are met, and for
     `Work Type` = `Testing` or anything tagged `UAT` only when a named human has
     certified it. **STOP and ask otherwise.** A merged PR is not sign-off; this
     project reserves test certification for `newyodsapad`, and criteria such as
     "พิมพ์ทดสอบจากเครื่องจริง และบันทึกผล Pass/Fail" cannot be satisfied from code.
   - → `Backlog` or `Cancelled` — requires a stated reason, recorded in the note.

   When the evidence supports a smaller step than the user asked for, say so and
   take the smaller step.
4. **Always write `Latest Update`.** Dated, naming what changed and linking the PR
   or commit. Never blank it, and never drop context another reader would need.
5. **Confirm, then write.** Show before → after per field and wait for a yes, then
   one `update-page` call with `command: update_properties`.
6. **Check the parent.** When the row has a `Parent item` and every sibling is now
   `Done` or `Cancelled`, **suggest** closing the umbrella and say which criteria
   it still carries of its own. Never close a parent automatically.
7. **Report what remains.** Name what still blocks the task from closing.

## Output

The fields changed with before → after values, the reasoning behind the Status
chosen (especially any refusal to mark `Done`), whether a parent is now closable,
and what remains before the task can close.

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
