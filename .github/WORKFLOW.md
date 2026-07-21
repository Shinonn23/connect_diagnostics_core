# Development Workflow — Connect Diagnostics Core

This document describes the **full-loop** development workflow for this project:
from an idea/bug all the way to production, how manual testing gates each
promotion, and the audited owner exception for UAT. It is the single source of
truth for _how we ship_.

---

## 1. Branches ↔ Environments

```
feature/* ──PR──▶ developments ──PR──▶ user-acceptance-testing ──PR──▶ production
   (work)            DEV / integration       UAT                          PROD
```

| Branch                          | Role                            | Environment |
| ------------------------------- | ------------------------------- | ----------- |
| `feature/*`, `fix/*`, `chore/*` | short-lived work branches       | local / dev |
| **`developments`** _(default)_  | integration + daily DEV testing | DEV site    |
| **`user-acceptance-testing`**   | user acceptance testing         | UAT site    |
| **`production`**                | released, live                  | PROD site   |

- CI (`ci.yml` → **Server**, `linter.yml` → **Frappe Linter**) runs on every PR
  into `developments`, `user-acceptance-testing`, and `production`.
- `auto-version.yml` bumps `__version__` **only** on PRs into `developments`
  (feature `+1 MINOR`, fix/chore `+1 PATCH`). Promotion PRs never double-bump.
- `deploy.yml` deploys `developments` to DEV and `user-acceptance-testing` to
  UAT after each push to those branches. Production deployment remains manual.
- All three long-lived branches are **protected**: required checks
  (`Server`, `Frappe Linter`) + 1 review. Admins may override for hotfixes.

---

## 2. Issue ↔ PR relationship

- **1 issue → 1 PR** is the default.
- **1 PR → many issues** is allowed when the changes are tightly related.
- A PR may have no issue when no related issue exists; write `None` in its
  **Related issues** section instead of creating a placeholder issue.
- When a PR has related issues, reference them with **`Refs #<n>`** — _not_
  `Closes #<n>`.

> ### ⚠️ Why `Refs`, not `Closes`
>
> We **merge first and test on `developments`**. When an issue exists,
> `Closes #n` would auto-close it the moment the PR merges — before testing. With
> `Refs #n` the issue stays **open** through the test phase and is closed by a
> human only after its manual tests pass. An open issue sitting in a _Test_ column
> = "not verified yet".

---

## 3. The full loop

