# Mercury

> A cloud-native data foundation platform demonstrated through a modern commerce implementation.

Mercury is an end-to-end cloud-native data foundation platform that demonstrates how modern organizations can build reusable, scalable analytics infrastructure.

Rather than building project-specific pipelines, Mercury focuses on creating a standardized data foundation that transforms raw operational data into trusted, reusable data products.

---

## Why Mercury?

Many organisations invest significant engineering effort preparing data before they can generate business value.

Operational data often arrives from multiple systems in inconsistent formats, transformation logic is duplicated across projects, and analytical solutions become tightly coupled to individual use cases.

Mercury demonstrates an alternative approach.

Instead of building isolated pipelines, Mercury establishes a reusable data foundation that standardises ingestion, modelling, testing and publishing so future analytics, reporting and machine learning solutions can build upon the same trusted platform.

---

## Design Philosophy

Mercury is intentionally built as if it were the internal data platform of a growing e-commerce company.

The platform prioritises reusable capabilities over project-specific solutions.

Every architectural decision is evaluated against one question:

> Does this strengthen the platform for future use cases?

The goal is not to build another data pipeline.

The goal is to build a reusable data foundation.

Mercury is built on one simple belief:

> Future innovation should focus on creating business value—not rebuilding data foundations.

---

## Overview

Mercury follows a layered architecture that separates source delivery, operational ingestion, immutable Raw storage, warehouse loading, standardisation, business modelling and data product generation.

Each layer has a clearly defined responsibility, allowing the platform to evolve incrementally while maintaining consistency across data products.

The ingestion platform currently supports:

- eight reusable Olist source connectors;
- interchangeable local and Google Cloud Storage backends;
- immutable Raw landing with SHA-256 integrity metadata;
- realistic initial and incremental source-delivery simulation;
- historical replay across business dates;
- explicit BigQuery Raw loading;
- partition-aware transactional loading;
- one-off reference-table loading;
- durable append-only source-level replay state;
- monotonic logical-completion semantics;
- stage-aware targeted recovery planning and execution;
- reuse of validated immutable Raw artifacts for warehouse-only recovery;
- append-only Raw artifact provenance;
- append-only warehouse-load provenance;
- exact Raw-artifact-to-warehouse-load lineage;
- metadata-only inspection of GCS Raw artifacts;
- metadata-only inspection of BigQuery Raw partitions;
- provenance-backed reconciliation of physical and control-plane state;
- finite structural reconciliation outcomes for missing or conflicting evidence;
- safe handling of ambiguous recovery cases without destructive guesses;
- least-privilege and data-leak-prevention security boundaries.

The ingestion and Raw-platform foundation is now complete for Mercury's current scope.

This architecture enables new analytical use cases to reuse existing platform capabilities rather than rebuilding ingestion and transformation logic for every project.

---

## Architecture

```text
┌──────────────────────┐
│       Sources        │
│                      │
│ APIs • Files • SaaS  │
└──────────┬───────────┘
           │
           ▼
┌──────────────────────┐
│   Source Delivery    │
│                      │
│ Initial • Incremental│
└──────────┬───────────┘
           │
           ▼
┌──────────────────────┐
│      Connectors      │
│                      │
│ Validate • Metadata  │
└──────────┬───────────┘
           │
           ▼
┌──────────────────────┐
│ Immutable Raw Landing│
│                      │
│ Local / Cloud Storage│
└──────────┬───────────┘
           │
           ▼
┌──────────────────────┐
│     BigQuery Raw     │
│                      │
│ Reference + Daily    │
└──────────┬───────────┘
           │
           ▼
┌──────────────────────┐
│       Staging        │
│       Dataform       │
└──────────┬───────────┘
           │
           ▼
┌──────────────────────┐
│      Canonical       │
│      Data Model      │
└──────────┬───────────┘
           │
           ▼
┌──────────────────────┐
│    Data Products     │
└──────────┬───────────┘
           │
           ▼
 Dashboards • APIs • Apps
```

The main data path is complemented by a separate operational control plane:

