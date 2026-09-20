# Accounting Behavior

ERPNext remains the transaction and ledger owner for accounting documents. This app extends accounting behavior only through explicit configuration, validation, reporting, and integration boundaries; it does not implement a parallel GL posting engine.

## Shared invariants

- Standard ERPNext posting controllers own GL effects.
- Department and Territory use ERPNext Accounting Dimensions and flow through ERPNext's generated accounting-dimension fields.
- Payment Entry dimension validation must preserve consistency with allocated Purchase/Sales Invoice references.
- App code must not create substitute accounting transactions when a native ERPNext document is the accepted posting endpoint.

## Workflows

- [Accounting dimensions](accounting-dimensions/README.md)
- [Payment Entry](payment-entry/README.md)
