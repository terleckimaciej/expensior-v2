# GCP & Neon — costs, limits, gotchas

- **Checked:** 2026-09-11. Re-verify anything you rely on if this is older than ~3 months.
- USD prices; region matters (Warsaw `europe-central2` is not the cheapest tier).

## Free tiers (per billing account unless noted)

| Service | Free | Notes |
|---|---|---|
| Cloud Run | 2M requests, 180k vCPU-s, 360k GiB-s /month | Free tier applied as a spending discount at Tier 1 prices. Request-based billing: idle non-min instances are not charged |
| BigQuery | 1 TiB queries, 10 GiB storage /month | |
| Firestore | 1 GiB, 50k reads / 20k writes / 20k deletes per day per project | |
| Cloud Storage | 5 GB-months | **US regions only** (us-east1, us-west1, us-central1) |
| Artifact Registry | 0.5 GB | Needs a cleanup policy |
| Secret Manager | 6 active versions, 10k access ops /month | |
| Cloud Build | 2,500 build-min/month (e2-standard-2) | |
| Cloud Logging | 50 GiB/project/month | |
| Compute Engine | 1 × e2-micro, 30 GB standard PD | US regions only; in-use external IPv4 is $0.005/h (~$3.65/month) |

## Paid things to know about

- **Cloud SQL** db-f1-micro: ~$8–10/month + storage; shared-core, no SLA, no CUDs, no scale to zero.
- **Cloud Monitoring alerting:** charges start **no sooner than 2027-09-01** — $0.35/month per metric
  reference in an alerting policy + $0.50 per 1M points returned. System metrics & dashboards: free.
- **Datastream:** CDC $2.00/GiB (first 2.5 TB tier); backfill free up to 500 GiB/month, then $0.40/GiB.
- **BigQuery CDC** background apply jobs bill on-demand without a reservation; tune `max_staleness`.
- **Load balancer** (needed for IAP in the past): fixed monthly cost — avoided via IAP directly on Cloud Run.

## To verify (numbers deliberately left blank)

Checked 2026-09-12: the Artifact Registry and Secret Manager pricing pages render client-side and could
not be read programmatically. These are structural facts worth knowing; fill in the rates from the
Pricing Calculator or the Billing console before relying on them.

- **Artifact Registry overage:** storage above the 0.5 GB free tier is billed per GB/month. This app's
  image is roughly 80–120 MB of compressed layers, so the free tier holds ~4 versions — hence the cleanup
  policy. Rate: __TBD__ (expected to be small enough to be irrelevant at this size; confirm).
- **Secret Manager:** billing counts **active secret versions**, so rotation that leaves old versions
  enabled quietly multiplies the cost — destroy superseded versions. Rate per active version/month and
  per access operation: __TBD__.

## Neon (free plan)

- 100 CU-hours/project/month, 0.5 GB storage/project, scale to zero after 5 min idle, no IP Allow.
- Logical replication: keeps compute awake while a subscriber is connected; inactive slots dropped after ~40 h;
  enabling it is irreversible; `REPLICATION` role only via Console/CLI/API.
- Requires TLS SNI; workaround for non-SNI clients: `options=endpoint%3D<id>` or password `endpoint=<id>;<pw>`.

## Storage options that don't work / need care

- **GCS FUSE volume on Cloud Run:** no file locking, not fully POSIX, last write wins, files staged fully
  in memory → never put Postgres (or a live SQLite file) on it.
- **Litestream** (SQLite → GCS replication): works on Cloud Run with `max-instances=1`; single writer only;
  flushes WAL on SIGTERM; tiny risk of losing the last second of writes on scale-down.

## IAP on Cloud Run

- Can be enabled directly on the service (covers `run.app` URL too), no load balancer.
- Projects outside a Google organization: enable from the console first, needs an OAuth client for external users.
- Cannot have IAP on both a load balancer and the Cloud Run service.

## Sources

- https://docs.cloud.google.com/free/docs/free-cloud-features
- https://cloud.google.com/run/pricing
- https://docs.cloud.google.com/run/docs/securing/identity-aware-proxy-cloud-run
- https://docs.cloud.google.com/run/docs/configuring/services/cloud-storage-volume-mounts
- https://cloud.google.com/products/observability/pricing
- https://cloud.google.com/datastream/pricing
- https://docs.cloud.google.com/bigquery/docs/change-data-capture
- https://cloud.google.com/vpc/pricing-announce-external-ips
- https://www.usage.ai/blogs/gcp/cloud-sql/pricing/
- https://neon.com/pricing
- https://neon.com/docs/guides/logical-replication-neon
- https://neon.com/docs/connect/connection-errors
- https://litestream.io/guides/gcs/
