# Mercury Roadmap

This roadmap tracks Mercury's implementation progress toward Version 1.

It records:

- major capabilities that have been completed;
- the platform phase currently under development;
- the next planned implementation milestones;
- capabilities intentionally deferred beyond Version 1.

Detailed architecture, implementation behavior, validation evidence, and engineering rationale are documented elsewhere in the repository.

---

## Roadmap Overview

```text
Phase 0 — Foundation                 [x] Complete
        ↓
Phase 1 — Ingestion                  [x] Complete
        ↓
Phase 2 — Cloud Raw Platform         [x] Complete
        ↓
Phase 3 — Analytics Engineering      [wip] In Progress
        ↓
Phase 4 — Production Platform        [] Planned
        ↓
Phase 5 — Data Products              [] Planned
```

### Phase 0 - Foundation

**Status**: [x] Complete

Mercury's project and architectural foundation was established before platform implementation began.

#### Completed

- [x] Create project repository and development structure
- [x] Define Mercury vision and scope
- [x] Create Project Charter
- [x] Define Nova Commerce business context
- [x] Establish layered platform architecture
- [x] Define immutable Raw principle
- [x] Define canonical modelling direction
- [x] Define data-product direction
- [x] Establish Architecture Decision Record process
- [x] Establish project documentation structure

#### Outcome

Mercury has a documented platform purpose, architectural direction, and engineering decision process that subsequent implementation phases build upon.

### Phase 1 - Ingestion

**Status**: [x] Complete

Phase 1 established Mercury's reusable ingestion framework and source-delivery model.

#### Connector Framework

- [x] Implement reusable connector architecture
- [x] Implement all eight Olist source connectors
- [x] Introduce shared CSV connector abstraction
- [x] Preserve source fidelity during ingestion
- [x] Generate consistent ingestion metadata
- [x] Preserve SHA-256 artifact integrity metadata

#### Storage

- [x] Introduce shared storage abstraction
- [x] Implement local Raw storage
- [x] Implement Google Cloud Storage backend
- [x] Preserve deterministic Raw Landing hierarchy
- [x] Implement immutable create-only cloud uploads
- [x] Keep connectors independent of physical storage backend

#### Source Delivery

- [x] Define initial vs incremental source-delivery semantics
- [x] Implement Olist historical source simulation
- [x] Implement one-off reference deliveries
- [x] Implement daily transactional deliveries
- [x] Preserve valid zero-record deliveries
- [x] Introduce reusable source-delivery abstractions
- [x] Validate expected source membership

#### Historical Replay

- [x] Implement historical replay orchestration
- [x] Separate reference loading from transactional replay
- [x] Implement chronological date-range replay
- [x] Preserve source-level failure isolation
- [x] Validate replay against real GCS infrastructure

#### Outcome

Mercury can ingest independent source systems through reusable connectors and land source-faithful, immutable Raw artifacts using interchangeable local and cloud storage backends.

### Phase 2 - Cloud Raw Platform

**Status**: [x] Complete

Phase 2 extended ingestion into a durable cloud Raw platform with warehouse loading, operational state, recovery, provenance, reconciliation, and security controls.

#### BigQuery Raw

- [x] Create BigQuery Raw dataset
- [x] Define explicit Raw schemas
- [x] Implement reusable BigQuery Raw loader
- [x] Implement reference-table loading
- [x] Implement transactional partition loading
- [x] Preserve source-faithful Raw values
- [x] Validate Raw loading against real BigQuery

#### Replay State

- [x] Define source-level replay-state model
- [x] Implement append-only replay history
- [x] Implement BigQuery-backed replay-state persistence
- [x] Integrate durable state with historical replay
- [x] Introduce execution-level run_id
- [x] Preserve ingestion and warehouse stage separation
- [x] Distinguish latest execution from logical completion
- [x] Implement monotonic logical-completion semantics
- [x] Derive date completeness from durable source state

#### Targeted Recovery

- [x] Implement stage-aware recovery planning
- [x] Implement targeted recovery execution
- [x] Avoid repeating already-complete source work
- [x] Support ingestion-and-load recovery
- [x] Support warehouse-only recovery
- [x] Reuse validated immutable Raw artifacts
- [x] Preserve append-only recovery history
- [x] Route ambiguous cases to reconciliation or manual review

#### Provenance & Reconciliation

- [x] Implement Raw artifact provenance
- [x] Implement warehouse-load provenance
- [x] Establish Raw-artifact-to-warehouse-load physical lineage
- [x] Implement metadata-only GCS artifact inspection
- [x] Implement metadata-only BigQuery partition inspection
- [x] Implement provenance-backed reconciliation
- [x] Block automatic recovery when evidence is missing or contradictory

