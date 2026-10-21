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

### Current BigQuery Implementation

Mercury currently operates four governed BigQuery datasets:

```text
metadata    3 operational control-plane tables
raw         8 immutable Olist source tables
staging     8 standardised tables + 21 blocking assertions + 13 non-blocking quality views
canonical   14 governed relations + 62 blocking assertions
```

The Terraform-managed canonical dataset contains Mercury's initial Olist canonical model:

- five dimensions;
- four facts;
- one bridge;
- four governed intermediate relations.

The complete canonical graph compiles and executes through the dedicated least-privilege Dataform identity. Its assertions validate relation grains, deterministic keys, parent references, source reconciliation, anomaly dispositions, monetary reconciliation, and join-amplification safeguards.

See [Mercury GCP Infrastructure](docs/infrastructure/gcp_infrastructure.md). Detailed architectural decisions are documented in [architecture/decisions/](architecture/decisions/).

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

The Olist canonical layer is also implemented and validated. It transforms the staging relations into reusable customer, product, seller, location, date, order, order-item, payment, and review entities while preserving source traceability and approved anomaly dispositions.

The complete Dataform project contains 118 actions, including 35 datasets and 83 assertions. The canonical publication selection contains 14 relations and 62 assertions, all of which have successfully compiled, dry-run, and executed.

See the [canonical model design](architecture/designs/canonical_model_design.md), [Olist canonical contracts](docs/analytics/canonical/olist/), and [canonical validation evidence](docs/analytics/canonical/olist/olist_canonical_validation.md) for the detailed model and validation results.

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
│   │   ├── canonical/      # Governed canonical relations
│   │   └── quality/        # Staging and canonical quality controls
│   └── includes/           # Shared Dataform helpers
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
Phase 3 — Analytics Engineering      [x]
        ↓
Phase 4 — Production Platform
        ↓
Phase 5 — Data Products
```

## Current Focus

Mercury has completed **Phase 3 — Analytics Engineering**.

The eight Olist Raw sources now progress through governed staging and canonical layers. The implemented canonical graph contains five dimensions, four facts, one bridge, and four intermediate relations with explicit grains, deterministic keys, source traceability, anomaly dispositions, reconciliation controls, and join-amplification safeguards.

The complete Dataform project compiles successfully. All canonical relations and blocking assertions have been dry-run and executed, and all 13 non-blocking quality observations remain operational.

Mercury is now preparing for **Phase 4 — Production Platform**, which will operationalise the platform through scheduled execution, persistent quality history, monitoring, alerting, CI/CD, and production-oriented runbooks.

The next major steps are:

```text
Production Runtime and Scheduling
        ↓
Quality Monitoring and Alerting
        ↓
CI/CD and Operational Readiness
        ↓
Reusable Data Products
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