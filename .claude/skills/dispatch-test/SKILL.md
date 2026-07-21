---
name: dispatch-test
description: Create and assign a revision-bound manual-test task for a merged PR, including deferred tests after UAT or PROD promotion. Select the environment from source deployment status, verify the exact deployed commit, and preserve UAT Deploy or PROD Deploy source-issue status. Use after deployment or when explicitly re-issuing a test task.
---

# Dispatch Test Task

Create the per-PR **manual-test task** for `newyodsapad`, aggregating the test
cases of every issue the PR `Refs`. Board IDs are in `CLAUDE.md`.

## Input

`/dispatch-test <PR#>` (if omitted, infer the PR from the current branch via
`gh pr view --json number`).

## Steps

1. **Verify readiness and resolve the PR.** Read
   `gh pr view <PR#> --json number,title,body,url,state,mergeCommit,closingIssuesReferences`.
   The PR must be merged; otherwise STOP without changing issues or board fields.
   Parse `Refs #<n>` from the body, falling back to the requested
   `closingIssuesReferences` field. These are the **source issues**. Read their
   current board Status values from
   `gh project item-list 6 --owner Shinonn23 --format json --limit 1000` before
   any mutation. Select one target for the whole task:
   - all source issues at **PROD Deploy** → PROD / `production`;
   - otherwise all at **UAT Deploy** → UAT / `user-acceptance-testing`;
   - otherwise none at either deployment Status → DEV / `developments`.
   STOP on mixed deployment statuses. Fetch the target branch, require the PR merge
   commit to be its ancestor, capture the branch SHA, and require explicit evidence
   that this exact SHA is currently deployed to the target environment. Do not use
   a newer DEV deployment to certify code preserved on UAT or PROD.
2. **Collect test cases.** For each source issue, read its body and pull the
   **Manual test steps** `- [ ]` lines. Keep them grouped per issue with a link.
3. **Find or create the test-task issue.** Search every state first:
   `gh issue list --state all --limit 100 --label manual-test --search "PR #<PR#> in:title"`.
   Reuse an open task only when it is not Failed. If a matching task is closed,
   Passed, or Failed, STOP unless the user explicitly requested a re-test; on an
   approved re-test, reopen the task and every source issue, add a `/retest-start`
   comment to the task, then reset that task instead of creating a duplicate. The
   marker invalidates earlier certifications. Whenever reusing a task whose existing
   `Test target` differs from the selected environment or SHA, edit its body to
   replace the target, reset every checklist item to unchecked, and comment
   `/retest-start — target rebound from <old target> to <new target>`. Do this before
   changing board fields; never leave stale target metadata on a reused task.
   Create a task only when no match exists:
   ```
   gh issue create \
     --title "🧪 Test: PR #<PR#> — <pr title>" \
     --label manual-test \
     --assignee newyodsapad \
     --body "<body>"
   ```
   Body contains: link to the PR, `Test target: <environment> (<branch> @ <full
   SHA>)`, then the aggregated checklist grouped per source issue and the
   instruction (substitute the task's literal environment and full SHA; do not
   leave placeholders in the posted marker):
   > On the exact test target above, run each step. Reply `/test-pass — all steps
   > verified on <environment> @ <full SHA>` when **all** pass, or `/test-fail —
   > source issues #<n>[, #<n>...]: <reason>` if any fail.
   > (Create the `manual-test` label first if missing: `gh label create manual-test
--color BFD4F2 --description "Manual test task" 2>/dev/null || true`.)
4. **Put it on the board** and mark it testing. Find its item id from
   `gh project item-list 6 --owner Shinonn23 --format json --limit 1000` (or add it with
   `gh project item-add 6 --owner Shinonn23 --url <issue url>`), then:
   `gh project item-edit --id <ITEM> --field-id PVTSSF_lAHOB1tcMM4BLM7IzhWdi_0 --project-id PVT_kwHOB1tcMM4BLM7I --single-select-option-id 2556afad` (Test Status = Testing).
5. **Update each source issue without regressing deployment status.** For each
   source issue's board item:
   - Preserve **UAT Deploy** (`98236657`) or **PROD Deploy** (`dba9dd7f`) when the
     source issue already has either Status; otherwise set Status →
     **Test In progress** (`18955566`).
   - Test Status → **Testing** (`2556afad`)
   - Ensure `newyodsapad` is an assignee: `gh issue edit <n> --add-assignee newyodsapad`.
6. **Link from the PR:** `gh pr comment <PR#> --body "🧪 Manual test task: #<test-issue> (assigned @newyodsapad)"`.

## Output

Return the test-task issue URL, exact environment and commit under test, source
issues marked Testing, any deployment Status preserved, and a one-line reminder
that `newyodsapad` certifies with the target-qualified `/test-pass — all steps
verified on <environment> @ <full SHA>` marker.
