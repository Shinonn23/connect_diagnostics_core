---
name: dispatch-test
description: Create and assign the manual-test task for a PR merged and deployed to DEV — a tracking issue with aggregated test cases, moved onto board #6 with Test Status = Testing. Use after DEV deployment or when explicitly re-issuing a test task.
---

# Dispatch Test Task

Create the per-PR **manual-test task** for `newyodsapad`, aggregating the test
cases of every issue the PR `Refs`. Board IDs are in `AGENTS.md`.

## Input

`$dispatch-test <PR#>` (if omitted, infer the PR from the current branch via
`gh pr view --json number`).

## Steps

1. **Verify readiness and resolve the PR.** Read
   `gh pr view <PR#> --json number,title,body,url,state,closingIssuesReferences`.
   The PR must be merged and its DEV deployment must be verified explicitly; if
   either condition is missing, STOP without changing issues or board fields.
   Parse `Refs #<n>` from the body, falling back to the requested
   `closingIssuesReferences` field. These are the **source issues**.
2. **Collect test cases.** For each source issue, read its body and pull the
   **Manual test steps** `- [ ]` lines. Keep them grouped per issue with a link.
3. **Find or create the test-task issue.** Search every state first:
   `gh issue list --state all --limit 100 --label manual-test --search "PR #<PR#> in:title"`.
   Reuse an open task only when it is not Failed. If a matching task is closed,
   Passed, or Failed, STOP unless the user explicitly requested a re-test; on an
   approved re-test, reopen the task and every source issue, add a `/retest-start`
   comment to the task, then reset that task instead of creating a duplicate. The
   marker invalidates earlier certifications. Create a task only when no match exists:
   ```
   gh issue create \
     --title "🧪 Test: PR #<PR#> — <pr title>" \
     --label manual-test \
     --assignee newyodsapad \
     --body "<body>"
   ```
   Body contains: link to the PR, then the aggregated checklist grouped per source
   issue, and the instruction:
   > After this PR is merged & deployed to the DEV site, run each step. Reply
   > `/test-pass` when **all** pass, or `/test-fail <reason>` if any fail.
   > (Create the `manual-test` label first if missing: `gh label create manual-test
--color BFD4F2 --description "Manual test task" 2>/dev/null || true`.)
4. **Put it on the board** and mark it testing. Find its item id from
   `gh project item-list 6 --owner Shinonn23 --format json --limit 1000` (or add it with
   `gh project item-add 6 --owner Shinonn23 --url <issue url>`), then:
   `gh project item-edit --id <ITEM> --field-id PVTSSF_lAHOB1tcMM4BLM7IzhWdi_0 --project-id PVT_kwHOB1tcMM4BLM7I --single-select-option-id 2556afad` (Test Status = Testing).
5. **Move each source issue into testing.** For each source issue's board item:
   - Status → **Test In progress** (`--field-id PVTSSF_lAHOB1tcMM4BLM7Izg62NJg --single-select-option-id 18955566`)
   - Test Status → **Testing** (`2556afad`)
   - Ensure `newyodsapad` is an assignee: `gh issue edit <n> --add-assignee newyodsapad`.
6. **Link from the PR:** `gh pr comment <PR#> --body "🧪 Manual test task: #<test-issue> (assigned @newyodsapad)"`.

## Output

The test-task issue url, the source issues moved to testing, and a one-line
reminder that `newyodsapad` certifies via `/test-pass`.
