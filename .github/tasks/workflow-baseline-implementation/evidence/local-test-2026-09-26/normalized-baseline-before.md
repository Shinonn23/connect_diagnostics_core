# Normalized workflow baseline — before evidence

Captured: 2026-09-26, Asia/Bangkok

Target: local Bench `/home/user_2/frappe/connect_diagnostics`, site `local.test`.
This is the approved disposable automated/migration-rehearsal target. No shared DEV/UAT/production
write is represented by this evidence.

## Source checkpoint

- Integration branch: `feat/workflow-baseline-checkpoint-20260919`
- HEAD before integration: `e4abbc7e7de665ccbb4809196eb0af3af8c4f165`
- Predecessor route-manifest SHA-256:
  `61a876fa98dba63dba709b439199b275061d73f58ec4578de6cc79e31f90257e`
- Ordered runtime Workflow parent/state/transition SHA-256:
  `ca2393b719d2459db8b8b7606eaca9e2f5ee757824a65cb65879a94ccc290ee2`

The source tree existed in multiple dirty child worktrees. TSK-602 preserves every child worktree
and integrates only files named in its reviewed plan.

## Runtime Workflow inventory

The fresh read-only Workflow query found these rows:

| Workflow | DocType | Active |
| --- | --- | ---: |
| Connect Asset Disposal Blueprint | Asset | 1 |
| Connect Asset Movement Approval | Asset Movement | 1 |
| Connect Journal Entry Approval | Journal Entry | 1 |
| Connect Material Request Blueprint | Material Request | 0 |
| Connect Payment Entry Approval | Payment Entry | 1 |
| Connect Payroll Entry Blueprint | Payroll Entry | 1 |
| Connect Purchase Invoice Blueprint | Purchase Invoice | 1 |
| Connect Purchase Order Blueprint | Purchase Order | 1 |
| Connect Sales Invoice Credit Blueprint | Sales Invoice | 1 |
| Connect Sales Order Blueprint | Sales Order | 1 |
| Connect Stock Reconciliation Blueprint | Stock Reconciliation | 1 |
| Connect Stock Transfer Approval | Stock Entry | 1 |

Journal Entry is active in runtime but absent from the predecessor integration fixture/manifest.
Asset Disposal is the obsolete active route. Material Request is already inactive at this target.

### Exact canonical predecessor fingerprints

The normalization patch's ordered security shape produced these SHA-256 values from the live rows:

| Workflow | SHA-256 |
| --- | --- |
| Connect Stock Transfer Approval | `e6c93b71a66f5859f20cf2c5d077cbee22a7bc0b972513fd5f46d4a968a7aed6` |
| Connect Stock Reconciliation Blueprint | `4a64451600d4dc3e6077b080cf918e4c30044a2633dc2e35210e209a4be9e4eb` |
| Connect Asset Movement Approval | `bcd76f7c03365e6ce5a638544e3e8e6cfe82876f355bf4a22f918cb0487e9048` |
| Connect Journal Entry Approval | `bd7b53d0f267caa31230d0d3009e54e50832e029c2bbcf01fae508f022c93ad6` |
| Connect Sales Order Blueprint | `dd2d2074c1710ce4a8722061611caabc1d2807f9e2d04d8747d3757dea431a78` |
| Connect Sales Invoice Credit Blueprint | `5ec14155aa5e4d4644e859e6eec77f2b85377fcba8bba0245e215453377f4f1f` |
| Connect Purchase Order Blueprint | `8218346a1c2121f6405612d972ced112e12e9325014f89078ab79f3c897fede3` |
| Connect Purchase Invoice Blueprint | `cf8c9697c3d764f8cb33b167d1cb8035402f84eaf7720141d4552353331f54f1` |
| Connect Payment Entry Approval | `54a81a2dd3aba72a86e1ea5f85d43235ae0d9c3a9d5b87b41758052245f69a54` |
| Connect Payroll Entry Blueprint | `b18f2b8127e4cd5f40cee1defd7c598ceec629d68ab1697db084ffd7942a908f` |

The first rehearsal stopped before workflow mutation because three initially transcribed allowlist
values did not represent these live predecessors. Read-only comparison proved Asset Movement and
Purchase Order are exact ordered-shape matches to the `e4abbc7` integration-base fixture. Sales
Invoice Credit is an exact match to the reviewed `wf-tsk-526-credit-writeoff` fixture already
applied to `local.test`. The allowlist was corrected to these exact values; no wildcard or relaxed
comparison was introduced.

## Pending actions and documents

- Fresh `local.test` open Workflow Action query: zero rows.
- Documents with a non-empty workflow state:
  - Stock Reconciliation: one cancelled document and one rejected draft.
  - Every other canonical or retired target DocType: zero rows.
- Therefore `local.test` has no non-terminal Material Request, Asset Disposal, Emergency Movement,
  or other legacy document requiring disposition before rehearsal.

This does not supersede the 2026-09-17 `local` audit: it recorded two open Material Request, three
open Purchase Order, and two open retired Stock Count actions. Those seven records remain under the
preservation policy in `decisions.md`: no deletion, migration, fabricated event, or vocabulary
cleanup; atomically block fixture synchronization until authorized resolution.

The migration rehearsal later observed `Connect Material Request Blueprint` active with ordered
fingerprint `5c535b4ee549ecac6753402e145352b2884fe433c2372ee1d77141f0c90e2633`. This
exactly matches the committed `e4abbc7` fixture. The route had been inactive at the first capture;
the active state changed before the retirement preflight completed. The migration now recognizes
that exact active predecessor and still requires no open actions or non-terminal documents before
deactivation.

## Workflow fields and Property Setters

The read-only filtered Custom Field query confirmed `workflow_state` exists on every canonical
DocType and on legacy Material Request/Asset. Approval snapshot fields exist on several partially
implemented routes. Legacy `freeze_exception` and `freeze_exception_reason` exist on Stock Entry.
No Property Setter targeting `workflow_state` was returned.

TSK-602 may stop code-managing legacy fields but does not drop their stored columns or historical
values. Clean-install ownership for canonical fields is defined in setup code and verified by the
focused setup tests.

## Reproduction

The evidence used `bench --site local.test execute frappe.get_all` for Workflow, Workflow Document
State, Workflow Transition, open Workflow Action, filtered Custom Field/Property Setter, and
workflow-state/docstatus rows. Queries were read-only. The Workflow hash used the ordered command
documented in `verification.md`.

No database mutation occurred during this capture.