#### Security Hardening

- [x] Establish platform-wide security contract
- [x] Implement PII-safe operational error handling
- [x] Validate immutable Raw storage protections
- [x] Establish dedicated runtime workload identity
- [x] Remove long-lived runtime service-account key dependency
- [x] Apply least-privilege runtime permissions
- [x] Separate business Raw data from operational control-plane metadata
- [x] Validate security controls against deployed GCP infrastructure


#### Outcome

Mercury has a validated cloud ingestion path from source delivery through immutable GCS Raw storage into BigQuery Raw, supported by durable operational state, targeted recovery, physical provenance, reconciliation, and least-privilege security controls.

The ingestion and Raw-platform foundation is complete for the current Version 1 scope.

### Phase 3 - Analytics Engineering

**Status**: [wip] In Progress

Phase 3 transforms source-faithful Raw data into standardised, tested, analytically useful data while preserving clear infrastructure and security boundaries.

#### 3.1 Staging Architecture & Contracts

**Status**: [x] Complete

- [x] Define reusable staging-layer standard
- [x] Define technical vs semantic staging responsibilities
- [x] Define blocking validation vs quality-observation boundary
- [x] Profile all eight Olist Raw sources
- [x] Define staging grain for all eight sources
- [x] Define staging keys
- [x] Define semantic data types
- [x] Define normalisation rules
- [x] Define nullability expectations
- [x] Define domain constraints
- [x] Document Olist staging contracts
- [x] Record staging architecture in ADR-012

#### 3.2 Dataform Foundation

**Status**: [x] Complete

- [x] Introduce Dataform project structure
- [x] Configure Mercury Dataform project
- [x] Declare all eight BigQuery Raw sources
- [x] Implement first staging model: stg_customers
- [x] Introduce Dataform assertions
- [x] Validate Dataform compilation locally
- [x] Validate BigQuery dry-run execution
- [x] Protect local Dataform credentials from source control
- [x] Introduce Terraform project structure
- [x] Configure Terraform development environment
- [x] Bring BigQuery staging dataset under Terraform management
- [x] Preserve europe-west4 regional placement
- [x] Establish Terraform/Dataform ownership boundary
- [x] Protect Terraform state, plans, and local variables from source control
- [x] Create dedicated Dataform transformation service account
- [x] Grant project-level BigQuery job execution
- [x] Grant read-only access to BigQuery Raw
- [x] Grant required read/write access to BigQuery Staging
- [x] Validate prohibited transformation capabilities
- [x] Execute Dataform using the intended transformation security boundary

#### 3.3 Complete Staging Layer

**Status**: [wip] In progress

Implement the remaining Olist staging models according to the documented contracts.

- [x] stg_customers
- [x] stg_orders
- [x] stg_order_items
- [x] stg_products
- [x] stg_sellers
- [ ] stg_payments
- [ ] stg_reviews
- [ ] stg_geolocations

For each staging model:

- [ ] apply documented semantic types;
- [ ] apply documented normalisation;
- [ ] implement blocking assertions where justified;
- [ ] preserve source-quality anomalies where required;
- [ ] compile and validate through Dataform;
- [ ] validate resulting BigQuery relation.

#### 3.4 Staging Quality Layer

**Status**: [wip] In Progress

- [x] Implement and validate `dq_orders_lifecycle_anomalies`
- [x] Implement and validate `dq_products_anomalies`
- [ ] Implement non-blocking source-quality observations
- [ ] Surface documented Olist source anomalies
- [ ] Separate source-quality reporting from transformation failure
- [ ] Define quality outputs suitable for downstream monitoring
- [ ] Validate quality behavior against profiled source findings

#### 3.5 Relationship Exploration

**Status**: [ ] Planned

Before implementing the canonical model:

- [ ] profile relationships between staged entities
- [ ] validate expected parent-child relationships
- [ ] investigate referential-integrity gaps
- [ ] validate cardinalities
- [ ] identify modelling implications of source anomalies
- [ ] document canonical modelling inputs and decisions

#### 3.6 Canonical Business Model

**Status**: [ ] Planned

Implement Mercury's reusable business-oriented model above staging.

Expected model direction includes:

##### Dimensions

- [ ] Customer
- [ ] Product
- [ ] Seller
- [ ] Date
- [ ] Location

##### Facts

- [ ] Orders
- [ ] Order Items
- [ ] Payments
- [ ] Reviews

Final model grain, relationships, and naming should be confirmed from staged-data exploration rather than assumed from the Raw source structure.

#### Phase 3 Exit Criteria

Phase 3 is complete when:

