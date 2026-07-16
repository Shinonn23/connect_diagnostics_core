# Development Workflow — Connect Diagnostics Core

This document describes the **full-loop** development workflow for this project:
from an idea/bug all the way to production, and how manual testing gates each
promotion. It is the single source of truth for _how we ship_.

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
- A PR references its issues with **`Refs #<n>`** — _not_ `Closes #<n>`.

> ### ⚠️ Why `Refs`, not `Closes`
>
> We **merge first and test on `developments`**. `Closes #n` would auto-close the
> issue the moment the PR merges — before testing. With `Refs #n` the issue stays
> **open** through the test phase and is closed by a human only after its manual
> tests pass. An open issue sitting in a _Test_ column = "not verified yet".

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
| 8   | **PROD Deploy**      | released to production; issue closed       | PR uat → production   |
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
8. Move those cards → **UAT Deploy**. Users run UAT sign-off.
    - **UAT fail** → open a fix issue → re-enter the loop at **TODO / DEV Ready**.

### 4.4 Promote to PROD

9. After UAT sign-off, open a promotion PR
   **`user-acceptance-testing → production`**. Merge & deploy PROD.
10. Move cards → **PROD Deploy**. The release is done.

---

## 5. Promotion gates (summary)

| Promotion                                  | Gate                                                |
| ------------------------------------------ | --------------------------------------------------- |
| `feature/*` → `developments`               | CI green **+** 1 review                             |
| `developments` → `user-acceptance-testing` | every batched issue **Test Status = Passed** on DEV |
| `user-acceptance-testing` → `production`   | UAT sign-off complete                               |

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

### Deployment safety

Before deployment, the remote script verifies the Bench directory and `flock`,
prepends `$HOME/.local/bin` and `/usr/local/bin` to the remote `PATH`, and requires
`command -v bench` to resolve to an absolute executable path. It then waits up to
60 minutes for an environment-local deployment lock and runs from the Bench root:

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
