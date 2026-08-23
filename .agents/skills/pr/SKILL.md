---
name: pr
description: Open a documented pull request for the current branch. Use when the user asks to create a PR without running the full project shipping workflow.
---

# Pull Request Skill

Create well-documented pull requests with comprehensive descriptions.

## Usage

```
$pr
```

## Behavior

1. Verify the current branch is a work branch based on `developments`, then
   analyze `developments...HEAD` and its merge base.
2. Inspect the branch and commits for related issues. When evidence identifies
   one or more issues, include all of them; ask the user only when that evidence
   is ambiguous. When the user confirms that no related issue exists and the
   branch or commits do not contradict that, proceed without an issue reference.
   Never create an issue solely to satisfy the PR template.
3. Generate a Conventional Commit PR title whose type matches the branch type.
4. Fill the repository template at `.github/pull_request_template.md`, including:
   - Summary of changes
   - `Refs #<n>` for every related issue, or `None` when no issue exists; never
     use `Closes #<n>`
   - Type of change
   - Screenshots when the change affects UI
5. Create the PR with `gh pr create --base developments`. Do not substitute a
   generic body or invent an issue reference. An issue-less PR must explicitly
   record `None` in the template's Related issues section.

## Requirements

- GitHub CLI (`gh`) installed and authenticated
- On a work branch, not `developments`, `user-acceptance-testing`, or `production`
