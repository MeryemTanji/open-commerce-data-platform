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

### Production Orchestration

Mercury is being operationalised through a governed production execution path that keeps scheduling, ingestion, readiness validation, and analytical transformation as separate control boundaries.

The source-controlled production implementation currently provides:

- a validated daily ingestion command;
- externalised runtime configuration;
- PII-safe structured execution results;
- a containerised, non-root ingestion runtime;
- durable delivery-readiness evaluation;
- separate scheduled and manual execution modes;
- a historical simulation clock for incremental Olist processing;
- workflow-controlled Cloud Run execution;
- ingestion-to-transformation dependency gates;
- explicit Dataform compilation and execution gates;
- known terminal outcomes for successful, failed, blocked, and no-work executions;
- automated runtime, readiness, CLI, and workflow contract tests.

For Olist, Mercury preserves the incremental simulation established during local development. Records assigned to historical delivery date `D` are processed with simulated ingestion date `D + 1 day`. Scheduled execution advances through the bounded historical range one incomplete delivery date at a time rather than loading the entire dataset in one operation.

The workflow permits Dataform execution only when:

1. the ingestion job terminates successfully;
2. durable metadata confirms the complete approved source set for the delivery date;
3. Dataform compilation succeeds.

The architecture and runtime contracts are implemented in source control. Cloud infrastructure deployment and end-to-end production validation remain Phase 4 work and must not be interpreted as complete.

See [ADR-014](architecture/decisions/ADR-014-Orchestrate-Production-Execution-with-Cloud-Workflows.md), the [production platform design](architecture/designs/production_platform_design.md), and the [Olist production runtime contract](architecture/designs/olist_production_runtime_contract.md).

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

```text
Phase 0 — Foundation                 [x]
        ↓
Phase 1 — Ingestion                  [x]
        ↓
Phase 2 — Cloud Raw Platform         [x]
        ↓
Phase 3 — Analytics Engineering      [x]
        ↓
Phase 4 — Production Platform        [~]
        ↓
Phase 5 — Data Products              [ ]
```

## Current Focus

Mercury is currently implementing **Phase 4 — Production Platform**.

The production architecture, runtime commands, durable readiness gate, historical simulation clock, container definition, governed workflow, automated contract tests, and source-specific Olist runtime contract are implemented in source control.

The scheduled production path is designed to:

1. resolve the next eligible historical Olist delivery date;
2. execute one finite ingestion job;
3. require successful job termination;
4. verify durable completion of the exact approved source set;
5. compile the Dataform project;
6. execute staging, canonical models, and governed quality controls;
7. finish with an explicit terminal result.

This preserves Mercury's incremental Olist simulation: historical source activity for delivery date `D` is treated as arriving on ingestion date `D + 1 day`. The resulting Raw, staging, and canonical layers can therefore evolve incrementally as they would for a daily API source.

The next major steps are:

```text
Reconcile Authoritative Terraform State
        ↓
Provision Runtime Infrastructure and IAM
        ↓
Build and Deploy the Cloud Run Image
        ↓
Deploy and Validate the Production Workflow
        ↓
Add Scheduling, Monitoring, and Alerting
        ↓
Introduce CI/CD and Operational Runbooks
```

Infrastructure deployment has not yet been completed. Terraform-dependent changes remain intentionally paused until the authoritative state is safely reconciled and verified.

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