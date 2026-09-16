# Active and paused work

This directory is the repository task registry. It contains work that is not yet accepted as
complete, including the current contract, dependency order, owned files, review findings,
test evidence, rollback constraints, and the exact next action.

Stable architecture belongs in `docs/domains/`. A task may carry a frozen working
specification while implementation is active, but it must move durable knowledge to the
matching domain reference when the task closes.

Each task directory must contain:

- a status overview with the last verified checkpoint;
- an implementation backlog with stable task IDs and dependencies;
- verification evidence that separates passing tests from unverified gates;
- explicit blockers and known P0/P1 review findings;
- a restart procedure that does not infer completion from source presence alone.

| Task | Status | Record |
| --- | --- | --- |
| Item Request / Asset Fulfillment v11 | Paused with implementation incomplete | [item-request-v11](item-request-v11/) |
