<!--
  Workflow: we MERGE FIRST and TEST on `developments`.
  Use `Refs #` (not `Closes #`) so issues stay open until their manual tests pass.
  See .github/WORKFLOW.md
-->

## Summary

<!-- What does this PR change, and why? -->

## Related issues

Refs #<!-- issue number -->

<!-- add more: Refs #x, Refs #y if this PR covers several related issues -->

## Type of change

- [ ] Bug fix
- [ ] Enhancement
- [ ] New requirement
- [ ] Refactor / chore

## Manual test checklist (run on the DEV site after merge)

<!-- Copy the test steps from the linked issue(s); tester ticks these on the issue. -->

| Test step | Expected result | Pass |
| --------- | --------------- | :--: |
|           |                 |  ☐   |
|           |                 |  ☐   |

## Pre-merge checklist

- [ ] CI is green (`Server`, `Frappe Linter`)
- [ ] Self-reviewed the diff
- [ ] Uses `Refs #` (not `Closes #`) so the issue stays open for testing
- [ ] Target branch is `developments`
