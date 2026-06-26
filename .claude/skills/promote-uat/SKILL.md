---
name: promote-uat
description: Gate-check then open the promotion PR developments → user-acceptance-testing. Promotes only when every PR merged into developments since the last UAT promotion has its manual-test task certified /test-pass by newyodsapad. Use when the user wants to promote to UAT or cut a UAT release.
---

# Promote to UAT

Open the promotion PR **`developments → user-acceptance-testing`** — but ONLY
after verifying every change in the batch was manually tested and certified by
`newyodsapad`. Board IDs / roles in `CLAUDE.md`.

## Steps

1. **Determine the batch** = commits on `developments` not yet in
   `user-acceptance-testing`:
   ```
   git fetch origin developments user-acceptance-testing
   git log --oneline origin/user-acceptance-testing..origin/developments
   ```
   Collect the **merged PRs** in that range (`gh pr list --base developments
--state merged` and match by merge commit / date), and from each PR body the
   `Refs #` **source issues**.
2. **Find each PR's test task** (`🧪 Test: PR #<n>`, label `manual-test`).
3. **Gate — every item must satisfy ALL of:**
   - test task is **closed**, and all its `- [x]` steps are ticked (no `- [ ]` left);
   - board **Test Status = Passed** on the test task and its source issues;
   - a `/test-pass` comment exists **authored by `newyodsapad`** and there is no
     later `/test-fail` (`gh issue view <n> --json comments` → check
     `.comments[] | select(.author.login=="newyodsapad")`).
4. **If any item fails the gate:** STOP. Report a table of pending items (PR,
   test task, what's missing: not certified / Test Status not Passed / open steps).
   Do not open the promotion PR.
5. **If all pass:** create the promotion PR:
   ```
   gh pr create --base user-acceptance-testing --head developments \
     --title "chore: promote to UAT (<YYYY-MM-DD>)" \
     --body "<list of included PRs + certified source issues>"
   ```
   (Base is `user-acceptance-testing`, so `auto-version` does not bump.)
6. **Advance the board:** move the promoted source issues → **UAT Deploy**
   (`98236657`). Note in the PR that UAT sign-off (`/uat-approve` by the owner) is
   required before `/promote-prod`.

## Output

Either the blocking table (nothing promoted) or the promotion PR url + the list of
certified issues moved to UAT Deploy. Never auto-merge — branch protection +
review apply.
