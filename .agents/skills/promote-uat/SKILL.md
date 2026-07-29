---
name: promote-uat
description: Gate-check then open the promotion PR developments → user-acceptance-testing. Normally requires every batched PR to have a manual-test task certified /test-pass by newyodsapad, with an explicit owner-only bypass that requires a reason and preserves pending test state. Use when the user wants to promote to UAT or cut a UAT release.
---

# Promote to UAT

Open the promotion PR **`developments → user-acceptance-testing`** after
inspecting every change and its manual-test state. Normally every item must be
certified by `newyodsapad`. The only exception is an explicit owner-authorized
manual-test bypass. Board IDs / roles are in `AGENTS.md`.

## Invocation

- Normal gate: `$promote-uat`
- Owner bypass: `$promote-uat --bypass-test "<reason>"`

Never infer a bypass from urgency or context. Require the exact flag and a
non-empty reason in the user's instruction.

## Steps

1. **Determine the batch** = commits on `developments` not yet in
   `user-acceptance-testing`:
   ```
   git fetch origin developments user-acceptance-testing
   git log --oneline origin/user-acceptance-testing..origin/developments
   ```
   Collect the complete set of **merged PRs** with
   `gh pr list --base developments --state merged --limit 1000 --json number,title,body,url,mergeCommit,mergedAt,headRefName,labels`
   and retain PRs whose merge commit is in the Git range. Verify that every
   non-promotion commit in the range maps to a PR; if any commit is unaccounted
   for, STOP and report it rather than silently excluding it. From every included
   PR body, collect the `Refs #` **source issues**.
   Classify a PR as Release Please metadata only when its head starts with
   `release-please--branches--developments` and it has the
   `autorelease: tagged` label. Exclude these PRs from source-issue and manual-test
   requirements, but keep them in the batch audit. Require the newest Release
   Please PR to be after every non-release PR in the range. Verify that its
   `connect_diagnostics_core/__init__.py` version equals the root value in
   `.release-please-manifest.json`, `CHANGELOG.md` contains that version, and the
   published GitHub Release `v<version>` targets the Release PR merge commit.
   STOP if the batch has unreleased commits, mismatched release metadata, or no
   matching published release.
2. **Find each non-release PR's test task** (`🧪 Test: PR #<n>`, label `manual-test`). Parse
   its single `Test target: <environment> (<branch> @ <full SHA>)`; missing or
   ambiguous target metadata fails the manual-test gate.
3. **Gate — every item must satisfy ALL of:**
   - test task is **closed**, and all its `- [x]` steps are ticked (no `- [ ]` left);
   - board **Test Status = Passed** on the test task and its source issues;
   - a `/test-pass — all steps verified on <environment> @ <full SHA>` comment
     exists **authored by `newyodsapad`**, names exactly the environment and SHA
     recorded in the task's current Test target, and is after the latest
     `/test-fail` or `/retest-start` marker (`gh issue view <n> --json comments`
     → compare comment bodies, timestamps, and authors). A bare or target-mismatched
     `/test-pass` is not certification.
4. **Handle the gate result:**
   - If all items pass, continue normally.
   - If any item fails and no bypass was explicitly requested, STOP. Report a
     table of pending items (PR, test task, and what is missing). Do not open the
     promotion PR.
   - If a bypass was explicitly requested, run `gh api user --jq .login` and
     require the exact authenticated login `Shinonn23`. STOP if the login differs
     or the reason is empty. Apply the bypass to every failing item in the current
     batch and keep the complete pending-items table for the PR body.
   - The bypass covers only the manual-test gate. It never covers an unaccounted
     commit, required CI, branch protection, review, deployment verification, or
     the owner `/uat-approve` required for production promotion.
5. **Create the promotion PR** after a normal pass or authorized bypass:
   ```
   gh pr create --base user-acceptance-testing --head developments \
     --title "chore: promote to UAT (<YYYY-MM-DD>)" \
     --body "<included PRs + certified items + bypass audit when applicable>"
   ```
   For a bypass, add a clearly labeled **Manual-test bypass** section containing
   the authenticated owner login, reason, and pending-items table with each PR,
   test task, source issue, current Test Status, unchecked steps, and missing or
   stale certification. State that bypassed items were not certified.
   After creating the PR, comment on every bypassed source issue from the same
   authenticated owner account:
   `/test-bypass — UAT promotion PR #<n>; owner Shinonn23; reason: <reason>`.
   The source comment and matching PR-body entry are durable audit evidence only;
   neither is a test result.
   Include the verified Release Please version and tag in the promotion PR body.
   Release Please runs only on `developments`, so this promotion copies the
   released version without another bump.
6. **Preserve bypassed test records.** Do not tick test steps, post `/test-pass`,
   change Test Status or Tested By, or close test tasks or source issues. A bypass
   is an authorization to promote, not a test result. Run later tasks and results
   through `$dispatch-test` and `$test-result`; both preserve an existing UAT or
   production deployment Status.
7. **Advance the board only after deployment.** Wait until the promotion PR is
   merged and its UAT deployment is explicitly verified, then move the promoted
   source issues, including bypassed ones, → **UAT Deploy** (`98236657`) while
   preserving their test fields. If a remediated source is already **PROD Deploy**
   (`dba9dd7f`), preserve PROD Deploy rather than moving it backward. Until merge
   and verified deployment are both true, leave board status unchanged. Note in
   the PR that UAT sign-off (`/uat-approve` by the owner) is required before
   `$promote-prod`.

## Output

Return either the blocking table (nothing promoted) or the promotion PR URL,
verified Release Please version/tag, and separate certified and bypassed lists.
For a bypass, also report the authenticated owner, reason, and source issues
carrying `/test-bypass` audit markers. Report board movement as pending until
merge and UAT deployment are verified; only then report the issues moved to UAT
Deploy and any existing PROD Deploy status preserved. Never auto-merge — branch
protection + review apply.
