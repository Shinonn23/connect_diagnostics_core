---
name: promote-prod
description: Gate-check then open the promotion PR user-acceptance-testing → production. Promotes only after UAT sign-off (/uat-approve by the owner) on the batch on UAT. Use when the user wants to release to production.
---

# Promote to Production

Open the promotion PR **`user-acceptance-testing → production`** — but ONLY after
the batch currently on UAT has been signed off. Roles in `CLAUDE.md`.

## Steps

1. **Determine the batch** = commits on `user-acceptance-testing` not yet in
   `production`:
   ```
   git fetch origin user-acceptance-testing production
   git log --oneline origin/production..origin/user-acceptance-testing
   ```
   Collect the included PRs and their `Refs #` source issues (these should be the
   ones in board column **UAT Deploy**).
2. **Gate — UAT sign-off.** Every source issue in the batch must be signed off by
   the owner (`Shinonn23`):
   - a `/uat-approve` comment **authored by `Shinonn23`** on the issue (or on the
     UAT promotion PR), `gh issue view <n> --json comments` → check
     `.comments[] | select(.author.login=="Shinonn23")`;
   - and the issue is not reopened / not labelled `uat-bug`.
3. **If any item lacks sign-off:** STOP and report the pending items. Do not open
   the PR. A failed UAT item → open a fix issue and it re-enters the dev loop.
4. **If all signed off:** create the promotion PR:
   ```
   gh pr create --base production --head user-acceptance-testing \
     --title "chore: release to production (<YYYY-MM-DD>)" \
     --body "<release notes: included PRs + issues>"
   ```
   (Base is `production`, so `auto-version` does not bump. The released version is
   whatever `__version__` already is on the branch.)
5. **After the PR merges & PROD deploys:** move the source issues → **PROD Deploy**
   (`dba9dd7f`) and close any still open. Consider running `/changelog` for notes.

## Output

Either the blocking table (nothing promoted) or the promotion PR url + the issues
queued for PROD Deploy. Never auto-merge.
