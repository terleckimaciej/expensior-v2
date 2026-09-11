# 0004: Analytics — Datastream CDC from Neon to BigQuery

- **Status:** Deferred (learning / PDE exercise, not a product need)
- **Date:** 2026-09-11

## Context

At this data volume Postgres handles all analytics itself. BigQuery + Datastream is worth doing only
as practice for the GCP Professional Data Engineer exam and as a portfolio piece.

## Decision (when picked up)

Neon (OLTP) → Datastream (PostgreSQL source, logical replication) → BigQuery `raw` dataset →
SQL views / marts → Looker Studio or Cloud Monitoring.

**dbt is the modelling layer here** — staging models over the raw CDC tables, then marts. This is the one
place in the project where it belongs: [ADR 0007](0007-transformations-elt-in-postgres.md) deliberately
keeps it out of the operational path, so picking this track up is also what brings dbt into the repo.

**Run Datastream in a daily window, not continuously:** Cloud Scheduler resumes the stream once a
day, pauses it after it catches up.

## Why the window (hard constraints found in research)

- Neon: *"While a logical replication subscriber is connected, your Neon compute stays active and will not scale to zero."*
  Always-on 0.25 CU ≈ 182 CU-h/month > 100 CU-h free-plan limit.
- Neon removes inactive replication slots after ~40 hours → the window must run more often than every 40 h.
- Google docs don't say explicitly that a resumed stream continues from the slot position — **test it**.

## Setup gotchas

- Enabling logical replication in Neon (`wal_level=logical`) is **irreversible** for the project.
- The `REPLICATION` role must be created via Neon Console/CLI/API, not SQL.
- Neon requires SNI; if Datastream's client doesn't send it, put `endpoint=<endpoint_id>;<password>`
  in the password field (auth downgrades to `password`, connection stays TLS).
- Neon is not an officially listed Datastream source — configure it as self-managed PostgreSQL.
- BigQuery CDC upserts require primary keys; background merges bill on-demand → set `max_staleness` (e.g. 24 h).

## Cost

Datastream CDC $2/GiB (first tier) × megabytes/month ≈ cents; backfill free up to 500 GiB/month;
BigQuery within free tier (10 GiB storage, 1 TiB queries).

## Fallback

Nightly Cloud Run Job: extract from Neon → BigQuery load job (free). Simpler, no replication slot.
