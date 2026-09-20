# Development Workflow — Connect Diagnostics Core

This document describes how a change moves from a work branch to production.
Automated tests, CI, code review, release accounting, and deployment verification
remain part of delivery. UAT scripts are maintained independently and are not
created, recorded, or used as gates by pull requests or promotion workflows.

---

## 1. Branches ↔ Environments

```
work branch ──PR──▶ developments ──PR──▶ user-acceptance-testing ──PR──▶ production
                       DEV / default       UAT                         PROD
```

| Branch                        | Role                             | Environment |
| ----------------------------- | -------------------------------- | ----------- |
| `feat/*`, `fix/*`, `chore/*`… | short-lived work branches        | local / dev |
| **`developments`** _(default)_| integration and released batches | DEV site    |
| **`user-acceptance-testing`** | promoted release batches         | UAT site    |
| **`production`**              | released, live                   | PROD site   |

- CI (`ci.yml` → **Server**, `linter.yml` → **Frappe Linter**) runs on every PR
  into `developments`, `user-acceptance-testing`, and `production`.
- All long-lived branches are protected: required checks (`Server`, `Frappe
  Linter`) plus one review. Admins may override for hotfixes.
- `release-please.yml` maintains a cumulative Release PR into `developments`.
  Merging it updates `__version__` and `CHANGELOG.md`, then publishes the matching
  `vX.Y.Z` tag and GitHub Release. Promotion PRs never bump the version.
- `deploy.yml` deploys DEV when a `vX.Y.Z` release is published and deploys UAT
  after a push to `user-acceptance-testing`. Production deployment remains manual.

---

## 2. Pull requests and issue tracking

- One issue normally maps to one PR; a PR may reference several related issues or
  none. Use `Refs #<n>`, never `Closes #<n>`.
- A work-branch PR targets `developments`, has a Conventional Commit title, and is
  ready only after required CI is green and a reviewer approves it.
- Do not create PR-linked test tasks, checklists, board fields, certification
  markers, bypass markers, or post-deployment testing status. UAT scripts are a
  separate process and do not control branch promotion.

---

## 3. Delivery flow

1. Create a compliant work branch from `developments`, implement the change, add
   the required automated tests, and open a PR to `developments` with `Refs #`.
2. After CI and review pass, merge the PR. Release Please accumulates merged work
   in its Release PR; a merge to `developments` does not deploy by itself.
3. When the release batch is ready, merge the Release PR. Verify that the published
   tag and GitHub Release point to that merge commit; this deploys the batch to DEV.
4. `$promote-uat` verifies that all commits are accounted for and that the batch has
   matching Release Please artifacts, then opens `developments →
   user-acceptance-testing`. After a verified UAT deployment, related source issues
   move to **UAT Deploy**.
5. `$promote-prod` verifies the complete, accounted UAT batch and release
   continuity, then opens `user-acceptance-testing → production`. After a verified
   PROD deployment, related source issues move to **PROD Deploy** and close.

## 4. Promotion gates

| Promotion                                  | Gate |
| ------------------------------------------ | ---- |
| work branch → `developments`               | CI green + one review |
| `developments` → `user-acceptance-testing` | complete, released, accounted batch |
| `user-acceptance-testing` → `production`   | complete, accounted UAT batch and release continuity |

---

## 5. Automated DEV and UAT deployment

`deploy.yml` connects as `erp` over SSH and runs
`bench update --apps connect_diagnostics_core --reset` after
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
secret `BENCH_PATH` in each environment to the Frappe Bench root. Configure these
Repository secrets:

- `SSH_PRIVATE_KEY` — the complete, passphrase-free private key authorized on both hosts.
- `SSH_KNOWN_HOSTS` — verified SSH host-key entries for both deployment hosts.

The workflow does not print these secrets. SSH requires a matching key from
`SSH_KNOWN_HOSTS`; it never learns or accepts a host key at deployment time.

### Deployment safety

Before deployment, the remote script verifies the Bench directory and `flock`,
initializes NVM, selects Node.js 24, and verifies the absolute paths and versions
of `bench`, `node`, `npm`, and `yarn`. It waits up to 60 minutes for an
environment-local deployment lock and runs from the Bench root:

```sh
cd "$BENCH_PATH" && bench update --apps connect_diagnostics_core --reset
```

DEV and UAT use separate concurrency groups. `cancel-in-progress` is disabled,
so a running deployment is never interrupted. Do not cancel a running deployment
or enable cancellation, because interrupting `bench update` can leave the remote
checkout or services inconsistent. A manually started `bench update` must wait
until the workflow's remote lock releases.
