<!--
  Workflow: we MERGE FIRST and TEST on `developments`.
  When related issues exist, use `Refs #` (not `Closes #`) so they stay open
  until their manual tests pass. If no related issue exists, write `None`.
  See .github/WORKFLOW.md
-->

## Summary

<!-- What does this PR change, and why? -->

## Related issues

None

<!-- Replace None with Refs #x (one per related issue). Never create an issue
solely to populate this section, and never use Closes #. -->

## Type of change

- [ ] Bug fix
- [ ] Enhancement
- [ ] New requirement
- [ ] Refactor / chore

## Manual test checklist (run on the DEV site after merge)

<!-- Copy test steps from linked issues when present. For an issue-less PR,
document the verification steps directly here. -->

| Test step | Expected result | Pass |
| --------- | --------------- | :--: |
|           |                 |  ☐   |
|           |                 |  ☐   |

## Pre-merge checklist

- [ ] CI is green (`Server`, `Frappe Linter`)
- [ ] Self-reviewed the diff
- [ ] Related issues use `Refs #` (not `Closes #`), or the section says `None`
- [ ] Target branch is `developments`
