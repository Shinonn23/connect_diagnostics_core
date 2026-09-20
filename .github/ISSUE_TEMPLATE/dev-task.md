---
name: "Task / Requirement"
about: "A development task, configuration, or new requirement"
title: "<MODULE>-000: "
labels: ["enhancement", "P2-Medium"]
---

| Field        | Value                                   |
| ------------ | --------------------------------------- |
| **Task-ID**  | <!-- e.g. ACC-006 -->                   |
| **Module**   | <!-- Accounting / Procurement / ... --> |
| **Reporter** |                                         |
| **Priority** | P2-Medium                               |

### Description

<!-- What needs to be built / configured, and why. -->

### Acceptance criteria

- [ ]

### Delivery criteria

- [ ] Implementation is complete for the approved bounded scope.
- [ ] Focused automated tests pass.
- [ ] Independent code review is complete; P0/P1 findings are fixed and re-reviewed.
- [ ] Final repository gates for the changed area pass.
- [ ] Computer Use acceptance test passes for every user-visible, workflow, permission, or role-handoff path affected by this task, or `N/A` is justified below.
- [ ] Final documentation is updated for changed shipped behavior, or `N/A` is justified below.
- [ ] Final documentation has been independently reviewed for accuracy and stale/duplicate content.

### Computer Use acceptance test

| Field            | Value                                      |
| ---------------- | ------------------------------------------ |
| Environment      | DEV unless explicitly authorized otherwise |
| Actor / role     |                                            |
| Route / document |                                            |
| Preconditions    |                                            |
| Test data        | Disposable / clearly named                 |

| #   | Action | Expected state / result | Actual | PASS/FAIL | Evidence |
| --- | ------ | ----------------------- | ------ | --------- | -------- |
| 1   |        |                         |        |           |          |

Required coverage when applicable: happy path, permission boundary, creator/reviewer/approver handoff, blocked or rejected path, visible downstream side effects, and recovery/retry behavior.

### Final documentation

- **Module:**
- **Workflow / process:**
- **Canonical path:** `docs/<module>/<workflow>/...`
- **Module behavior updated:** `docs/<module>/behavior.md` / N/A
- **Obsolete or duplicate docs removed/migrated:**

Final docs contain only accepted current behavior. Do not copy task status, implementation history, temporary test evidence, TODOs, or unimplemented design into `docs/`.
