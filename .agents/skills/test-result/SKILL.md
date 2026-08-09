---
name: test-result
description: Record and certify a PR's revision-bound manual-test outcome, including deferred results after a UAT test bypass. Verify the task's exact deployed environment and commit, preserve deployment status, and create a global release hold for post-PROD failures. Use when the tester reports a result.
---

# Test Result

Record a manual-test outcome on a PR's test task. Board field IDs are in the Board #6 reference below.
Deferred results after a UAT test bypass must update test state without regressing
a source issue's deployment status.

> **Certification authority:** only a `/test-pass` comment authored by
> `newyodsapad` counts toward UAT promotion (`$promote-uat` checks the comment
> author). Run this skill from the tester's own `gh` login, or have `newyodsapad`
> tick the steps and comment `/test-pass` in the GitHub UI. A non-certifier must
> not mark a pass, close issues, or post a non-authoritative `/test-pass`.

## Input

`$test-result <PR# | test-issue# | source-issue#> pass|fail [reason]`

## Steps

1. **Resolve the test task without guessing the input type.** Try the number as a
   PR first. For a PR, find its `🧪 Test: PR #<n>` issue across all states. For an
   issue, read its labels: use it directly only when it has the `manual-test`
   label. Otherwise it is a source issue; enumerate manual-test tasks with
   `gh issue list --state all --limit 1000 --label manual-test --json number,title,body,url`
   and find the single task that links or references that source issue. If the
   result is missing or ambiguous, STOP and report the candidates. Identify the
   complete set of **source issues** from the resolved test task. Before any
   mutation, read the current board Status of every source issue
   from `gh project item-list 6 --owner Shinonn23 --format json --limit 1000`.
   Parse the task's `Test target: <environment> (<branch> @ <full SHA>)`. STOP and
   re-dispatch the task when this metadata is missing or ambiguous. Fetch the
   branch, require the target SHA to remain in its history, and require explicit
   evidence that this exact SHA is deployed to that environment before recording
   a result.
2. **Read the checklist** in the test-task body and confirm with the user which
   steps passed. Do not mark pass unless **every** step is verified. For a failed
   shared task, require the exact failing source issue(s) and reason before any
   mutation; STOP rather than infer the affected issue from the task.

### On PASS

3. **Verify certification authority before any mutation.** Check
   `gh api user -q .login`. If it is not `newyodsapad`, accept the pass only when
   the resolved task already has a `/test-pass — all steps verified on
   <environment> @ <full SHA>` authored by `newyodsapad` that names exactly the
   task's current Test target and is after the latest `/test-fail` or
   `/retest-start` marker; otherwise STOP without editing the task, board, or
   issues. A bare or target-mismatched `/test-pass` is invalid. Do not post another
   certification when relying on an existing one.
4. **Tick every** `- [ ]` → `- [x]` in the test-task body (`gh issue edit <n> --body …`).
5. **Update the board without regressing deployment status:**
   - On the test task, set **Test Status = Passed** (`97d946bc`), **Tested By** =
     the tester (text field `PVTF_lAHOB1tcMM4BLM7IzhWdjBE`), and
     **Status → Test Review** (`6c769416`).
   - On each source issue, set the same Test Status and Tested By values. Preserve
     **Status = UAT Deploy** (`98236657`) or **PROD Deploy** (`dba9dd7f`) when it
     already has either deployment status; otherwise set **Status → Test Review**.
6. **Certify when running as `newyodsapad`:**
   `gh issue comment <test-issue> --body "/test-pass — all steps verified on <environment> @ <full SHA>"`.
7. **Close** the test task and each fully-passed source issue only after the valid,
   target-matched certification is present
   (`gh issue close <n> --reason completed`).

### On FAIL

3. **Update the board without regressing deployment status:**
   - On the test task, set **Test Status = Failed** (`15087b1c`) and
     **Status = Test In progress** (`18955566`).
   - On each failing source issue, set Test Status = Failed. Preserve
     **Status = UAT Deploy** (`98236657`) or **PROD Deploy** (`dba9dd7f`) when it
     already has either deployment status; otherwise set Status = Test In progress.
   - Reopen the test task and every failing source issue that is closed. Keep them
     **open**, including a deployed source issue whose Status is preserved.
4. **Record and propagate the failure:**
   - Comment on the test task:
     `gh issue comment <test-issue> --body "/test-fail — source issues #<n>[, #<n>...]: <reason> (target <environment> @ <full SHA>)"`.
     List exactly the failing source issues so a shared task's failure is
     attributable.
   - Comment on each failing source issue:
     `gh issue comment <source-issue> --body "/test-fail — deferred manual test #<test-issue> failed: <reason>"`.
   - Treat the source-issue marker as invalidating every earlier `/uat-approve`
     for that item. A later production promotion requires a new owner approval
     posted after this failure. When the preserved Status is PROD Deploy, this
     failure also creates a global production hold: no unrelated later batch may
     promote until the issue has Passed with target-matched certification and has
     a newer owner approval. A remediation-only release may deploy its fix under
     `$promote-prod`, but the hold remains active until that exact new PROD target
     passes.
5. Offer to open a **fix issue** (`fix/` work) referencing the failed source
   issue, so it re-enters the dev loop. The eventual remediation PR must directly
   `Refs #<failed-source>` every PROD-held source it fixes (and may also Ref the
   fix issue); this is the evidence that lets `$promote-prod` distinguish the
   remediation-only batch from unrelated work. Do not auto-create it without
   confirmation.

## Output

State the exact tested environment and commit, new Test Status, whether
certification was recorded (and by whom), any deployment Status preserved, and for
a fail, the reason, global hold when applicable, and any fix issue created.

## Board #6 reference

- Project: owner `Shinonn23`, number `6`, id `PVT_kwHOB1tcMM4BLM7I`.
- **Status** field `PVTSSF_lAHOB1tcMM4BLM7Izg62NJg`: TODO `f75ad846` · DEV Ready `61e4505c` · Dev In progress `47fc9ee4` · Dev review `df73e18b` · Test In progress `18955566` · Test Review `6c769416` · UAT Deploy `98236657` · PROD Deploy `dba9dd7f` · Hold `232c6587`.
- **Test Status** field `PVTSSF_lAHOB1tcMM4BLM7IzhWdi_0`: Not Tested `9d66b7d0` · Testing `2556afad` · Passed `97d946bc` · Failed `15087b1c`.
- **Tested By** field `PVTF_lAHOB1tcMM4BLM7IzhWdjBE` (text).
- Set a field: `gh project item-edit --id <ITEM_ID> --field-id <FIELD_ID> --project-id PVT_kwHOB1tcMM4BLM7I --single-select-option-id <OPT_ID>` (text fields use `--text`). Find an issue's item id with `gh project item-list 6 --owner Shinonn23 --format json --limit 1000`.
