---
name: ship-pr
description: From the current work branch, open a ready-to-merge PR into `developments` (conventional title, Refs the issues, aggregated manual-test checklist, CI), then dispatch a manual-test task to newyodsapad. Use when the user says "ship", "open a PR", "ready to merge", or finishes a feature/fix.
---

# Ship PR

Turn the current work branch into a **ready-to-merge** PR into `developments`
and queue its manual testing for `newyodsapad`. Follows the project rules in
`CLAUDE.md` and `.github/WORKFLOW.md`.

## Preconditions

1. Current branch is a **work branch**, not `developments` / `user-acceptance-testing`
   / `production`. If on a long-lived branch, stop and ask the user to branch.
2. Branch name matches `^(feat|fix|refactor|chore|style|test|docs|perf|build|ci|revert)/[a-z0-9._/-]+$`.
   If not, propose a compliant rename (`git branch -m <new>`) and confirm before continuing.
3. Working tree changes are committed (use `/commit` if needed). Do not commit
   unrelated changes.

## Steps

1. **Identify the issue(s)** this branch addresses. Infer from the branch name,
   commit messages, or ask the user. You may have **one or many** issues.
2. **Read each issue** (`gh issue view <n> --json title,body,labels`) and extract
   its **Manual test steps** (`- [ ]` task-list). You aggregate these into the PR
   and the test task — this is the "Claude helps look at the relevant test cases" part.
3. **Decide the PR title type** = the branch `<type>` (Conventional Commits).
   This drives the auto-version bump (see CLAUDE.md). For `revert`, warn the user
   that the version must be bumped manually.
4. **Push** the branch: `git push -u origin <branch>`.
5. **Open the PR into `developments`** with `gh pr create --base developments`:
   - Title: `<type>: <summary>`
   - Body: fill `.github/pull_request_template.md`. Use **`Refs #<n>`** for every
     issue (NEVER `Closes #`). Paste the aggregated manual-test table.
6. **Report readiness.** Poll CI: `gh pr checks <PR#>`. "Ready to merge" =
   `Server` + `Frappe Linter` green and 1 review present. Do **not** auto-merge
   (branch protection + human review). Tell the user the exact blockers if any.
7. **Dispatch the test task** — run the `dispatch-test` skill steps for this PR
   (create the `🧪 Test: PR #<N>` issue assigned to `newyodsapad`, move source
   issues to **Test In progress** / **Test Status = Testing**, comment on the PR).
   Note in the test task that testing happens **after this PR is merged & deployed
   to the DEV site**.

## Output

Report: PR url + title, CI status, the test-task issue url, and the source issues
moved to testing. If anything blocks "ready to merge", list it explicitly.