```text
                 Replay State
                      +
             Artifact Provenance
                      +
          Warehouse Load Provenance
                      ↓
          Targeted Recovery Planning
                      ↓
             Recovery Execution
                      ↓
       Provenance-Backed Reconciliation
```

Operational replay and provenance metadata are maintained separately from business Raw data so orchestration state does not become part of the source-faithful Raw layer.

> Detailed platform and deployment architecture diagrams will be added as the platform evolves.

---

## Core Capabilities

### Implemented

- Standardised source ingestion
- Eight reusable source connectors
- Shared CSV connector abstraction
- Storage-backend abstraction
- Local Raw landing
- Google Cloud Storage Raw landing
- Immutable create-only Raw storage
- SHA-256 integrity metadata
- Initial and incremental source simulation
- Historical source replay
- BigQuery Raw loading
- Partitioned transactional Raw tables
- One-off reference Raw tables
- Explicit BigQuery schemas
- Source-level replay-state domain model
- Append-only BigQuery replay-state persistence
- Replay-runner state integration
- Latest-attempt vs monotonic logical-completion semantics
- Source-level failure isolation
- Stage-aware targeted recovery planning
- Safe targeted recovery execution
- Validated immutable Raw artifact reuse
- Append-only Raw artifact provenance
- Append-only warehouse-load provenance
- Provenance-linked warehouse loading
- GCS metadata inspection without payload downloads
- BigQuery partition metadata inspection
- Provenance-backed physical-state reconciliation
- Structural blocked-reconciliation reasons
- Zero-physical-work reconciliation of previously successful operations
- Monotonic logical-completion derivation
- Security hardening and data-leak prevention
- Automated regression testing

### Planned

- Dataform staging transformations
- Canonical business modelling
- Reusable data products
- Data quality validation
- Infrastructure as Code
- Production orchestration
- Platform observability
- Automated deployment
- Operational runbooks and manual-review procedures

---

## Source Delivery Model

Mercury distinguishes between sources that behave like reference snapshots and sources that arrive incrementally over time.

### Initial / Reference Sources

```text
customers
products
sellers
geolocations
```

These are currently modelled as one-off initial deliveries and loaded into non-partitioned BigQuery Raw tables.

They deliberately remain outside the transactional replay and targeted-recovery lifecycle defined by ADR-010.

### Incremental Sources

```text
orders
order_items
payments
reviews
```

These are delivered at business-date grain and loaded into date-partitioned BigQuery Raw tables.

Orders define the transactional parent population for order items and payments.

Reviews are simulated independently using their own source arrival date.

A valid daily delivery may contain zero business records. Header-only source files remain valid deliveries.

### Delivery Date vs Ingestion Date

Mercury distinguishes the business date represented by a delivery from the date on which the artifact is ingested.

For the Olist historical simulator, daily deliveries intentionally simulate next-day arrival:

```text
delivery_date = D
ingestion_date = D + 1 day
```

This rule belongs only to the Olist source-delivery simulation boundary.

Generic connectors, storage, warehouse loading, replay, recovery and reconciliation components do not derive this relationship themselves.

For transactional data:

```text
delivery_date
     ↓
BigQuery partition_date
```

while:

```text
ingestion_date
     ↓
GCS Raw landing path
```

This separation allows the historical Olist dataset to simulate realistic daily ingestion without embedding simulation-specific timing assumptions into reusable ingestion infrastructure.

---

## Historical Replay

Mercury supports deterministic historical replay of incremental source deliveries.

A replay date coordinates the expected independent sources:

```text
orders
order_items
payments
reviews
```

through:

```text
Source Delivery
      ↓
Connector Ingestion
      ↓
Immutable GCS Raw Landing
      ↓
BigQuery Raw
```

Historical replay validates complete source membership before ingestion and preserves the distinction between:

```text
zero business records
```

and:

```text
zero source deliveries
```

A valid source delivery containing zero records is supported.

An empty source-delivery batch is invalid.

Source failures are isolated where safe. A failure affecting one source does not prevent independent sibling sources for the same business date from completing their eligible work.

