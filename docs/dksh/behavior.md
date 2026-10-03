# DKSH Behavior

`Connect Diagnostics DKSH` is the home for DKSH-specific reference masters.

Each reference master is keyed by its DKSH code and may optionally link to the corresponding Connect Diagnostics master. A blank link represents DKSH reference data that has not been mapped to a CD master. Reference data does not control the lifecycle or transaction eligibility of the CD master.

Shared validation and dashboard-link behavior lives in `connect_diagnostics_core/connect_diagnostics_dksh/reference.py`.

## DKSH Item

`DKSH Item` stores DKSH item/reference codes and may link to an ERPNext Item. The link is surfaced from the Item form's Connections rather than by duplicating DKSH reference fields onto Item.

## DKSH Customer

`DKSH Customer` stores the DKSH customer code plus DKSH-side name, tax, address, and contact reference data. When it has no linked ERPNext Customer, Desk exposes the conversion flow that opens a prefilled Customer form. Customer insertion links the source DKSH Customer under locking and may create a primary Billing Address from available DKSH address/tax data when the new Customer has no address.
