# Payment Request Approval

- The code-managed Frappe Workflow `Payment Request Approval` applies only to
  `Payment Request.payment_request_type = "Outward"`. Inward requests use the
  standard submit path. Payment Entry Receive and Internal Transfer behavior is
  unchanged.
- `Company.low_value_payment_approval_limit` is expressed in company currency.
  Blank or zero sends every Outward request to the primary approver. With a
  positive limit, amounts below the limit use the low-value approver; amounts equal
  to or above it use the primary approver. The limit is snapshotted when approval
  is requested, so later Company changes do not reroute a pending request.
- `Payment Request.base_grand_total` is the requested amount in company currency.
  It equals `grand_total` for company-currency requests and otherwise uses the
  reference document's `conversion_rate`.
- After 24 calendar hours, the secondary executive is added as an approver. The
  original primary remains eligible; low-value requests also remain eligible for
  the accounting approver. The first approval or rejection completes the shared
  Workflow Action. Self-approval is disabled; creator, deadline, base amount, and
  limit snapshot are protected and revalidated server-side.
- Every submitted `Payment Entry.payment_type = "Pay"` must allocate its complete
  amount to one or more submitted, approved Outward Payment Requests whose company,
  party, and reference match. Requests are locked in sorted order and allocation is
  aggregated per request, allowing partial payments and multiple requests without
  concurrent overpayment. Pay entries without such references are rejected.
- The workflow, custom roles, profiles, fields, Custom DocPerm records, submit gate,
  and scheduler are managed in `connect_diagnostics_core/setup/payment_approval.py`
  and `connect_diagnostics_core/api/erpnext/payment_approval.py`. The scheduler
  checks escalation deadlines every five minutes.
- Setup and migration append the approved payment profile when a User already uses
  Role Profiles. For a User with no Role Profiles they add only the profile's roles
  directly so existing direct roles are not erased. Missing or disabled approver
  Users do not block a fresh installation; later migrations retry the assignment.
  Arirat receives primary plus low-value access, Sopha receives low-value access,
  and Sasin receives the secondary direct role until his later Role Profile migration.
- Workflow Actions work without email, but email delivery requires a configured
  Default Outgoing Email Account on each site.
- Frappe Workflow owns approval states, transitions, roles, and approval-required
  submission. If this managed Workflow is inactive, an Outward Payment Request
  bypasses approval and finalizes on submit; financial and reference validations
  remain enforced.
