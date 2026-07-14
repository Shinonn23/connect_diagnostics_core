---
name: test-result
description: Record the manual-test outcome for a PR's test task and certify it. Pass ticks all steps, sets Test Status = Passed, closes the test task and moves source issues forward; fail records the reason and keeps it open. Use when the tester reports a result.
---

# Test Result

Record a manual-test outcome on a PR's test task. Board IDs are in `CLAUDE.md`.

> **Certification authority:** only a `/test-pass` comment authored by
> `newyodsapad` counts toward UAT promotion (`/promote-uat` checks the comment
> author). Run this skill from the tester's own `gh` login, or have `newyodsapad`
> tick the steps and comment `/test-pass` in the GitHub UI. A non-certifier must
> not mark a pass, close issues, or post a non-authoritative `/test-pass`.

## Input

`/test-result <PR# | test-issue# | source-issue#> pass|fail [reason]`

## Steps

1. **Resolve the test task without guessing the input type.** Try the number as a
   PR first. For a PR, find its `🧪 Test: PR #<n>` issue across all states. For an
   issue, read its labels: use it directly only when it has the `manual-test`
   label. Otherwise it is a source issue; enumerate manual-test tasks with
   `gh issue list --state all --limit 1000 --label manual-test --json number,title,body,url`
   and find the single task that links or references that source issue. If the
   result is missing or ambiguous, STOP and report the candidates. Identify the
   complete set of **source issues** from the resolved test task.
2. **Read the checklist** in the test-task body and confirm with the user which
   steps passed. Do not mark pass unless **every** step is verified.

### On PASS

3. **Verify certification authority before any mutation.** Check
   `gh api user -q .login`. If it is not `newyodsapad`, accept the pass only when
   the resolved task already has a valid `/test-pass` authored by `newyodsapad`
   after the latest `/test-fail` or `/retest-start` marker; otherwise STOP without
   editing the task, board, or issues. Do not post another certification when
   relying on an existing one.
4. **Tick every** `- [ ]` → `- [x]` in the test-task body (`gh issue edit <n> --body …`).
5. Board: **Test Status = Passed** (`97d946bc`), **Tested By** = the tester
   (text field `PVTF_lAHOB1tcMM4BLM7IzhWdjBE`), **Status → Test Review** (`6c769416`)
   for the test task and each source issue.
6. **Certify when running as `newyodsapad`:**
   `gh issue comment <test-issue> --body "/test-pass — all steps verified on DEV"`.
7. **Close** the test task and each fully-passed source issue only after the valid
   certification is present
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
