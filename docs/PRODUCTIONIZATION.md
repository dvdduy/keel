# Productionization Notes

Keel is a complete portfolio platform, not a production service. These are the
deliberate non-goals and the seam where the real implementation would attach.

## Auth and SSO

The API, CLI, and MCP surfaces do not enforce real identity. Production Keel
would put OIDC/SAML authentication at the entrypoints and pass an actor through
application use cases for audit events. The important seam already exists in the
use-case boundary: submit, run, override, acknowledge, and diagnose operations
can all receive an authenticated actor without moving policy into adapters.

## Tenant RBAC and Quotas

Keel models teams and owners, but it does not enforce tenant isolation, per-team
quotas, or role-based authorization. Production enforcement belongs in an
authorization policy service called from entrypoints before use cases mutate
state. Quotas are the harder half because they need metering across runs,
warehouse usage, incident volume, and retained history.

## Disaster Recovery and Multi-Region

The control plane is written as ordinary repository ports, and the local build
uses Postgres-compatible storage plus DuckDB for the warehouse seam. Production
DR would require managed backups, restore drills, replicated object storage for
artifacts, and region-aware warehouse adapters. The repository and warehouse
ports are the integration points; the demo intentionally does not pretend that a
single local DuckDB file is an HA data plane.

## Cloud Deploy

There is no Terraform, Kubernetes chart, secret manager integration, or managed
warehouse deployment. A production deployment would split the API/MCP server,
worker execution, scheduler, and agent runtime into separately scalable services.
The current adapter boundaries keep that possible, but the repo stops at the
local and CI-verifiable implementation.

## Regulatory Certification

Keel is designed with auditability and contract safety in mind, but it is not
SOC 2, PCI, or SOX certified. Certification would require operational controls:
access reviews, evidence capture, change management, key rotation, retention
policies, and incident procedures. Those are organizational systems around the
software, not code that belongs in this capstone.

## Reverse ETL

Keel governs data production and quality before downstream consumption. It does
not push warehouse data back into SaaS tools. Reverse ETL would add connector
adapters, destination-specific idempotency, consent policy, and failure handling
that are separate from the core contract and lineage story.

## Time Travel

The warehouse port supports current-state reads needed for checks and freshness.
It does not expose historical table snapshots. Production time travel belongs in
the warehouse adapter contract once Keel needs backfills, reproducible incident
replay, or point-in-time contract validation.

## Undo and Replace Limitation

Rollback is best-effort compensation over local execution steps. It handles the
demo quarantine path, but it is not a full transactional undo across external
systems. Production replace/rollback needs versioned artifacts, idempotent
publishing, staged swaps, and explicit recovery semantics for every adapter.

## DECIMAL(p,s) Latent Bug

The current contract model treats `decimal` as a coarse type and DuckDB mapping
collapses physical `DECIMAL(p,s)` into that logical type. Production compatibility
must track precision and scale because `DECIMAL(18,2) -> DECIMAL(10,2)` is a
narrowing even though both are decimals. The fix belongs in `ColumnType` or an
extended type descriptor plus a richer compatibility widening table.
