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
- immutable Raw landing with integrity metadata;
- realistic initial and incremental source-delivery simulation;
- historical replay across business dates;
- explicit BigQuery Raw loading;
- partition-aware transactional loading;
- one-off reference-table loading;
- durable append-only source-level replay state;
- stage-aware targeted recovery planning and execution;
- reuse of validated immutable Raw artifacts for warehouse-only recovery;
- monotonic date-completion derivation across replay and recovery attempts;
- least-privilege and data-leak-prevention security boundaries.

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

Operational replay metadata is maintained separately from business Raw data so orchestration state does not become part of the source-faithful Raw layer.

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
- Stage-aware targeted recovery planning
- Safe targeted recovery execution
- Validated immutable Raw artifact reuse
- Monotonic logical-completion derivation
- Security hardening and data-leak prevention
- Automated regression testing

### Planned

- Recovery reconciliation and manual-review workflows
- Dataform staging transformations
- Canonical business modelling
- Reusable data products
- Data quality validation
- Infrastructure as Code
- Production orchestration
- Platform observability
- Automated deployment

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

Historical replay routes each daily source delivery to the corresponding BigQuery partition.

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

Targeted recovery is divided into explicit planning and execution responsibilities:

```text
Replay history + recovery evidence
        ↓
RecoveryPlanner
        ↓
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

The recovery planner can select:

```text
SKIP
INGEST_AND_LOAD
LOAD_ONLY
RECONCILE
MANUAL_REVIEW
```

`RecoveryExecutor` executes only safe, unambiguous actions:

- `SKIP` performs no physical work;
- `INGEST_AND_LOAD` reruns ingestion and then loads the resulting immutable Raw artifact;
- `LOAD_ONLY` reuses an explicitly validated `gs://` Raw artifact without rerunning ingestion;
- `RECONCILE` and `MANUAL_REVIEW` remain blocked until ADR-010 Phase 3C defines their resolution workflow.

Recovery attempts append new replay-state history under a fresh `run_id`. Ordinary source failures remain isolated so unrelated safe work can continue, while replay-state persistence failures fail closed.

Date completeness is re-derived from durable successful-completion history. An earlier `SUCCESS | WAREHOUSE` remains valid completion evidence even if a later recovery re-attempt fails.

Recovery execution also complies with ADR-011: arbitrary provider or exception text is not persisted in operational failure metadata, Raw artifacts remain immutable, and recovery does not require destructive storage or infrastructure-administration privileges.

## Security by Design

Mercury is designed to process customer and source data using explicit,
least-privilege security boundaries.

Key security properties include:

- **Dedicated runtime identity** — deployed workloads use a bounded
  `mercury-runtime` service account rather than developer credentials.
- **Least-privilege cloud access** — runtime permissions are limited to the
  GCS and BigQuery operations required by ingestion and orchestration.
- **Immutable Raw landing** — Raw objects are written using create-only
  generation preconditions, preventing accidental replacement of existing
  artifacts.
- **Restricted destructive access** — the runtime identity cannot delete Raw
  GCS objects or administer storage infrastructure.
- **Infrastructure/runtime separation** — datasets, buckets, and IAM are
  provisioned outside the application runtime. Mercury cannot create arbitrary
  BigQuery datasets.
- **Explicit dataset access** — sensitive datasets do not rely on broad
  `projectReaders`, `projectWriters`, or `projectOwners` dataset ACLs.
- **Safe operational errors** — persisted failure metadata contains
  Mercury-authored operational descriptions rather than raw provider or
  exception text that could contain sensitive data.
- **Keyless runtime authentication** — Mercury's runtime model does not require
  long-lived downloaded service-account keys.

Security decisions, audits, and validation evidence are documented in
`architecture/decisions/ADR-011-Data Security, Privacy, and Data-Leak Prevention.md`
and `docs/security/`.

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

The ingestion package contains the current implementation of:

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
shared connector construction
```

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

### Phase 2 — Cloud Data Platform

- [x] Cloud Storage Raw Landing Zone
- [x] BigQuery Raw Dataset
- [x] BigQuery Raw Loading
- [x] Transactional Partition Loading
- [x] Reference Table Loading
- [x] Replay-State Persistence Foundation
- [x] Replay Runner State Integration
- [x] Security hardening and data-leak prevention
- [x] Targeted Replay Recovery Planning and Execution
- [ ] Recovery Reconciliation and Manual Review
- [ ] Dataform Transformations

### Phase 3 — Production

- [ ] Terraform
- [ ] Cloud Run
- [ ] Scheduling
- [ ] CI/CD
- [ ] Observability

### Phase 4 — Data Products

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
- ADR-011 — Security hardening and data-leak prevention

ADR-010 is being implemented incrementally. Its replay-state foundation, runner integration, recovery planning, and safe recovery execution phases are complete; reconciliation and manual-review handling remain for Phase 3C.

---

## Documentation

Project documentation is maintained alongside the implementation.

This includes:

- Architecture Decision Records (ADRs)
- Design principles
- Architecture diagrams
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

---

## Current Status

## Current Status

Mercury currently has a validated cloud ingestion path from simulated source delivery through immutable Google Cloud Storage landing into BigQuery Raw.

Both historical incremental replay and one-off reference loading have been successfully exercised against real GCP infrastructure.

ADR-010 now provides a complete replay-state, recovery-planning, and safe recovery-execution path through Phase 3B.

Historical replay records durable append-only source-level state, correlates top-level replay and recovery invocations through `run_id`, isolates independent source failures within a business date, preserves successful sibling data, and distinguishes latest-attempt state from monotonic logical completion.

Targeted recovery can now:

- skip sources that require no work;
- rerun ingestion and warehouse loading where safe;
- reuse validated immutable Raw artifacts for warehouse-only recovery;
- continue unrelated safe sibling work after ordinary source failures;
- fail closed when replay-state persistence is unavailable;
- append recovery events under a fresh `run_id`;
- re-derive business-date completeness from durable completion history;
- preserve prior successful completion across later failed re-attempts;
- block ambiguous reconciliation and manual-review cases rather than guessing.

Recovery execution remains within ADR-011's security boundary: Raw artifacts are not destructively overwritten or unnecessarily downloaded, operational errors use safe Mercury-authored messages, and recovery does not require broad infrastructure-administration privileges.

The complete automated regression suite currently passes with **1084 tests**.

The next ADR-010 engineering step is **Phase 3C — reconciliation and manual-review handling for ambiguous physical/control-plane state**.

---

## License

This project is licensed under the MIT License.