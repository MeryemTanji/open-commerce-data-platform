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
- source-level replay-state persistence foundations.

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
- Automated regression testing

### Planned

- Replay recovery and resumability
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

Mercury has begun introducing durable source-level historical replay state.

ADR-010 Phase 1 establishes:

```text
ReplayStatus
ReplayStage
ReplayStateRecord
ReplayStateStore
BigQueryReplayStateStore
is_date_complete()
```

Replay state is append-only and stored separately from business Raw data.

The logical replay identity is:

```text
delivery_date + source_object
```

while individual state transitions receive their own event identity.

The state foundation is designed to support future targeted recovery without weakening immutable Raw storage.

Runner integration and recovery execution remain under active development and are intentionally not considered complete yet.

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
- [ ] Replay Runner State Integration
- [ ] Targeted Replay Recovery
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

ADR-010 is being implemented incrementally. Its state and persistence foundation is complete; runner integration and recovery behavior remain in development.

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

Mercury currently has a validated cloud ingestion path from simulated source delivery through immutable Google Cloud Storage landing into BigQuery Raw.

Both historical incremental replay and one-off reference loading have been successfully exercised against real GCP infrastructure.

The current stable recovery foundation provides source-level append-only replay state and BigQuery-backed operational metadata.

The next engineering step is to complete ADR-010 runner integration and validate its recovery semantics before implementing targeted replay recovery.

---

## License

This project is licensed under the MIT License.