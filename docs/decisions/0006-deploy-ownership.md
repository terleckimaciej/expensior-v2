# 0006: Who owns the deploy — Terraform or CI

- **Status:** Proposed — options laid out, no verdict yet
- **Date:** 2026-09-12

## Context

In `google_cloud_run_v2_service` the `template` block **is** the revision: image digest, env vars,
secrets, scaling and service account. Terraform holds that template in its state.

If CI deploys a new image with `gcloud run deploy`, the live revision runs digest X2 while Terraform's
state and code still say X1. The next `terraform apply` — even one that only meant to add a label —
plans a new revision with the **old** image and silently rolls the deployment back. Two tools
would be shaping the same field.

This has to be settled before the first `infra/` commit, because it decides what the CI service account
is allowed to do and how the release flow in [ADR 0005](0005-environments-terraform-layout.md) is executed.

## Decision

None yet. Recorded so the question stays visible rather than being discovered the first time an apply
reverts a deploy.

## Options

### A. Terraform deploys

The image digest is an input variable. CI builds, pushes to Artifact Registry, then runs
`terraform apply -var="image=...@sha256:..."`.

- Good: one source of truth. What is running is what the repo says, and drift is impossible by
  construction. Rollback is a variable change plus an apply, reviewable as a diff.
- Bad: every deploy runs a full plan over all resources, so an unrelated console change can block a
  release; CI needs write access to all infrastructure, not just Cloud Run; plans get noisy.
- Friction with ADR 0005: the release flow needs a revision with the **dev** secret and, later, another
  revision with the **prod** secret, from the same digest. One `google_cloud_run_v2_service` resource
  describes one template, so two simultaneously-live revisions with different secrets are awkward to
  express — the `rc` step does not fit cleanly.

### B. CI deploys, Terraform ignores the image

Terraform owns the service's shape (service account, scaling, IAP, ingress); `gcloud` owns revisions and
traffic. The service resource carries
`lifecycle { ignore_changes = [template[0].containers[0].image, traffic] }` and a placeholder image for
the first apply.

- Good: deploys are fast and narrow — the CI identity needs only `run.developer` and
  `artifactregistry.writer`. The `rc` / `next` / traffic-shift flow from ADR 0005 is exactly what the
  CLI is built for, and rollback is one command.
- Bad: Terraform state no longer describes what is running; "what is deployed?" is answered by `gcloud`,
  not by the repo. `ignore_changes` also masks genuine drift in the ignored fields, and the split of
  ownership between the two tools lives in discipline rather than in a mechanism.

## What would settle it

- Whether the release flow in ADR 0005 stays as written (two revisions, two different secrets). If it
  does, option A needs a workaround and B is the natural fit.
- How much the "repo describes what runs" property is worth, given a single developer who is also the
  only person who could cause drift.
- Whether the CI identity should be able to touch anything beyond Cloud Run and Artifact Registry.

## Consequences (either way)

- The image is always referenced by **digest**, never by a moving tag — otherwise neither tool can tell
  whether anything changed.
- The choice determines the deploy service account's roles, so ADR 0002's "least privilege, separate
  deploy and runtime SAs" depends on it.
