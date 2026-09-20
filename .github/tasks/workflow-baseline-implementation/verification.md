# Workflow baseline verification

## Reproducible audit checkpoint — 2026-09-17

| Field | Evidence |
| --- | --- |
| Repository | `/home/shinon/frappe/connect_diagnostics/apps/connect_diagnostics_core` |
| Branch / HEAD | `developments` / `2e80debe7349826a4f950a2d993517a595228f6b` |
| Documented intended target | `/home/erp/frappe`, absent; no runtime claims may be made for it |
| Audit target | bench `/home/shinon/frappe/connect_diagnostics`, site `local`; read-only evidence target, not an approved replacement |
| Runtime | Python 3.14.7 |
| Frappe | 16.31.0, `version-16`, `6a329d068416768ec47ccd3326b9cc95a8d7bf99` |
| ERPNext | 16.32.1, `version-16`, `21d187302045476f1ceb5d0d86219389ab1e75b8` |
| HRMS | 16.16.0, `f281e8b172ac8836ad89c59df65a922101103097` |
| ERPNext Thailand | 1.0.2, `d7065b163673645c14bf58422bc60a4efb7904ae` |
| App source commit | `2e80debe7349826a4f950a2d993517a595228f6b`; site reports 0.51.1 / `feat/prefix-custom-fields`, so equivalence is not inferred |
| Effective Workflow definitions hash | `518272f01831ce549998346c4b63bebaf67ec039f6c499e91259f8d2df7c54a2` (parents, ordered states and ordered transitions) |
| Effective Custom DocPerm query hash | `5e85bb7e514fb04d04a5da75c1cd9a1610a81d85cd3a5cab128bf46477e66606` |
| Effective `workflow_methods` hook query hash | `6a479b263e51fd684957b83f4549f279a471ffc59fcfca5abbcb91d0fa1f92f7` |

## Finding register

| ID | Finding | Evidence / classification |
| --- | --- | --- |
| F-01 | No deployed Stock Count model on audit site; native Stock Reconciliation present | Site metadata; legacy repository code is conflicting, not reusable runtime evidence |
| F-02 | Three active site Workflows exist for Stock Entry, Payment Entry and Asset Movement | Read-only Workflow query; site-owned desired state unapproved |
| F-03 | Workflow fixtures/config changes are dirty or untracked | Git status and hashes below; contested ownership |
| F-04 | Seven open legacy Workflow Actions remain | Read-only query: 2 Stock Count, 3 Purchase Order, 2 Material Request; pending policy required |
| F-05 | Salary Slip direct submit guard and native Payroll Entry path exist | App hook/HRMS source; broader review/recovery incomplete |
| F-06 | Planned SO/credit/CN/write-off/PO/PI/payment adapters are incomplete | Hook/API audit; native posting reusable, approval coverage missing |
| F-07 | Intended DEV is unavailable | Path check; target runtime/config/migration evidence missing |
| F-08 | Native approval primitives exist but do not supply business-identity delegation or idempotency | Frappe Workflow/Workflow Action, User Permission, Version, ToDo and locking source audit |

## Dirty content hashes

| Path | SHA-256 |
| --- | --- |
| `connect_diagnostics_core/hooks.py` | `e1a6832866ce7797bfbacfdd072f874714b93001ddd6e6049f5e7e0405107f12` |
| `connect_diagnostics_core/patches.txt` | `2f8106b170cce685c4c403913069aeaf05a1709728375d6c01e6802b7199fbc3` |
| `connect_diagnostics_core/setup/procure_to_pay.py` | `9ffa273a0c242d050346781796ba223fb4b556f5af022e2d696475e07ab59f3b` |
| `connect_diagnostics_core/setup/tests/test_workflow_reset.py` | `4ca711314259a6d22df6608b1de4e411dd8f11c3c34caf9d0e431f7176e0f301` |

| Historical untracked path at the 2026-09-17 checkpoint | SHA-256 |
| --- | --- |
| `connect_diagnostics_core/custom/asset_movement.json` | `a7132967429b8bd96b01fac62bd01904d9838f46a94c82023193e96b3e00ec4d` |
| `connect_diagnostics_core/custom/payment_entry.json` | `a695c2b70aabe3e1c7345ddb022cc1bb8c8e5b0a77aad39afcd75c5ce0c18e20` |
| `connect_diagnostics_core/connect_diagnostics_stock/custom/stock_entry.json` | `f944a8748af026d3cc06891307f29bef1ecc6310887810b33a3ab8090ac929e7` |
| `connect_diagnostics_core/fixtures/workflow.json` | `86acb281b8239f2ab062d9a3e0c7e1a954dcee6b9056d52ea0cbdb202da4fbc7` |
| `connect_diagnostics_core/fixtures/workflow_action_master.json` | `862ff7bc6fd89954dacbf1df9a7d4cf876030e6398b81ee083c8a5be6f7416a1` |
| `connect_diagnostics_core/fixtures/workflow_state.json` | `437fe606c2f5d5ba79452f1ab78b1c187654d650d230a4097b477e5dc06c1bd7` |
| `connect_diagnostics_core/patches/v1_0/remove_legacy_workflow_revise_actions.py` | `69e0765445cdd47562c3d6e6f3a78785f0a929e59af58376d2cc51c240413757` |
| `connect_diagnostics_core/patches/v1_0/rollback_remove_legacy_workflow_revise_actions.py` | `92a85076aab085935c4d152c8fd682fa3130f2e5d17939bda163e11088e094ed` |
| `connect_diagnostics_core/patches/v1_0/tests/test_remove_legacy_workflow_revise_actions.py` | `b9994ecdb4f725b96984b64d0c895a49d92a3ab9090b9b603afd3d5c56d3ad69` |

