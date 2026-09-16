# Payment Request Approval

**Workflow: not currently defined by the app.** The custom Payment Request
Approval workflow was retired in the custom-workflow reset. The app no longer
owns any Workflow, approval role, approval-state field, or submit gate for
Payment Request or Payment Entry.

Current baseline:

- **Payment Request** and **Payment Entry** follow standard ERPNext behavior. The
  app does not require a Payment Request to be "approved", does not require
  approval evidence, and does not know whether a Payment Request workflow exists.
- **Payment Entry** keeps only the genuine, non-workflow custom validation in
  `connect_diagnostics_core/api/erpnext/payment_entry.py`: allocated Purchase/Sales
  Invoice references must share consistent accounting dimensions, and the Payment
  Entry's dimensions are synced to match. This is independent of any workflow.
- Removed with the reset: the `Payment Request Approval` Frappe Workflow and its
  states/transitions/action masters; the approver roles (`Executive P2P Approver`,
  `P2P Finance Verifier`) and their profiles and Payment Request `Custom DocPerm`
  rows; the `payment_approval_state` and `base_grand_total` fields; the
  `before_submit` gate that required allocation to approved Outward Payment
  Requests; and `setup/payment_approval.py` / `api/erpnext/payment_approval.py`.

A future payment approval design must start from a written Workflow Behavior
Specification (see the reset plan) rather than recreating the previous Payment
Request dependency. Approval of a payment intent is not the same event as
submitting the Payment Entry accounting transaction, and that distinction should
be settled in the specification before any workflow is rebuilt.
