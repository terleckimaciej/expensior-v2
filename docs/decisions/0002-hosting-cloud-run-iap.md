# 0002: Hosting — one Cloud Run service behind IAP

- **Status:** Accepted
- **Date:** 2026-09-11

## Context

Personal finance data must never be publicly reachable. Budget ~0 PLN/month, no servers to manage,
"production at work" standards: IaC, least-privilege IAM, keyless CI/CD, observability, budget alerts.

## Decision

- **Compute:** a single Cloud Run service (UI and backend in one FastAPI-based app — NiceGUI by default, see ADR 0003),
  request-based billing, `min-instances=0`. Region `europe-central2` (Warsaw).
- **Access:** IAP enabled **directly on Cloud Run** (no load balancer). Projects without a Google
  organization need an OAuth client configured first.
- **Images:** Artifact Registry — **required**: Cloud Run can only deploy images from AR, not from an
  external registry. Cleanup policy for hygiene, not cost (overage is cents at this size).
  Same region as the service, so image pull does not add to cold start.
- **Secrets:** Secret Manager. Terraform owns the secret and its IAM binding, **never the value** — a
  `secret_version` with an inline value writes the password into the GCS state in clear text; values are
  injected out of band (`gcloud secrets versions add`). Runtime SA gets `secretAccessor` on that one secret.
  Rotation destroys superseded versions — billing counts *active* versions.
- **CI/CD:** GitHub Actions → Workload Identity Federation → deploy. No service account keys. The OIDC
  provider carries an attribute condition pinning it to this repository (without one, any GitHub repo can
  mint tokens for the SA), and deploy rights are bound to `v*` tag refs. Deploy SA and runtime SA are separate.
- **IaC:** Terraform, state in a versioned GCS bucket. Repo layout, module policy and plan-on-PR are out of
  scope here — see ADR 0005.
- **Governance:** one service account per workload with minimal roles; labels on every resource;
  billing budget with alert (alerts only — a budget does not cap spend); billing export to BigQuery.
- **Observability:** Cloud Monitoring dashboard on Cloud Run system metrics (free); structured JSON logs.

## Alternatives considered

| Option | Why not |
|---|---|
| External HTTPS Load Balancer + IAP | LB has a fixed monthly cost; direct IAP on Cloud Run makes it unnecessary |
| Separate API and UI services | Two things to deploy and secure for one user; the UI framework (ADR 0003) runs inside the same app, so no separate frontend service is needed |
| Public service + app-level login | Reinventing auth; IAP is free and managed |
| VM / GKE | Administration and fixed cost |
| Images in GHCR (as in `menu_delivery`) | Cloud Run cannot deploy from it; an AR remote repository would proxy it but still store — and bill — the layers in AR. GHCR fits `menu_delivery` because that runtime *is* GitHub Actions |

## Consequences

- Good: ~0 PLN (Cloud Run free tier covers this usage), nothing to patch, IAM + audit logs out of the box.
- Bad / accepted risks:
  - Cold start of a few seconds after idle (plus Neon wake-up).
  - Personal Gmail account = no Google organization → no Org Policies, folders or VPC-SC.
    Fix if wanted: Cloud Identity Free on an own domain (~50 PLN/year for the domain).
  - Cloud Monitoring alerting becomes paid no sooner than 2027-09-01 ($0.35/metric reference/month).
- Follow-ups:
  - ~~Decide dev/prod split~~ and ~~Terraform repo layout~~ — both settled in
    [ADR 0005](0005-environments-terraform-layout.md): one project, one service, pre-prod as a tagged
    no-traffic revision, a separate Neon dev project, flat Terraform root with var-files.
  - When mounting the Neon secret: `latest` (rotation without redeploy) vs a pinned version
    (deterministic deploys). Leaning `latest` for a single-user app.