These `custom/*.json` rows are historical evidence only. Current workflow Custom Fields are
code-managed by `connect_diagnostics_core/setup/workflow_fields.py`; the old exported JSON files
are not a source of truth and are removed from the current tree.

Recompute every current-source hash before relying on this checkpoint.

Current canonical-reference hashes after the 2026-09-20 documentation taxonomy rewrite:

- `docs/accounting/payment-entry/README.md`: `697a8435f0eb44a51165bd7ae2cea6ebbf968e055d7f48dfbde0afe116c47682`
- `docs/stock/stock-reconciliation/README.md`: `19530932ad427613c2c7824bfc883e58d4717ccebd5285cba6a7133588b342ce`
- `docs/payroll/thai-payroll/README.md`: `e6df02d8890cccc6be8cc18c3db2f0cd4863e70745b430278d0ad5aa20418535`

The previous `docs/domains/*` hashes are historical only and no longer identify canonical files.

## Effective audit-site configuration

- Active: `Connect Asset Movement Approval` → Asset Movement.
- Active: `Connect Payment Entry Approval` → Payment Entry.
- Active: `Connect Stock Transfer Approval` → Stock Entry.
- Inactive: `Material Request Flow` → Material Request.
- Open Workflow Actions: two Stock Count, three Purchase Order, two Material Request. Identifiers
  and users are omitted from this repository record.
- The app declares Workflow transition callbacks in `hooks.py`; the dirty fixture/setup/permission
  changes must not be synced to shared DEV/UAT.

## Native primitive audit

- Frappe `get_transitions`, `apply_workflow`, `validate_workflow` and `has_approval_access` enforce
  site-owned transition state, allowed roles and document-owner self-approval. They do not model
  requester/delegator business identity or idempotency.
- Workflow Action persists pending actions and permitted roles but has no delegation,
  operation-key or immutable provenance contract.
- User Permission supplies current per-user scope; app adapters must still define which scope
  dimensions are relevant.
- Version and Workflow comments preserve change/audit evidence; Audit Trail compares amendment
  chains and is not an event ledger.
- Database `FOR UPDATE` is the critical-section primitive. `Document.lock` is an expiry-based file
  lock intended for longer background operations and is insufficient alone for approval races.
- ToDo is assignment/notification, not approval delegation.
- Existing Material Request APIs demonstrate `for_update=True` and downstream mutation locks;
  no reusable Item Request operation/delegation model was found.

## Reproduction commands

Current verification/re-test commands target the dedicated `local.test` site. The dated
2026-09-17 audit above remains historical evidence from `local` and must not be treated as a
current test result.

```sh
git branch --show-current
git rev-parse HEAD
git status --short
sha256sum <recorded-source-and-reference-paths>
bench --site local.test list-apps
bench --site local.test execute "frappe.get_all('Workflow', fields=['name','document_type','is_active'], order_by='name asc')"
bench --site local.test execute "frappe.get_all('Workflow Action', filters={'status':'Open'}, fields=['status','reference_doctype'], order_by='reference_doctype asc')"
bench --site local.test execute frappe.get_all --kwargs "{'doctype':'Custom DocPerm','filters':{'parent':['in',['Stock Entry','Payment Entry','Asset Movement']]},'fields':['parent','role','permlevel','read','write','create','submit','cancel','amend','report','export','print','email','share'],'order_by':'parent asc,role asc,permlevel asc'}" | sha256sum
bench --site local.test execute frappe.get_hooks --kwargs "{'hook':'workflow_methods'}" | sha256sum
{ bench --site local.test execute frappe.get_all --kwargs "{'doctype':'Workflow','fields':['name','workflow_name','document_type','is_active','override_status','send_email_alert','enable_action_confirmation','workflow_state_field'],'order_by':'name asc'}"; bench --site local.test execute frappe.get_all --kwargs "{'doctype':'Workflow Document State','fields':['parent','idx','state','doc_status','update_field','update_value','allow_edit','is_optional_state','avoid_status_override','send_email','evaluate_as_expression'],'order_by':'parent asc,idx asc'}"; bench --site local.test execute frappe.get_all --kwargs "{'doctype':'Workflow Transition','fields':['parent','idx','state','action','next_state','allowed','allow_self_approval','condition','send_email_to_creator'],'order_by':'parent asc,idx asc'}"; } | sha256sum
```

The installed Workflow Action schema has no `workflow_name` column. Queries must follow the
installed schema rather than old assumptions.

## Evidence invalidation rule

Recheck every finding affected by a change to target, commit, dirty-file hash, dependency commit,
effective Workflow/permission/hook configuration, policy revision, dataset or route scope. An old
audit remains historical evidence, not proof of the new state.

## Recovery taxonomy

- Transaction rollback: before commit, prove no partial DB fact remains.
- Native reversal: after commit, use supported cancel/amend/reversal and period/dependency rules.
- Configuration rollback: version desired state, pending-document mapping, permissions and
  repeated-apply behavior; never disable an old control before its replacement is verified.
- Environment restore: restore only with a reconciliation plan for valid later transactions.
- External recovery: bank, email and other external effects are not undone by DB rollback; retain
  evidence and retry only the failed ERP step.

## Gate status

- Planning checkpoint: accepted after graph correction and reproducible audit capture.
- G0: incomplete; target and scoped decisions in `decisions.md` remain open.
- G1–G4: not started/unsupported by current evidence.
- Runtime implementation: not authorized by this checkpoint.
