# 0001: Database — Neon serverless Postgres

- **Status:** Accepted
- **Date:** 2026-09-11

## Context

Requirements: relational data with real integrity (FKs, unique constraints, cascades), ~0 PLN/month,
**no database administration** (no OS patching, no manual backups), scale to zero between uses.
Data volume is tiny (thousands of transactions per year, single user).

There is no relational database on GCP that scales to zero and is free. Facts behind this in
[`research/gcp-costs-2026-09.md`](../research/gcp-costs-2026-09.md).

## Decision

Use **Neon** (managed serverless Postgres, free plan) as the only operational database.
App and CLI connect with `DATABASE_URL` (SQLAlchemy 2.0 + psycopg 3). Schema is owned by Alembic.
The Neon password lives in GCP Secret Manager and is injected into Cloud Run.

## Alternatives considered

| Option | Why not |
|---|---|
| Cloud SQL Postgres (db-f1-micro) | ~$8–10/month + storage, never scales to zero; stop/start takes minutes |
| BigQuery as the main store | Serverless and free, but no enforced PK/FK, no autoincrement, DML latency ~1–2 s — wrong tool for OLTP |
| Firestore | Free, but NoSQL — poor fit for a relational schema and aggregations |
| Postgres on free e2-micro VM | $0, but US-only regions (data leaves the EU), 1 GB RAM, and OS/backup/security administration is on us |
| Postgres inside Cloud Run on a GCS FUSE volume | Unsafe: GCS FUSE has no file locking and is not POSIX-compliant → corruption |
| SQLite + Litestream on Cloud Run | ~0 PLN and minimal code, but single-writer only (`max-instances=1`, careful deploys), and the CLI cannot talk to the prod DB directly |
| Wake a DB via Pub/Sub on request | Cloud Run already wakes on HTTP; waking a VM/Cloud SQL takes tens of seconds to minutes |

## Consequences

- Good: real Postgres, zero ops, CLI works from the laptop against prod (same pattern as `menu_delivery`),
  deploys are independent of data.
- Bad / accepted risks:
  - Database is outside GCP → not covered by GCP IAM / Cloud Audit Logs.
  - Free plan has no IP allowlist → DB reachable from the internet, protected by password + TLS only.
  - Free plan limits (100 CU-hours/project/month, 0.5 GB storage) — fine for this app, but anything that
    keeps the compute awake (e.g. continuous logical replication) breaks it. See ADR 0004.
  - First query after idle pays a Neon wake-up.
- Follow-ups: backup/export strategy beyond Neon's built-in history (e.g. periodic `pg_dump` to GCS).
