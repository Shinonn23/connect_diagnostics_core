---
name: take-task
description: Claim a Notion Task Tracker task — read it in full, summarize what is actually left against the repo, propose a branch name, then set Status, Assignee and Start Date. Use when the user says which task they are starting.
---

# Take Task

Claim one task and set up the work. Database and property IDs are in `CLAUDE.md`
under **Notion Task Tracker reference**. Branch naming follows the branch rule in
the same file.

## Input

`/take-task <TSK-n>` — accepts `TSK-12`, `12`, or a Notion page URL.

## Steps

1. **Resolve the task.** Query
   `collection://bcd5f7fa-c9c1-43dc-bfd7-c30272a1d100` by `"Task ID"`, or `fetch`
   the page directly when given a URL. STOP when nothing matches or more than one
   row does — report what was found instead of picking one.
2. **Read the whole task.** `fetch` the page for `Description`,
   `Acceptance Criteria`, `Dependencies`, `Parent item`, `Sub-item`,
   `Related User Tickets`, `Assignee`, and current `Status`. Read the linked
   parent and children too when they exist.
3. **Gate before writing.** STOP and ask when any of these hold:
   - `Status` is `Done` or `Cancelled`;
   - `Assignee` is someone other than the current user;
   - a listed dependency is unfinished;
   - it is an umbrella whose `Sub-item` rows are still open — offer the children.

   Report the conflict and let the user decide. Do not route around a gate.
4. **Summarize before starting.** State in the response:
   - what the task asks, in one or two sentences;
   - its Acceptance Criteria verbatim when present;
   - what already exists in the repo, citing files — search before claiming
     anything is missing (`rg`, `git log`, `gh pr list`);
   - what is genuinely left;
   - which parts **no code can finish** (real-printer tests, tester sign-off,
     physical measurements), so a verification task is not mistaken for a coding
     task.
5. **Propose a branch.** `<type>/<short-kebab-summary>` per `CLAUDE.md`, with the
   type inferred from `Work Type` (`Development` → `feat`/`fix`,
   `Configuration` → `chore`, `Data Migration` → `refactor`, `Documentation` →
   `docs`). Offer the exact `git checkout -b` command; creating the branch is the
   user's call, not this skill's.
6. **Confirm, then write.** Show the exact field values first and wait for a yes —
   Notion is shared, outward-facing state. Then one `update-page` call with
   `command: update_properties`:
   - `Status` → `In progress`
   - `Assignee` → `[<self user id>]`
   - `date:Start Date:start` → today, **only when it is empty**; never overwrite an
     existing start date
   - `Latest Update` → a dated line naming what is being started and by whom,
     appended to whatever is already there rather than replacing history
7. **Verify.** Re-query the row and show the stored values. Running this skill
   twice on the same task must be a safe no-op, not a duplicate write.

## Output

The fields changed with their before → after values, the summary of what is left,
the parts that need a human, and the proposed branch command.