Historical replay stops progression to later dates only after all safe work for the current date has been attempted and the date is determined to remain logically incomplete.

The historical replay implementation has been integration-tested against real Google Cloud Storage and BigQuery resources.

---

## BigQuery Raw Layer

Mercury's BigQuery Raw layer preserves source-faithful data while adding warehouse-level structure required for scalable downstream processing.

### Transactional Sources

```text
orders
order_items
payments
reviews
```

are stored in date-partitioned Raw tables.

Historical replay routes each daily source delivery to the corresponding BigQuery partition using the business `delivery_date` as the warehouse `partition_date`.

### Reference Sources

```text
customers
products
sellers
geolocations
```

are loaded as one-off Raw reference tables.

The Raw loader uses explicit schemas rather than schema autodetection.

BigQuery loading remains separate from connector ingestion so storage and warehouse responsibilities remain independently testable and replaceable.

---

## Replay State and Recovery

Mercury supports durable source-level historical replay state and stage-aware targeted recovery through ADR-010.

Replay state is append-only and stored separately from business Raw data.

The logical replay identity is:

```text
delivery_date + source_object
```

while each execution attempt receives a `run_id` and each persisted state transition receives a unique `event_id`.

The platform deliberately distinguishes:

```text
latest execution attempt
          ≠
logical source completion
```

Once a source has successfully reached `SUCCESS | WAREHOUSE`, a later failed attempt does not erase that earlier durable completion.

### Recovery Planning

Targeted recovery begins with a pure planning layer:

```text
Replay history + recovery evidence
        ↓
RecoveryPlanner
        ↓
RecoveryPlan
```

The planner can select:

```text
SKIP
INGEST_AND_LOAD
LOAD_ONLY
RECONCILE
MANUAL_REVIEW
```

Each action represents the minimum safe work justified by the available evidence.

### Recovery Execution

```text
RecoveryPlan
      ↓
RecoveryExecutor
      ↓
safe physical work
      ↓
durable replay-state events
      ↓
date-completeness re-derivation
```

`RecoveryExecutor` handles the actions conservatively:

- `SKIP` performs no physical work;
- `INGEST_AND_LOAD` repeats ingestion and then loads the resulting immutable Raw artifact;
- `LOAD_ONLY` reuses an existing validated immutable `gs://` Raw artifact without rerunning ingestion;
- `RECONCILE` delegates ambiguous physical/control-plane state to provenance-backed reconciliation;
- `MANUAL_REVIEW` remains blocked when the platform does not possess enough deterministic evidence to act safely.

Recovery attempts use a fresh `run_id`.

Ordinary source failures remain isolated so unrelated safe work can continue, while replay-state and provenance persistence failures fail closed.

Date completeness is re-derived from durable successful-completion history after recovery.

---

## Provenance and Physical Lineage

ADR-010 Phase 3C introduces durable provenance for the physical data path.

Mercury records two complementary provenance entities:

```text
RawArtifactProvenance
```

and:

```text
WarehouseLoadProvenance
```

A Raw artifact provenance record captures the identity and immutable physical characteristics of a landed source artifact, including:

```text
provenance_id
run_id
delivery_date
source_object
ingestion_date
gcs_uri
checksum
file_size_bytes
record_count
recorded_at
```

A warehouse-load provenance record captures the resulting BigQuery materialisation:

```text
load_id
provenance_id
run_id
delivery_date
source_object
destination
partition_date
output_rows
job_id
recorded_at
```

The `provenance_id` links the warehouse materialisation to the exact immutable Raw artifact from which it was produced.

This produces explicit physical lineage:

```text
Source Delivery
      ↓
Raw Artifact
      ↓
RawArtifactProvenance
      ↓
Warehouse Load
      ↓
WarehouseLoadProvenance
      ↓
BigQuery Raw Partition
```

A single logical source job may have multiple execution attempts and therefore multiple provenance records over its history.

This append-only model preserves traceability without mutating or replacing earlier evidence.

---

