# Leave Notifications

- `Leave Approval Notification` emails an open Leave Application to its leave approver;
  `Leave Status Notification` emails Approved, Rejected, or Cancelled results to the employee.
- Both templates are code-managed in `fixtures/email_template.json` and store
  their Jinja/HTML content in `response_html` with `use_html` enabled.
- Do not fixture the complete HR Settings Single DocType. Select both templates
  in HR Settings per site so unrelated environment-specific HR configuration is not overwritten.
