# 0005: Environments and Terraform layout

- **Status:** Proposed
- **Date:** 2026-09-12

## Context

ADR 0002 left "decide dev/prod split" as a follow-up and pointed Terraform at the layout used in
`../cloud-data-platform`. Both need settling before any infrastructure exists.

Constraints: one developer, one user, ~0 PLN/month, and no Google organization (personal Gmail), which
makes some setup permanently manual. The data is the owner's own personal finance data — so the usual
"no production data outside production" reasoning does not apply unchanged, but anything *persisted or
shared* still leaves his control forever.

## Decision

**One GCP project, one Cloud Run service.** No separate dev project, no permanent dev service.

**Pre-production is a tagged revision, not an environment.** A Cloud Run revision is an immutable
snapshot of image digest + config; the service is a stable URL plus a traffic table over revisions.
Deploying with `--no-traffic --tag rc` yields a revision reachable at its own URL, behind the same IAP,
serving none of the real traffic. That covers what a laptop cannot: IAP, secret mounting, the runtime
service account, Cloud Run → Neon connectivity, and cold start.

**Promotion moves the artifact, not the revision object.** Because secrets are part of a revision, the
`rc` revision is pinned to the dev database forever and must never receive production traffic. Release is:

1. revision with digest X + **dev** secret, `--no-traffic --tag rc` — smoke test, safe to break;
2. migrate the production database as a separate, deliberate step (hence: migrations must be backward
   compatible, expand/contract — the old revision still serves traffic on the new schema);
3. revision with the **same digest X** + **prod** secret, `--no-traffic --tag next` — one read-only check;
4. `gcloud run services update-traffic expensior --to-tags next=100`.

Rollback is `--to-revisions <previous>=100`: seconds, no rebuild. Idle revisions cost nothing.

**Databases — three permanent, one throwaway:**

| Runtime | Database | Why |
|---|---|---|
| App on the laptop | Local Postgres (`docker compose`) | Daily driver: fast, offline, no CU-hours, destroy at will |
| App on the laptop, occasionally | Throwaway branch of the Neon **prod** project | Migration rehearsal on real-shaped data; deleted afterwards |
| `rc` revision | Neon **dev** project | Half-broken code *writes*; it must not be able to reach prod |
| Production revision | Neon **prod** project | — |

A separate Neon dev **project**, not a branch: Neon's limits (100 CU-hours, 0.5 GB) are per project, so a
dev branch would share — and could exhaust — production's compute budget. Free plan allows 100 projects
and 10 branches per project (checked 2026-09-12).

**Data placement.** Real data belongs anywhere ephemeral and local: the local Postgres, a prod branch.
Synthetic data is required wherever data is *persisted or shared* — committed test fixtures, logs, issues,
and LLM prompts. For fixtures the main reason is not privacy but test quality: a fixture should be small,
stable and built for one case, which a slice of a real statement never is. Git history is permanent and
this repo is intended as a portfolio piece. Data flows one way only: production → laptop (via `pg_dump`
or a branch). Nothing is ever pushed up into the production database except through the app's import path.

**Terraform, not OpenTofu** — parity with the tooling the owner uses at work is worth more here than the
licence question; this repo doubles as practice for work and for the GCP PDE exam.

**One flat root in `infra/`, no hand-written modules.** Modules pay off at two or three
instantiations, or when they enforce convention across teams; this is one service and roughly 150 lines of
resources, so a module layer would be pure indirection.

**Environment separation by var-file and backend-config, never workspaces:**

```bash
terraform init -backend-config=envs/prod.gcs.tfbackend
terraform plan -var-file=envs/prod.tfvars
```

The selected workspace is invisible state; the flag is visible in the command, in CI logs and in review.

**Bootstrap is separate and manual-ish.** The state bucket and the Workload Identity pool must exist
before CI can plan anything, so they are applied once from the laptop (`infra/bootstrap/`) and documented.
The IAP OAuth consent screen is clicked in the console — it cannot be Terraformed without an organization.

## Alternatives considered

| Option | Why not |
|---|---|
| Separate dev and prod GCP projects | The IAM boundary is real, but every extra project repeats the manual IAP OAuth consent screen, which no code captures. It does not protect quota either — Cloud Run's free tier is per *billing account*, not per project |
| A permanent `expensior-dev` Cloud Run service | A second copy of everything to maintain forever; unused environments rot and must be repaired before they can be trusted. A per-change revision is fresh by construction |
| Neon branch instead of a dev project | Shares the parent's 100 CU-hours and 0.5 GB; a runaway dev loop eats production's compute |
| Only a local Postgres, no cloud pre-prod | Cannot exercise IAP, Secret Manager, the runtime SA, or Cloud Run → Neon connectivity |
| Terraform workspaces per environment | Differences migrate into `terraform.workspace` conditionals, and a wrong `workspace select` applies dev values to prod with nothing visible in the diff |
| Own modules, `applications/` + `environments/` (the owner's layout at work) | Correct where the same shape repeats (many datasets); wrong for a single service |
| A copy of the root directory per environment | Roots drift: a resource added in dev goes missing in prod, and it surfaces months later |

## Consequences

- Good: one service, one IAP setup, one Terraform root, one budget. Pre-prod costs nothing and cannot be
  stale. Rollback is a traffic shift. Prod and dev credentials are physically distinct.
- Bad / accepted risks:
  - Migrations must be backward compatible — pre-prod and prod share a schema lineage.
  - The tested revision and the promoted revision are different objects; the guarantee is "same image
    digest", not "same revision". Step 3's read-only check is what covers the gap.
  - No IAM boundary between dev and prod resources; discipline replaces it (per-resource role grants only,
    never project-level).
  - The IAP consent screen exists outside Terraform, so the project cannot be recreated from code alone.
- Follow-ups:
  - Who owns the deploy — Terraform or CI — is open; see [ADR 0006](0006-deploy-ownership.md). It bears on
    the release flow above, since the `rc` and `next` revisions carry different secrets.
  - Whether the Neon free plan offers schema-only branches (the plans page does not say).
  - A persistent dev service is reconsidered if a long-running experiment starts (ADR 0004) or if someone
    else needs access.
