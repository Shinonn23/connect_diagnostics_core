# Leave Notifications

Two code-managed email templates support the leave lifecycle:

- `Leave Approval Notification` emails an open Leave Application to its leave approver.
- `Leave Status Notification` emails Approved, Rejected, or Cancelled results to the employee.

The templates live in `connect_diagnostics_core/fixtures/email_template.json` and store their HTML/Jinja content in `response_html` with HTML enabled.

The complete HR Settings Single DocType is not shipped as a fixture. Each site selects the two templates in HR Settings so environment-specific HR configuration is not overwritten.