## Provenance-Backed Reconciliation

Reconciliation exists for situations where replay state alone cannot prove whether a previously attempted physical operation actually completed successfully.

Rather than guessing or blindly repeating physical work, Mercury compares durable provenance with independently observable cloud metadata.

```text
RecoveryAction.RECONCILE
          ↓
   RecoveryReconciler
       ↙       ↘
      ↙         ↘
GCS Inspector  BigQuery Inspector
      ↘         ↙
       ↘       ↙
      Provenance
          ↓
 CONFIRMED / BLOCKED
```

### Raw Artifact Inspection

`GCSArtifactInspector` performs metadata-only inspection.

It validates evidence such as:

```text
object existence
SHA-256 checksum metadata
object size
ingestion-date path identity
```

The reconciler does not download Raw payloads to prove their existence or integrity.

### Warehouse Inspection

`BigQueryInspector` inspects warehouse metadata through:

```text
INFORMATION_SCHEMA.PARTITIONS
```

rather than reading Raw business rows.

It validates:

```text
partition existence
destination identity
row count
```

### Reconciliation Evidence

Automatic confirmation requires the complete evidence chain to agree:

```text
WarehouseLoadProvenance exists
            ↓
linked RawArtifactProvenance exists
            ↓
logical identities agree
            ↓
GCS checksum agrees
            ↓
GCS size agrees
            ↓
GCS ingestion_date path agrees
            ↓
BigQuery destination agrees
            ↓
BigQuery row count agrees
            ↓
artifact record count agrees with warehouse output
            ↓
        CONFIRMED
```

Zero-record deliveries remain valid:

```text
artifact.record_count = 0
warehouse.output_rows = 0
observed BigQuery rows = 0
```

can reconcile successfully.

If required evidence is absent, malformed or contradictory, reconciliation returns a finite structural `BLOCKED` outcome rather than inventing a conclusion.

Infrastructure failures are treated separately from ordinary blocked evidence and fail closed through the recovery execution boundary.

### Confirmed Reconciliation

A confirmed reconciliation proves that the required physical work already exists.

Therefore Mercury performs:

```text
0 connector executions
0 GCS writes
0 BigQuery loads
```

and appends exactly one:

```text
SUCCESS | WAREHOUSE
```

replay-state event for the reconciliation execution.

Mercury does not fabricate a `RUNNING | WAREHOUSE` event because no new warehouse operation actually occurred.

---

## Security by Design

Mercury is designed to process customer and source data using explicit, least-privilege security boundaries.

Key security properties include:

- **Dedicated runtime identity** — deployed workloads use a bounded `mercury-runtime` service account rather than developer credentials.
- **Least-privilege cloud access** — runtime permissions are limited to the GCS and BigQuery operations required by ingestion and orchestration.
- **Immutable Raw landing** — Raw objects are written using create-only generation preconditions, preventing accidental replacement of existing artifacts.
- **Restricted destructive access** — the runtime identity cannot delete Raw GCS objects or administer storage infrastructure.
- **Infrastructure/runtime separation** — datasets, buckets, and IAM are provisioned outside the application runtime. Mercury cannot create arbitrary BigQuery datasets.
- **Explicit dataset access** — sensitive datasets do not rely on broad `projectReaders`, `projectWriters`, or `projectOwners` dataset ACLs.
- **Safe operational errors** — persisted failure metadata contains Mercury-authored operational descriptions rather than raw provider or exception text that could contain sensitive data.
- **Safe provenance errors** — BigQuery provenance insertion failures expose static Mercury-authored messages rather than provider insertion payloads.
- **Metadata-only reconciliation** — reconciliation validates physical state without downloading Raw business payloads or querying Raw rows.
- **Non-destructive recovery** — reconciliation confirms or blocks existing state rather than mutating evidence to force consistency.
- **Keyless runtime authentication** — Mercury's runtime model does not require long-lived downloaded service-account keys.

Security decisions, audits, and validation evidence are documented in:

```text
architecture/decisions/ADR-011-Data Security, Privacy, and Data-Leak Prevention.md
docs/security/
```

