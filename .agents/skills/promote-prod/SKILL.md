---
name: promote-prod
description: Verify the accounted UAT batch and open the promotion PR user-acceptance-testing → production. Use when the user wants to release to production.
---

# Promote to Production

Open the promotion PR **`user-acceptance-testing → production`** after verifying
the complete UAT batch. CI, review, branch protection, and commit accounting remain
required; UAT verification is handled separately from pull requests.

## Steps

1. **Determine the batch** = commits on `user-acceptance-testing` not yet in
   `production`:
   ```
   git fetch origin user-acceptance-testing production
   git log --oneline origin/production..origin/user-acceptance-testing
   ```
   Enumerate merged `developments → user-acceptance-testing` promotion PRs whose
   merge commits are in the range, oldest first. For every included developments
   PR, verify it is named by the first promotion merge commit that contains it.
   STOP and report any unaccounted or ambiguous commit instead of silently
   excluding it. Collect `Refs #` source issues from every included development
   PR body.
2. **Verify release continuity.** Confirm each included promotion PR identifies
   the included development PRs and carries the published Release Please version
   and tag. The version and changelog must be the artifacts already released from
   `developments`; this promotion does not calculate another version bump.
3. **Create the promotion PR**:
   ```
   gh pr create --base production --head user-acceptance-testing \
     --title "chore: release to production (<YYYY-MM-DD>)" \
     --body "<included UAT promotions, development PRs, source issues, and release notes>"
   ```
4. **Complete delivery after deployment.** Once the PR is merged and its PROD
   deployment is explicitly verified, move every related source issue to
   **PROD Deploy** (`dba9dd7f`) and close it. Do not create or update PR-linked
   testing records.

## Output

Return either a blocking commit/accounting detail or the production PR URL with
the issues awaiting verified PROD deployment. Never auto-merge.

## Board #6 reference

- Project: owner `Shinonn23`, number `6`, id `PVT_kwHOB1tcMM4BLM7I`.
- **Status** field `PVTSSF_lAHOB1tcMM4BLM7Izg62NJg`: PROD Deploy `dba9dd7f`.
- Set a field: `gh project item-edit --id <ITEM_ID> --field-id <FIELD_ID> --project-id PVT_kwHOB1tcMM4BLM7I --single-select-option-id <OPT_ID>`. Find an issue's item id with `gh project item-list 6 --owner Shinonn23 --format json --limit 1000`.
