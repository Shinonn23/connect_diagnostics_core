# Pull Request Skill

Create well-documented pull requests with comprehensive descriptions.

## Usage

```
/pr
```

## Behavior

1. Verify the current branch is a work branch based on `developments`, then
   analyze `developments...HEAD` and its merge base.
2. Identify every related issue. If the branch and commits do not provide an
   unambiguous issue number, ask the user before creating the PR.
3. Generate a Conventional Commit PR title whose type matches the branch type.
4. Fill the repository template at `.github/pull_request_template.md`, including:
   - Summary of changes
   - `Refs #<n>` for every related issue; never use `Closes #<n>`
   - Type of change
   - Manual test instructions
   - Screenshots when the change affects UI
5. Create the PR with `gh pr create --base developments`. Do not substitute a
   generic body or omit the issue references because downstream test workflows
   parse them.

## Requirements

- GitHub CLI (`gh`) installed and authenticated
- On a work branch, not `developments`, `user-acceptance-testing`, or `production`
