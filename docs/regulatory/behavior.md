# Regulatory Behavior

`Connect Diagnostics Regulatory` owns the medical-device regulatory source-of-truth masters.

## Ownership

- Product Registration owns the FDA registration record and effective Registered Product rows.
- Item retains classification and read-only current-coverage values derived from regulatory data.
- Renewal and variation history is recorded as registration actions rather than by overwriting historical registration facts.
- Regulatory transaction policy is resolved through `connect_diagnostics_core/api/erpnext/regulatory_transactions.py`.
- Historical transaction decisions use transaction-date coverage and persisted snapshots rather than re-reading an Item's current regulatory values.

## Alerts and reporting

`connect_diagnostics_core/api/erpnext/regulatory_alerts.py` owns expiry processing and digest notifications. Regulatory reports consume read-only reporting helpers and do not become alternate transaction-policy engines.

## Item boundary

The Item form exposes medical-device classification and current regulatory coverage. When an Item is not a medical device, the app clears medical-device-specific classification/current-coverage values according to the server validation rules.