---

## Technology Stack

| Capability | Technology | Purpose |
| --- | --- | --- |
| Programming | Python | Ingestion, orchestration & utilities |
| Raw Object Storage | Google Cloud Storage | Immutable source landing |
| Warehouse | BigQuery | Raw & analytical storage |
| Transformations | Dataform | SQL modelling |
| Infrastructure | Terraform | Infrastructure as Code |
| Orchestration | Cloud Run + Scheduler | Automated ingestion |
| BI | Looker Studio | Dashboards |
| Applications | Streamlit | Internal tools |

---

## Repository Structure

```text
.
├── architecture/
├── docs/
├── ingestion/
├── transformations/
├── infrastructure/
├── app/
├── tests/
├── scripts/
├── README.md
├── PROJECT_CHARTER.md
├── ROADMAP.md
└── LICENSE
```

The ingestion package contains the implementation of:

```text
connectors
storage backends
source-delivery providers
source simulation
historical replay orchestration
BigQuery Raw loading
replay-state persistence
recovery planning
recovery execution
artifact provenance
warehouse-load provenance
GCS artifact inspection
BigQuery warehouse inspection
provenance-backed reconciliation
shared connector construction
```

The implementation deliberately separates these responsibilities rather than concentrating ingestion, storage, warehouse loading and operational recovery into one orchestration component.

---

## Roadmap

### Phase 0 — Foundation

- [x] Project Charter
- [x] Repository Structure
- [x] Architecture Documentation
- [x] Foundational Architecture Decisions

### Phase 1 — Ingestion

- [x] Reusable Source Connector Framework
- [x] Shared CSV Connector Abstraction
- [x] Local Raw Landing Zone
- [x] Storage Abstraction
- [x] Cloud Storage Raw Landing
- [x] Initial and Incremental Source Simulation
- [x] Historical Replay Orchestration
- [x] Historical Replay Integration Validation

### Phase 2 — Cloud Raw Platform

- [x] Cloud Storage Raw Landing Zone
- [x] BigQuery Raw Dataset
- [x] BigQuery Raw Loading
- [x] Transactional Partition Loading
- [x] Reference Table Loading
- [x] Replay-State Persistence Foundation
- [x] Replay Runner State Integration
- [x] Security Hardening and Data-Leak Prevention
- [x] Targeted Replay Recovery Planning
- [x] Targeted Replay Recovery Execution
- [x] Raw Artifact Provenance
- [x] Warehouse Load Provenance
- [x] Physical Artifact Inspection
- [x] Provenance-Backed Recovery Reconciliation

### Phase 3 — Analytics Engineering

- [ ] Dataform Raw Source Declarations
- [ ] Staging Transformations
- [ ] Canonical Business Model
- [ ] Data Quality Assertions

### Phase 4 — Production Platform

- [ ] Terraform
- [ ] Cloud Run
- [ ] Scheduling
- [ ] CI/CD
- [ ] Observability
- [ ] Recovery and Manual-Review Runbooks

### Phase 5 — Data Products

- [ ] Customer 360
- [ ] Sales Analytics
- [ ] Delivery Analytics
- [ ] ML / Feature Examples

---

## Architecture Decisions

Mercury uses Architecture Decision Records to document significant engineering decisions and, importantly, the reasoning behind them.

Implemented decisions currently include:

- ADR-001 — Layered Platform Architecture
- ADR-002 — Immutable Raw Data
- ADR-003 — Canonical Data Model
- ADR-004 — Data Products
- ADR-005 — Shared CSV Connector Abstraction
- ADR-006 — Storage Abstraction
- ADR-007 — Source Delivery and Historical Simulation
- ADR-008 — BigQuery Raw Loading
- ADR-009 — Historical Replay Orchestration
- ADR-010 — Replay State and Recovery Architecture
- ADR-011 — Security Hardening and Data-Leak Prevention

ADR-010 is complete for the current ingestion scope.

Its implemented architecture now covers:

