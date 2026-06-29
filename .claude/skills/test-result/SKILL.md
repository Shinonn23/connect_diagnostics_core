---
name: test-result
description: Record the manual-test outcome for a PR's test task and certify it. Pass ticks all steps, sets Test Status = Passed, closes the test task and moves source issues forward; fail records the reason and keeps it open. Use when the tester reports a result.
---

# Test Result

Record a manual-test outcome on a PR's test task. Board IDs are in `CLAUDE.md`.

> **Certification authority:** only a `/test-pass` comment authored by
> `newyodsapad` counts toward UAT promotion (`/promote-uat` checks the comment
> author). Run this skill from the tester's own `gh` login, or have `newyodsapad`
> tick the steps and comment `/test-pass` in the GitHub UI. If you are NOT
> `newyodsapad` (`gh api user -q .login` to check), say so — you can update the
> board, but the certification comment will not satisfy the gate.

## Input

`/test-result <PR# | test-issue# | source-issue#> pass|fail [reason]`

## Steps

1. **Resolve the test task.** From a PR number → find its `🧪 Test: PR #<n>`
   issue (label `manual-test`). From an issue number → use it directly. Identify
   the **source issues** it covers.
2. **Read the checklist** in the test-task body and confirm with the user which
   steps passed. Do not mark pass unless **every** step is verified.

### On PASS

3. **Tick every** `- [ ]` → `- [x]` in the test-task body (`gh issue edit <n> --body …`).
4. Board: **Test Status = Passed** (`97d946bc`), **Tested By** = the tester
   (text field `PVTF_lAHOB1tcMM4BLM7IzhWdjBE`), **Status → Test Review** (`6c769416`)
   for the test task and each source issue.
5. **Certify:** `gh issue comment <test-issue> --body "/test-pass — all steps verified on DEV"`.
6. **Close** the test task and each fully-passed source issue
   (`gh issue close <n> --reason completed`).

### On FAIL

3. Board: **Test Status = Failed** (`15087b1c`) on the test task + the failing
   source issue; leave **Status = Test In progress**. Keep everything **open**.
4. **Record:** `gh issue comment <test-issue> --body "/test-fail — <reason>"`.
5. Offer to open a **fix issue** (`fix/` work) referencing the failed source
   issue, so it re-enters the dev loop. Do not auto-create it without confirmation.

## Output

State the new Test Status, whether certification was recorded (and by whom), and
for a fail, the reason + any fix issue created.
