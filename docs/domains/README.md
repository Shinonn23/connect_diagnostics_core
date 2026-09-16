# Stable domain knowledge

Per-domain architecture and design records for `connect_diagnostics_core`. These are stable
"why it is built this way" references, not implementation backlogs. Read the relevant file
before changing that area, then read the matching active record in `.github/tasks/` when one
exists.

When stable architecture, behavior, or constraints change, update the matching file here in
the same change. Put unfinished work, blockers, ownership, and test evidence in
`.github/tasks/` instead.

| Domain                               | File                                                 |
| ------------------------------------ | ---------------------------------------------------- |
| Leave notifications                  | [leave-notifications.md](leave-notifications.md)     |
| Thai payroll                         | [thai-payroll.md](thai-payroll.md)                   |
| Accounting dimensions (Department)   | [accounting-dimensions.md](accounting-dimensions.md) |
| Payment Request approval             | [payment-approval.md](payment-approval.md)           |
| Customer onboarding & master data    | [customer-master-data.md](customer-master-data.md)   |
| Customer sales document requirements | [sales-requirements.md](sales-requirements.md)       |
| Regulatory module                    | [regulatory.md](regulatory.md)                       |
| DKSH module                          | [dksh.md](dksh.md)                                   |
| Print formats & audit log            | [print.md](print.md)                                 |
| Stock custom reset                   | [stock-count.md](stock-count.md)                     |

Item Request / Asset Fulfillment v11 remains active and is tracked in
[`../../.github/tasks/item-request-v11/`](../../.github/tasks/item-request-v11/).