States map 1:1 to the **Status** column on [Project board #6](https://github.com/users/Shinonn23/projects/6).

| #   | Board Status         | Meaning                                    | Branch / action       |
| --- | -------------------- | ------------------------------------------ | --------------------- |
| 1   | **TODO**             | triaged backlog                            | —                     |
| 2   | **DEV Ready**        | spec clear, prioritized, ready to pick up  | —                     |
| 3   | **Dev In progress**  | being implemented                          | `feature/*`           |
| 4   | **Dev review**       | PR open → `developments`; CI + code review | PR → developments     |
| 5   | **Test In progress** | merged; manual testing on DEV site         | `Refs #`, test on DEV |
| 6   | **Test Review**      | tests complete, QA verifying               | issue checklist ✅    |
| 7   | **UAT Deploy**       | promoted to UAT; user sign-off             | PR developments → uat |
| 8   | **PROD Deploy**      | released; pending bypass test may stay open | PR uat → production  |
| —   | **Hold**             | blocked / waiting                          | —                     |

Two extra board fields support testing:

- **Test Status** — `Not Tested` / `Testing` / `Passed` / `Failed`
- **Tested By** — who verified it

---

## 4. Step-by-step

### 4.1 Develop

1. Card in **DEV Ready** → move to **Dev In progress**, create `feature/<slug>`.
2. Open a PR into `developments`. In the body: `Refs #<issue>` (+ a manual-test
   checklist). Card → **Dev review**.
3. CI (`Server`, `Frappe Linter`) must be green; get 1 approving review.

### 4.2 Merge & test (on DEV)

4. Merge to `developments`. `auto-version` bumps the version. The issue stays
   **open**; card → **Test In progress**, **Test Status = Testing**.
5. Deploy `developments` to the DEV site. Run the issue's **test-step checklist**
   (the `- [ ]` task list in the issue body), ticking each step.
6. **Pass** → tick all steps, set **Test Status = Passed**, fill **Tested By**,
   move card → **Test Review**, then **close the issue**.
   **Fail** → set **Test Status = Failed**; open a **fix issue** (or push a small
   fix PR into `developments`). The original card stays in **Test In progress**
   until green.

### 4.3 Promote to UAT

7. When every issue in the release batch is **Test Status = Passed**, open a
   promotion PR **`developments → user-acceptance-testing`** (CI re-runs, no
   version bump). Merge & deploy the UAT site.
   - **Owner-only exception:** `Shinonn23` may explicitly invoke
     `$promote-uat --bypass-test "<reason>"`. The promotion process must inspect
     the complete batch, verify the authenticated GitHub login, and record the
     owner, reason, and every pending test in the PR body. It also writes an
     owner-authored `/test-bypass` marker on each source issue linking to that PR;
     both records must agree before the item can later reach PROD.
   - A bypass covers only the manual-test gate. It does not mark tests Passed,
     tick steps, close test tasks or source issues, or bypass unaccounted commits,
     CI, review, deployment verification, or UAT sign-off.
8. Move those cards → **UAT Deploy** after the promotion is merged and the UAT
   deployment is verified. Preserve the test fields and open state of bypassed
   items; preserve **PROD Deploy** instead for a remediated source already at that
   higher deployment state. Users run UAT sign-off.
   - Deferred dispatch and test results preserve an existing **UAT Deploy** or
     **PROD Deploy** Status instead of moving cards backward. The task records the
     exact environment, branch, and deployed commit under test; certification is
     valid only when `newyodsapad` posts `/test-pass — all steps verified on
     <environment> @ <full SHA>` matching that recorded deployment target. Bare,
     stale, or target-mismatched markers are invalid. Reusing a task for a
     different target replaces this metadata, resets its checklist, and records
     `/retest-start` before testing continues.
   - A deferred failure reopens its source issue and records `/test-fail` on the
     test task and source issue. The shared-task marker names the exact failing
     source issues; an unattributed active failure blocks PROD promotion. Each
     source marker invalidates every earlier `/uat-approve` for that item.
   - **UAT fail** → open a fix issue → re-enter the loop at **TODO / DEV Ready**.

### 4.4 Promote to PROD

9. After UAT sign-off that is newer than each source issue's own latest
   `/test-fail`, open a promotion PR. An active shared-task failure must first be
   mapped to its exact failing source issues. Map each source in a cumulative PROD
   batch to the UAT promotion that introduced its latest included developments PR;
   approval or bypass evidence from another UAT promotion does not apply. Normal
   promotion requires Passed plus target-matched tester certification, or a source
   `/test-bypass` marker matching that governing UAT PR's audited issue, owner, and
   reason. This evidence rule applies regardless of the Test Status enum. Before
   evaluating the current Git batch, scan existing PROD Deploy issues: any
   unresolved post-PROD failure blocks unrelated production batches until the
   exact deployed revision passes and the owner posts a newer `/uat-approve`.
   A remediation-only batch may deploy a fix while the hold remains only when
   every included developments PR directly `Refs` an actively held source, every
   commit is accounted for, and no unrelated PR is present. The PROD PR audits the
   remediation mapping; each held source is re-dispatched against the new PROD SHA
   after deployment.
   **`user-acceptance-testing → production`**. Merge & deploy PROD.
10. Move cards → **PROD Deploy**. Close only issues with Test Status = Passed
    and a valid target-matched `/test-pass` from `newyodsapad`; every bypassed or
    otherwise uncertified issue remains open regardless of its Test Status enum.
    A remediation hold also remains active until the new PROD target passes. The
    release is done.

---

## 5. Promotion gates (summary)

| Promotion                                  | Gate                                                |
| ------------------------------------------ | --------------------------------------------------- |
| `feature/*` → `developments`               | CI green **+** 1 review                             |
| `developments` → `user-acceptance-testing` | every batched issue Passed, or an audited owner-only manual-test bypass |
| `user-acceptance-testing` → `production`   | certified or audited per-source evidence; no unrelated PROD hold, except an audited remediation-only batch |

---

## 6. Automated DEV and UAT deployment

`deploy.yml` connects as `erp` over SSH and runs `bench update --reset` after
updates to the deployed branches:

| Trigger branch            | GitHub Environment | Host             |
| ------------------------- | ------------------ | ---------------- |
| `developments`            | `DEV`              | `34.143.156.218` |
| `user-acceptance-testing` | `UAT`              | `136.110.8.47`   |

The workflow can also be retried or started from the Actions UI with
`workflow_dispatch`; select `DEV` or `UAT` explicitly. Manual runs use the same
environment, credentials, concurrency group, and remote lock as automatic runs.

### Required GitHub configuration

Create GitHub Environments named exactly `DEV` and `UAT`. Set the Environment
secret `BENCH_PATH` in each environment; its initial value is
`/home/erp/frappe`. This is the Frappe Bench root containing `apps`, `sites`, and
`env`, not the path to the `bench` executable. Configure these Repository secrets:

- `SSH_PRIVATE_KEY` — the complete, passphrase-free `google_compute_engine`
  private key authorized on both hosts.
- `SSH_KNOWN_HOSTS` — verified SSH host-key entries for both deployment hosts.

The workflow does not print these secrets. SSH requires a matching key from
`SSH_KNOWN_HOSTS`; it never learns or accepts a host key at deployment time.
The `erp` account on each host must have NVM at `$HOME/.nvm/nvm.sh`, with Node.js
24, npm, and Yarn installed for that NVM user.

### Deployment safety

Before deployment, the remote script verifies the Bench directory and `flock`,
prepends `$HOME/.local/bin` and `/usr/local/bin` to the remote `PATH`, and requires
`command -v bench` to resolve to an absolute executable path. It initializes NVM
directly, selects Node.js 24, and checks the absolute executable paths and versions
of `node`, `npm`, and `yarn`. It then waits up to 60 minutes for an environment-local
deployment lock and runs from the Bench root:

```sh
cd "$BENCH_PATH" && bench update --reset
```

DEV and UAT use separate concurrency groups. `cancel-in-progress` is disabled,
so a running deployment is never interrupted; if several updates arrive, GitHub
keeps the newest pending run for that environment. Do not cancel a running
deployment or enable cancellation, because interrupting `bench update` can leave
the remote checkout or services inconsistent. Each job has a 120-minute timeout.

The remote lock coordinates deployments started by this GitHub workflow. A
manually started `bench update` does not acquire the lock and must wait until the
workflow run finishes.
