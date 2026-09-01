# Mercury

> A reusable, cloud-native data foundation for analytics, data science, and data products.

Mercury is an end-to-end data platform built on Google Cloud that demonstrates how organisations can transform raw operational data into trusted, reusable data products.

Rather than building isolated pipelines for individual dashboards, models, or analyses, Mercury establishes a common data foundation that standardises ingestion, storage, transformation, quality, recovery, and publishing.

The project is implemented using a realistic e-commerce dataset while being designed around reusable platform capabilities rather than source-specific solutions.

---

## Why Mercury?

Analytics teams often spend significant engineering effort repeatedly preparing data before they can create business value.

Common problems include:

- inconsistent source formats;
- duplicated transformation logic;
- manually prepared analytical datasets;
- fragile pipelines;
- limited operational traceability;
- tightly coupled reporting and modelling solutions.

Mercury addresses this by creating a reusable platform between source systems and downstream use cases.

```text
Sources
   ↓
Reusable Data Platform
   ↓
Trusted Data Products
   ↓
Analytics • Data Science • Applications
```

## Architecture

Mercury follows a layered architecture with clear responsibilities between ingestion, storage, transformation, modelling, and consumption.

```text
┌─────────────────────────┐
│         Sources         │
│                         │
│ APIs • Files • Systems  │
└────────────┬────────────┘
             │
             ▼
┌─────────────────────────┐
│       Ingestion         │
│                         │
│ Connectors • Delivery   │
└────────────┬────────────┘
             │
             ▼
┌─────────────────────────┐
│      Immutable Raw      │
│                         │
│  Cloud Storage + BQ     │
└────────────┬────────────┘
             │
             ▼
┌─────────────────────────┐
│        Staging          │
│                         │
│       Dataform          │
└────────────┬────────────┘
             │
             ▼
┌─────────────────────────┐
│    Canonical Model      │
│                         │
│ Trusted Business Data   │
└────────────┬────────────┘
             │
             ▼
┌─────────────────────────┐
│      Data Products      │
└────────────┬────────────┘
             │
             ▼
 Dashboards • ML • Apps • APIs
 ```

 A separate operational control plane provides replay state, provenance, targeted recovery, and reconciliation without mixing operational metadata into business Raw data.

 ```text
 Replay State + Provenance
           ↓
    Recovery Planning
           ↓
    Recovery Execution
           ↓
      Reconciliation
```

Detailed architectural decisions are documented in [architecture/decisions/](architecture/decisions/).

## Platform Capabilities

### Ingestion

Mercury provides a reusable ingestion framework rather than source-specific pipeline scripts.

Current capabilities include:

- reusable source connectors;
- shared CSV ingestion abstractions;
- interchangeable local and Google Cloud Storage backends;
- initial and incremental source delivery;
- historical replay;
- source-level failure isolation;
- explicit BigQuery Raw loading.

The current commerce implementation contains eight source connectors covering reference and transactional datasets.

### Raw Data Foundation

Mercury preserves source-faithful data before applying analytical transformations.

The Raw platform provides:

- immutable Cloud Storage landing;
- SHA-256 integrity metadata;
- explicit BigQuery schemas;
- partitioned transactional tables;
- reference tables;
- deterministic historical loading.

This provides a stable boundary between source ingestion and downstream analytics engineering.

### Reliability & Recovery

Mercury maintains an operational control plane for understanding and recovering historical ingestion activity.

It supports:

- durable append-only replay state;
- stage-aware recovery planning;
- targeted recovery execution;
- immutable Raw artifact reuse;
- Raw artifact provenance;
- warehouse-load provenance;
- physical lineage;
- provenance-backed reconciliation.

Recovery is deliberately non-destructive: ambiguous situations are surfaced for review rather than resolved through unsafe assumptions.

See [ADR-010](architecture/decisions/ADR-010-Persist%20Source-Level%20Historical%20Replay%20State%20and%20Derive%20Date-Level%20Completion.md) for the detailed replay and recovery architecture.

### Analytics Engineering

Mercury standardises Raw data before it enters business modelling.

The analytics layer uses Dataform to provide:

- reusable staging contracts;
- technical and semantic normalisation;
- explicit source declarations;
- data quality assertions;
- source-quality visibility;
- canonical business modelling.

The staging layer normalises source data without silently rewriting source-quality problems. Quality issues can instead be flagged separately so valid data is not unnecessarily blocked from progressing through the platform.

The Olist staging layer is implemented and validated across all eight Raw source tables. Blocking assertions enforce structural contracts, while separate non-blocking quality views preserve and surface documented source anomalies.

See [ADR-012](architecture/decisions/ADR-012-Staging%20Layer%20Standardization%20and%20Semantic%20Contracts.md) and the Olist staging contract under [docs/](docs/analytics/staging/) for detailed staging rules.

