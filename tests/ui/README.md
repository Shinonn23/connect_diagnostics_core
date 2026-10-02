# Playwright Desk acceptance

This suite drives Frappe's actual Desk forms and native Workflow menus. Each actor
gets an independent Playwright BrowserContext and a separate recording. Actions
are clicked through the visible page; the test does not call Frappe business APIs.

## Setup

Install the pinned project dependencies and Playwright's Chromium once:

```sh
npm ci
npx playwright install chromium
```

Create a scenario JSON by copying `workflow-scenario.example.json`, using a
disposable document on `local.test`, and specifying the exact configured states,
native Workflow action labels, user emails, and expected roles. Do not commit real
user identities or credentials. The example is a template, not executable test
data.

Provide the base URL, scenario path, and one password variable for each actor key.
For example, actor key `maker` reads `PLAYWRIGHT_PASSWORD_MAKER`. Set passwords
through the local secret manager or shell environment; never put them in the JSON,
command line, repository, or recorded evidence.

```sh
PLAYWRIGHT_SCENARIO_FILE="$PWD/tests/ui/local-payment-entry.json" \
PLAYWRIGHT_PASSWORD_MAKER="$TEST_MAKER_PASSWORD" \
PLAYWRIGHT_PASSWORD_CHECKER="$TEST_CHECKER_PASSWORD" \
PLAYWRIGHT_PASSWORD_APPROVER="$TEST_APPROVER_PASSWORD" \
npm run test:ui
```

The runner defaults to `http://dev.erp.connectdiagnostics.test`. Set
`PLAYWRIGHT_BASE_URL` only when the approved test Desk uses another address. The
test configuration maps the standard local test hostname to loopback for Chromium
without changing the host machine's resolver.

## Scenario format

Each scenario names one existing disposable document and a list of distinct
authenticated actors. `roles` may contain multiple required native Frappe roles,
which lets the journey verify that the document maker still cannot use a protected
approval action. Action steps click the visible native Workflow item and assert
the resulting state from the loaded Desk form. An `assert-unavailable` step asserts
that a protected action is absent for that actor in that state.

The test does not create users or documents. Prepare them using an approved setup
task or ordinary Desk actions, then record the exact identities and prerequisites
in the workflow task. Server-side native/unit tests remain responsible for API
bypass, ledger, transaction, concurrency, and migration behavior.

## Evidence

Each run creates a unique `test-results/playwright/<run-id>/` directory containing Playwright's report output,
an ordered JSON manifest, a screenshot after every asserted journey step, and one
unmodified WebM screen recording for each actor context. The report also attaches
the screenshots, manifest, and videos. Keep the entire output directory with the
workflow task evidence; do not trim or combine actor recordings. Credentials are
not included in the manifest. Failed runs keep diagnostic recordings but do not
count as acceptance.

Acceptance requires a completed scenario: every actor authenticated with the
declared roles, every configured action/state check passed, and all recordings and
screenshots exist. A test that was not run because a Desk, user, credential, or
disposable record is missing must be reported as blocked/not run, never as passed.
