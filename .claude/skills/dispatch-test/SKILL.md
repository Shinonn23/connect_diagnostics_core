---
name: dispatch-test
description: Create and assign the manual-test task for a merged/ready PR to newyodsapad — a tracking issue with the aggregated test cases, moved onto board #6 with Test Status = Testing. Use after a PR is ready/merged, or when re-issuing a test task.
---

# Dispatch Test Task

Create the per-PR **manual-test task** for `newyodsapad`, aggregating the test
cases of every issue the PR `Refs`. Board IDs are in `CLAUDE.md`.

## Input

`/dispatch-test <PR#>` (if omitted, infer the PR from the current branch via
`gh pr view --json number`).

## Steps

1. **Resolve the PR and its issues.** `gh pr view <PR#> --json number,title,body,url`.
   Parse `Refs #<n>` from the body (fall back to `closingIssuesReferences`). These
   are the **source issues**.
2. **Collect test cases.** For each source issue, read its body and pull the
   **Manual test steps** `- [ ]` lines. Keep them grouped per issue with a link.
3. **Create the test-task issue** (skip if one already exists for this PR — search
   `gh issue list --label manual-test --search "PR #<PR#>"`):
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
   `gh project item-list 6 --owner Shinonn23 --format json` (or add it with
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