```text
Phase 1
Replay-state foundation
        ↓
Phase 2
Stateful historical replay
        ↓
Phase 3A
Recovery planning
        ↓
Phase 3B
Safe targeted recovery execution
        ↓
Phase 3C
Provenance-backed reconciliation
```

Together, ADR-010 and ADR-011 establish Mercury's operational control plane for replay, recovery, physical lineage, reconciliation and safe failure handling.

---

## Documentation

Project documentation is maintained alongside the implementation.

This includes:

- Architecture Decision Records (ADRs)
- Design principles
- Architecture diagrams
- Security documentation
- Project charter
- Engineering roadmap

The ADRs capture not only what Mercury implements, but why specific architectural boundaries and trade-offs were chosen.

---

## Engineering Principles

Mercury is developed according to the following principles:

- Build what belongs.
- Document why it exists.
- Automate how it runs.
- Design for maintainability.
- Prefer clarity over cleverness.
- Build reusable capabilities before reusable code.
- Keep infrastructure concerns behind explicit abstractions.
- Preserve source fidelity in Raw.
- Make failure visible before automating recovery.
- Prefer explicit operational state over inference from side effects.
- Preserve evidence rather than rewriting history.
- Reconcile from independently observable facts rather than assumptions.
- Fail closed when control-plane integrity cannot be guaranteed.
- Keep source-specific simulation semantics outside reusable infrastructure.

---

## Current Status

Mercury has completed its ingestion and cloud Raw-platform foundation for the current project scope.

The platform provides a validated data path from simulated source delivery through immutable Google Cloud Storage landing into BigQuery Raw:

```text
Source Delivery
      ↓
Reusable Connector
      ↓
Immutable GCS Raw
      ↓
BigQuery Raw
```

Both historical incremental replay and one-off reference loading have been successfully exercised against real GCP infrastructure.

ADR-010 provides the complete operational control plane for transactional historical replay:

```text
Replay State
      +
Physical Provenance
      ↓
Recovery Planning
      ↓
Recovery Execution
      ↓
Reconciliation
```

Historical replay:

- records durable append-only source-level state;
- correlates top-level replay invocations through `run_id`;
- isolates independent source failures within a business date;
- preserves successfully completed sibling work;
- distinguishes latest-attempt state from monotonic logical completion;
- stops later-date progression only after all safe work for an incomplete date has been attempted.

Targeted recovery can:

- skip sources that require no work;
- rerun ingestion and warehouse loading where safe;
- reuse validated immutable Raw artifacts for warehouse-only recovery;
- continue unrelated safe sibling work after ordinary source failures;
- fail closed when replay-state or provenance persistence is unavailable;
- append recovery events under fresh execution identities;
- re-derive business-date completeness from durable completion history;
- preserve prior successful completion across later failed re-attempts;
- reconcile ambiguous physical/control-plane state from durable provenance and independently observed cloud metadata;
- confirm existing successful physical work without repeating it;
- block contradictory or insufficient evidence rather than guessing;
- keep manual-review cases non-destructive when deterministic automation is not justified.

Physical lineage now connects:

```text
delivery
   ↓
immutable Raw artifact
   ↓
provenance_id
   ↓
warehouse load
   ↓
BigQuery Raw partition
```

Recovery and reconciliation remain within ADR-011's security boundary: Raw artifacts are not destructively overwritten or unnecessarily downloaded, Raw rows are not read merely to prove warehouse existence, operational errors use safe Mercury-authored messages, and runtime execution does not require broad infrastructure-administration privileges.

The complete ingestion regression suite currently passes with:

```text
1251 passed
0 failed
```

### Current Engineering Focus

The ingestion layer is complete for the current scope.

Mercury now moves into **Analytics Engineering**:

```text
BigQuery Raw
      ↓
Dataform
      ↓
Staging
      ↓
Canonical Model
      ↓
Data Quality
      ↓
Reusable Data Products
```

The next implementation milestone is to declare the existing BigQuery Raw sources in Dataform and begin building the staging layer on top of the ingestion foundation.

---

## License

This project is licensed under the MIT License.