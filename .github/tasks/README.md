# Active and paused work

This directory is the repository task registry. It contains work that is not yet accepted as
complete, including the current contract, dependency order, owned files, review findings,
test evidence, rollback constraints, and the exact next action.

Final accepted behavior belongs in `docs/`. A task may carry a frozen working
specification while implementation is active, but durable current knowledge moves to the
matching module/workflow documentation only after acceptance.

Each task directory must contain:

- a status overview with the last verified checkpoint;
- an implementation backlog with stable task IDs and dependencies;
- verification evidence that separates passing tests from unverified gates;
- an explicit Computer Use acceptance matrix for every user-visible or role/permission-sensitive flow, including actor, route, prerequisites, exact actions, expected/actual state, and durable evidence;
- explicit blockers and known P0/P1 review findings;
- a restart procedure that does not infer completion from source presence alone.

For implementation tasks, the default completion chain is:

`Plan ready → Implement → Focused automated tests → Independent code review → Fix/re-review loop → Final automated gates → Computer Use acceptance test → Final documentation → Documentation review → Accepted`.

Computer Use is an end-to-end acceptance layer, not a substitute for deterministic automated tests. A task that changes Desk-visible behavior, workflow transitions, permissions, role handoffs, or user-facing side effects is not accepted until its Computer Use matrix passes on the approved DEV target or the task explicitly records why that gate is not applicable.

After runtime acceptance, stable shipped behavior must be finalized under `docs/` before the task closes. Final documentation describes only current accepted behavior and durable operating constraints; it must not contain implementation backlogs, TODOs, blockers, branch/task status, temporary evidence, speculative future design, or historical working notes. Those remain in the active task record and are removed from the final documentation.

| Task | Status | Record |
| --- | --- | --- |
| Workflow baseline implementation | Planning checkpoint accepted; implementation record imported from workflow branch | [workflow-baseline-implementation](workflow-baseline-implementation/) |
