---
name: promote-uat
description: Verify the released batch and open the promotion PR developments → user-acceptance-testing. Use when the user wants to promote to UAT or cut a UAT release.
---

# Promote to UAT

Open the promotion PR **`developments → user-acceptance-testing`** after verifying
the complete released batch. CI, review, branch protection, commit accounting, and
Release Please artifacts remain required; UAT verification is handled separately
from pull requests.

## Steps

1. **Determine the batch** = commits on `developments` not yet in
   `user-acceptance-testing`:
   ```
   git fetch origin developments user-acceptance-testing
   git log --oneline origin/user-acceptance-testing..origin/developments
   ```
   Collect the complete set of **merged PRs** with
   `gh pr list --base developments --state merged --limit 1000 --json number,title,body,url,mergeCommit,mergedAt,headRefName,labels`
   and retain PRs whose merge commit is in the Git range. Verify every
   non-promotion commit maps to a PR; STOP and report unaccounted commits. Collect
   `Refs #` source issues from every included non-release PR body.
2. **Verify the release artifacts.** Classify a Release Please PR only when its
   head starts with `release-please--branches--developments` and it has the
   `autorelease: tagged` label. Keep it in the batch audit but exclude it from
   source-issue reporting. Require the newest Release Please PR to be after every
   non-release PR in the range. Verify its
   `connect_diagnostics_core/__init__.py` version equals the root value in
   `.release-please-manifest.json`, `CHANGELOG.md` contains that version, and the
   published GitHub Release `v<version>` targets the Release PR merge commit. STOP
   if the batch has unreleased commits, mismatched metadata, or no matching release.
3. **Create the promotion PR**:
   ```
   gh pr create --base user-acceptance-testing --head developments \
     --title "chore: promote to UAT (<YYYY-MM-DD>)" \
     --body "<included PRs, source issues, and verified Release Please version/tag>"
   ```
   The promotion copies the released version and does not calculate another bump.
4. **Advance the board only after deployment.** Once the PR is merged and its UAT
   deployment is explicitly verified, move related source issues to **UAT Deploy**
   (`98236657`). Preserve an existing **PROD Deploy** status rather than moving it
   backwards. Do not create or update PR-linked testing records.

## Output

Return either the blocking commit/accounting or release-artifact details, or the
promotion PR URL with its verified version/tag and source issues awaiting UAT
deployment. Never auto-merge.

## Board #6 reference

- Project: owner `Shinonn23`, number `6`, id `PVT_kwHOB1tcMM4BLM7I`.
- **Status** field `PVTSSF_lAHOB1tcMM4BLM7Izg62NJg`: UAT Deploy `98236657` · PROD Deploy `dba9dd7f`.
- Set a field: `gh project item-edit --id <ITEM_ID> --field-id <FIELD_ID> --project-id PVT_kwHOB1tcMM4BLM7I --single-select-option-id <OPT_ID>`. Find an issue's item id with `gh project item-list 6 --owner Shinonn23 --format json --limit 1000`.
