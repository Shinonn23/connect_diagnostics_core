# Selling Behavior

ERPNext owns the standard Customer, Quotation, Sales Order, Delivery Note, and Sales Invoice transaction lifecycle. The app adds bounded master-data, requirement, print, and validation rules without replacing native posting behavior.

## Shared invariants

- Customer Code is the Customer document identity used by this implementation.
- Customer tax-invoice readiness is calculated from current master data; it is not a stored onboarding state.
- Sales document requirement gates are driven by Customer requirements and server-side validation.
- Print-time options are request-scoped and are documented under [Print](../print/behavior.md).

## Workflows

- [Customer master](customer-master/README.md)
- [Sales document requirements](sales-document-requirements/README.md)
