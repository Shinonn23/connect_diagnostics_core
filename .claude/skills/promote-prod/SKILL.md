---
name: promote-prod
description: Gate-check then open the promotion PR user-acceptance-testing → production. Map each source to its UAT promotion, enforce post-PROD holds with a remediation-only release path, require target-bound certification or an audited bypass, and preserve uncertified issues. Use when the user wants to release to production.
---

# Promote to Production

Open the promotion PR **`user-acceptance-testing → production`** — but ONLY after
the batch currently on UAT has been signed off. Roles are in `CLAUDE.md`.

## Steps

1. **Determine the batch** = commits on `user-acceptance-testing` not yet in
   `production`:
   ```
   git fetch origin user-acceptance-testing production
   git log --oneline origin/production..origin/user-acceptance-testing
   ```
   Collect every included developments PR and its `Refs #` source issues. Enumerate
   every merged `developments → user-acceptance-testing` promotion PR whose merge
   commit is in the range, oldest first. Assign each developments PR to the first
   promotion merge commit that contains its merge commit. For a source referenced
   by more than one developments PR, use the promotion assigned to that source's
   latest included developments PR as its **governing UAT promotion PR**. Require
   that promotion body to name both the included PR and source issue; STOP on a
   missing or ambiguous mapping. Do not use one promotion PR for the whole range:
   cumulative PROD batches may contain several UAT promotions. Find every related
   `manual-test` task by enumerating tasks with
   `gh issue list --state all --limit 1000 --label manual-test --json number,title,body,url`
   and matching their source-issue references. For a current source, use the task
   belonging to its latest included developments PR. For a historical PROD source,
   use the task for the latest merged developments PR in production that `Refs` it,
   or the later deferred task explicitly named by its latest source `/test-fail`.
   STOP when the applicable task is missing or ambiguous; never accept an older
   task merely because it has a pass marker.
2. **Build source-scoped test evidence.** For each related task, parse its single
   `Test target: <environment> (<branch> @ <full SHA>)`. A valid certification is
   a `/test-pass — all steps verified on <environment> @ <full SHA>` authored by
   `newyodsapad` that exactly matches the current task target and is newer than the
   latest `/test-fail` or `/retest-start`. Bare, target-mismatched, or stale pass
   comments are invalid. A valid bypass for a source is an owner-authored
   `/test-bypass` marker that references that source's governing UAT promotion PR,
   whose **Manual-test bypass** section names the same source, owner, and non-empty
   reason. Test Status alone never substitutes for either evidence type.
3. **Gate — outstanding post-PROD failures.** Read every board item with
   `gh project item-list 6 --owner Shinonn23 --format json --limit 1000`. Exclude
   `manual-test` tasks and inspect every source issue whose Status is PROD Deploy.
   For a historical source outside the current batch, obtain its governing UAT PR
   from the PR referenced by its source `/test-bypass` marker and verify that PR is
   merged and contains the matching audit entry. A source without an active
   failure is globally clear only when it has both Test Status Passed and valid
   target-matched certification, or a valid bypass. This applies to every Test
   Status value: Passed without certification still needs bypass evidence.
   An uncertified and unaudited item is a global hold.

   When a PROD source has a `/test-fail`, the hold clears only after all of these
   conditions hold:
   - its Test Status is Passed and its related task has valid target-matched
     certification after the latest source failure;
   - it has no active re-test or unattributed active task failure; and
   - `Shinonn23` posted `/uat-approve` on the source issue strictly after its latest
     failure.

   Normally any unresolved post-PROD failure, open PROD issue with Test Status
   Failed, or `uat-bug` label stops the release. The sole exception is a
   **remediation-only release**: every included developments PR must directly
   `Refs #<held-source>` at least one currently held PROD source, every commit must
   map to those PRs, and no unrelated PR may be present. Each held source being
   remediated must be included in its governing UAT promotion, have a valid bypass
   for that promotion when it is not already re-certified, and have an owner
   `/uat-approve` strictly newer than its failure. Under this exception, only the
   referenced held sources may remain Failed or in re-test; every other source
   must pass the normal gates below. Add a **Post-PROD remediation** table to the
   PROD PR mapping each included developments PR to its held source. The exception
   permits deployment of the fix but does not clear any hold. Unrelated batches
   remain blocked until the held source passes on the new PROD target.
4. **Gate — UAT sign-off.** Every source issue in the current batch must be signed
   off by the owner (`Shinonn23`):
   - Read comments from each related test task, source issue, and the UAT promotion
     PRs with `gh issue view <n> --json comments` and
     `gh pr view <n> --json comments`.
   - On each test task, compare the latest `/test-fail` with the latest valid
     target-matched certification. When failure is later, its comment must name
     the exact affected source issues as
     `/test-fail — source issues #<n>[, #<n>...]: <reason>`, and every named issue
     must have a source-specific `/test-fail` that references this task with a
     `createdAt` equal to or later than the task marker. Equal timestamps are valid
     because GitHub comment timestamps have one-second resolution.
     Otherwise STOP: the active task failure is unattributed and no issue from the
     task may promote until `/test-result` records the mapping.
   - Treat a test task as an active re-test when its latest `/retest-start` is
     newer than its latest valid target-matched certification. An active re-test
     blocks promotion except for its referenced held source in an eligible
     remediation-only release.
   - Find the latest `/test-fail` timestamp on that source issue. Do not use a
     shared task marker as that issue's timestamp after its affected issues have
     been mapped. Find `/uat-approve` comments authored by `Shinonn23` on the
     source issue or that source's governing UAT promotion PR. A valid approval
     must be strictly newer than that source issue's latest failure; when no
     source-issue failure exists, any owner approval is eligible. An approval on a
     different UAT promotion PR does not apply.
   - Require either both Test Status Passed and valid target-matched certification,
     or a valid bypass tied to this source's governing UAT promotion PR, regardless
     of the current Test Status enum. A source with Failed status or an active
     re-test still blocks unless it is the referenced held source in an eligible
     remediation-only release. The issue must not have the `uat-bug` label.
5. **If any item lacks valid sign-off:** STOP and report the pending items,
   including unattributed task failure, unaudited pending test, missing approval,
   approval from the wrong governing PR, approval older than the latest source
   failure, target-mismatched certification, Failed or active re-test state, or
   `uat-bug` label. Do not open the PR. A failed UAT item → open a fix issue and it
   re-enters the dev loop.
6. **If all signed off:** create the promotion PR:
   ```
   gh pr create --base production --head user-acceptance-testing \
     --title "chore: release to production (<YYYY-MM-DD>)" \
     --body "<release notes: included PRs + issues>"
   ```
   Release Please runs only on `developments`, so this promotion does not bump.
   The production version and changelog must be the artifacts already published
   by the governing Release Please PR and carried through UAT.
7. **After the PR merges & PROD deploys:** move every source issue →
   **PROD Deploy** (`dba9dd7f`). Close an issue only when its Test Status is
   **Passed** and its manual-test task has valid target-matched certification by
   `newyodsapad`. Leave every bypassed or otherwise uncertified issue open,
   regardless of its Test Status enum. For a remediation-only release, keep each
   held source open and globally held, then run `/dispatch-test` after the new PROD
   SHA is explicitly verified; its rebound task records `/retest-start`. Only a
   later `/test-result` pass on that exact PROD target can clear the test portion of
   the hold. Consider running `/changelog` for notes.

## Output

Either the blocking table (nothing promoted) or the promotion PR URL + the issues
queued for PROD Deploy. Distinguish issues that will close, uncertified issues that
will remain open, and remediation holds that remain active. Never auto-merge.