- [ ] Dataform executes through a dedicated least-privilege transformation identity;
- [ ] all eight Raw sources have implemented staging models;
- [ ] blocking staging assertions are operational;
- [ ] non-blocking quality observations are operational;
- [ ] staged relationships have been profiled and validated;
- [ ] the canonical business model is implemented and tested;
- [ ] analytical transformation infrastructure is reproducible through the intended Terraform/Dataform ownership model.

### Phase 4 — Production Platform

**Status**: [ ] Planned

Phase 4 will operationalise Mercury beyond local development and manually initiated cloud execution.

#### Infrastructure as Code

Terraform adoption has begun during Phase 3 where infrastructure ownership is required for Analytics Engineering.

Phase 4 will expand infrastructure management to the broader Mercury runtime.

- [x] Introduce Terraform
- [x] Bring staging dataset under Terraform management
- [ ] Evaluate existing GCP resources for Terraform adoption
- [ ] Manage production runtime infrastructure through Terraform
- [ ] Manage production IAM through Infrastructure as Code

#### Runtime & Scheduling

- [ ] Deploy ingestion runtime to Cloud Run
- [ ] Implement scheduled execution with Cloud Scheduler
- [ ] Define production runtime configuration
- [ ] Validate keyless workload authentication

#### Observability

- [ ] Implement cloud logging
- [ ] Implement operational monitoring
- [ ] Define alerting strategy
- [ ] Surface ingestion/replay/recovery status
- [ ] Ensure production telemetry conforms to ADR-011

#### CI/CD

- [ ] Introduce GitHub Actions
- [ ] Automate test execution
- [ ] Automate formatting and linting
- [ ] Add dependency/security scanning
- [ ] Add infrastructure validation
- [ ] Define deployment workflow

#### Operations

- [ ] Create recovery runbook
- [ ] Create manual-review runbook
- [ ] Define operational escalation paths
- [ ] Define production retention policies
- [ ] Create developer/operations documentation where required

#### Phase 4 Exit Criteria

Phase 4 is complete when Mercury can be deployed, scheduled, monitored, validated, and operated through reproducible production-oriented workflows.

### Phase 5 — Data Products

**Status**: [ ] Planned

Phase 5 demonstrates how reusable business data can support multiple downstream use cases without rebuilding the underlying data foundation.

Final products will be selected based on the canonical model and the analytical value they demonstrate.

#### Candidate Data Products

##### Customer Analytics

- [ ] Customer 360
- [ ] Customer segmentation
- [ ] Customer lifetime value

##### Sales Analytics

- [ ] Sales performance
- [ ] Revenue trends
- [ ] Product performance

##### Operations Analytics

- [ ] Delivery performance
- [ ] Seller performance
- [ ] Payment analytics

##### Business Intelligence

- [ ] Looker Studio dashboard

##### Application

- [ ] Streamlit application
- [ ] Customer explorer
- [ ] Order explorer
- [ ] Seller explorer
- [ ] Platform monitoring

##### Data Science / ML

- [ ] Demonstrate reusable feature generation from canonical data
- [ ] Implement at least one analytical or ML example where useful

#### Phase 5 Exit Criteria

Phase 5 is complete when Mercury demonstrates that multiple downstream products can consume the same trusted platform foundation without duplicating ingestion and core modelling logic.

### Beyond Version 1

The following capabilities are intentionally deferred unless a concrete requirement justifies introducing them.

- [ ] Production SaaS/API source connectors
- [ ] REST API ingestion
- [ ] Change Data Capture
- [ ] Real-time streaming
- [ ] Automated schema evolution
- [ ] Additional storage or warehouse backends
- [ ] Advanced feature-store capabilities
- [ ] Advanced table formats where justified
- [ ] Container-orchestration platforms beyond the requirements of Mercury's runtime

These are not required to demonstrate Mercury's Version 1 platform architecture.

### Related Documentation

Detailed information is maintained in the appropriate repository documentation:

- [README.md](README.md) — platform overview and capabilities
- [PROJECT_CHARTER.md](PROJECT_CHARTER.md) — project purpose, scope, and goals
- [architecture/decisions/](architecture/decisions/) — architectural decisions and rationale
- [docs/](docs/) — detailed implementation documentation
- [docs/infrastructure/](docs/infrastructure/) — ingestion framework implementation overview
- [docs/infrastructure/gcp_infrastructure.md](docs/infrastructure/gcp_infrastructure.md) — current GCP infrastructure implementation
- [docs/security/](docs/security/) — security audits and validation evidence
- [docs/olist_staging_contracts.md](docs/analytics/staging/olist_staging_contracts.md) — Olist staging contracts