### Security & Infrastructure

Security boundaries are designed around least privilege and separation of responsibilities.

Mercury includes:

- dedicated workload identities;
- immutable Raw storage;
- restricted destructive access;
- keyless runtime authentication;
- infrastructure/runtime separation;
- safe operational error handling;
- metadata-only reconciliation;
- protected local credentials and infrastructure state;
- Terraform-managed infrastructure.

Ingestion and analytical transformation workloads are treated as separate security boundaries rather than sharing broad platform permissions.

See [ADR-011](architecture/decisions/ADR-011-Data%20Security,%20Privacy,%20and%20Data-Leak%20Prevention.md) and [docs/security/](docs/security/) for the detailed security model and validation evidence.

## Technology Stack

| Capability                      | Technology           |
| ------------------------------- | -------------------- |
| Ingestion & orchestration logic | Python               |
| Raw object storage              | Google Cloud Storage |
| Data warehouse                  | BigQuery             |
| Transformations                 | Dataform             |
| Infrastructure as Code          | Terraform            |
| Runtime                         | Cloud Run            |
| Scheduling                      | Cloud Scheduler      |
| BI                              | Looker Studio        |
| Applications                    | Streamlit            |

## Repository Structure

```text
.
├── architecture/
│   └── decisions/          # Architecture Decision Records
|   └── designs/            # Design Frameworks and Diagrams
│
├── docs/                   # Platform and implementation documentation
│
├── ingestion/              # Ingestion and operational control plane
│
├── dataform/
│   ├── definitions/
│   │   ├── sources/        # BigQuery Raw declarations
│   │   ├── staging/        # Standardised staging models
│   │   └── quality/        # Data-quality logic
│   └── includes/
│
├── terraform/
│   └── environments/       # Infrastructure definitions
│
├── tests/                  # Automated tests
├── scripts/                # Development and operational utilities
│
├── PROJECT_CHARTER.md
├── ROADMAP.md
└── README.md
```

The repository is intentionally organised by platform responsibility so ingestion, transformation, infrastructure, operational recovery, and documentation can evolve independently.

## Engineering Principles

Mercury is guided by a small set of platform principles:

- preserve source fidelity in Raw;
- standardise data above the Raw layer;
- separate technical normalisation from data-quality handling;
- prefer reusable capabilities over project-specific solutions;
- keep infrastructure behind explicit boundaries;
- use durable state rather than inferring success from side effects;
- preserve operational evidence rather than rewriting history;
- automate only when the platform has sufficient evidence to act safely;
- apply least privilege to each workload independently;
- document significant architectural decisions.

## Roadmap

Mercury is being developed incrementally.

```text
Phase 0 — Foundation                 [x]
        ↓
Phase 1 — Ingestion                  [x]
        ↓
Phase 2 — Cloud Raw Platform         [x]
        ↓
Phase 3 — Analytics Engineering      [wip]
        ↓
Phase 4 — Production Platform
        ↓
Phase 5 — Data Products
```

## Current Focus

Mercury is currently in **Phase 3 — Analytics Engineering**.

The reusable staging standard and Olist staging contracts have been implemented across all eight Raw sources. The complete Dataform graph compiles and executes successfully under the dedicated least-privilege transformation identity, and all staging assertions pass.

The anomaly-disposition and monitoring contract has been defined, with Olist controls, validated baselines, severities, ownership, response expectations, and downstream dispositions documented.

Current work is focused on relationship exploration across staged entities. This phase will validate cardinalities, referential integrity, join amplification, reconciliation behavior, and the modelling constraints required for the canonical business model.

Operational implementation of quality history, baseline evaluation, and automated alerting is planned as part of **Phase 4 — Production Platform**.

The next major steps are:

```text
Relationship Exploration
        ↓
Canonical Business Model
        ↓
Production Platform
```

Detailed implementation status and upcoming work are maintained in [ROADMAP.md](ROADMAP.md).

## Documentation

Mercury keeps detailed engineering documentation outside the README so this file remains a concise platform overview.

| Document                                             | Purpose                                            |
| ---------------------------------------------------- | -------------------------------------------------- |
| [PROJECT_CHARTER.md](PROJECT_CHARTER.md)           | Project purpose, scope, and goals                  |
| [ROADMAP.md](ROADMAP.md)                           | Detailed implementation progress and upcoming work |
| [architecture/decisions/](architecture/decisions/) | Architecture decisions and engineering rationale   |
| [docs/](docs/)                                     | Detailed platform and implementation documentation |
| [docs/security/](docs/security/)                   | Security audits, controls, and validation evidence |

Architecture Decision Records cover the major platform boundaries, including immutable Raw storage, storage abstractions, source delivery, BigQuery loading, historical replay, recovery and provenance, security, and staging standardisation.

## License

This project is licensed under the MIT License.