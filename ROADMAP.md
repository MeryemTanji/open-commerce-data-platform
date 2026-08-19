# Mercury Roadmap

This roadmap tracks the engineering milestones for Mercury.

The goal is not simply to complete features, but to build a production-inspired cloud-native commerce data platform one capability at a time.

Each completed milestone represents a meaningful addition to the platform.

---

# Sprint 1 — Foundation & Ingestion Framework

## Phase 0 — Foundation

### Project Definition

- [x] Create repository
- [x] Define project vision
- [x] Write project charter
- [x] Define Nova Commerce business context
- [x] Create repository README
- [x] Create architecture documentation

### Engineering Decisions

- [x] ADR-001 Layered Platform Architecture
- [x] ADR-002 Immutable Raw Data
- [x] ADR-003 Canonical Data Model
- [x] ADR-004 Data Products

### Architecture

- [x] Ingestion framework design
- [ ] Canonical warehouse design
- [ ] Platform architecture diagram
- [ ] Deployment architecture
- [ ] Data lineage diagrams

---

## Phase 1 — Local Ingestion Framework

### Project Structure

- [x] Python package structure
- [x] Virtual environment
- [x] pyproject.toml
- [x] Testing framework

### Platform Components

- [x] IngestionMetadata
- [x] LocalStorageManager
- [x] BaseConnector
- [x] CustomerConnector
- [x] OrdersConnector
- [x] OrderItemsConnector
- [x] ProductsConnector
- [x] SellersConnector
- [x] PaymentsConnector
- [x] ReviewsConnector
- [x] GeolocationConnector
- [x] Runner

### Local Raw Landing

- [x] First successful customer ingestion
- [x] Verify customer raw file integrity with SHA-256
- [x] Execute CustomerConnector through IngestionRunner
- [x] First successful orders ingestion
- [x] Verify orders raw file integrity with SHA-256
- [x] First successful order-items ingestion
- [x] Verify order-items raw file integrity with SHA-256
- [x] First successful products ingestion
- [x] Verify products raw file integrity with SHA-256
- [x] First successful sellers ingestion
- [x] Verify sellers raw file integrity with SHA-256
- [x] First successful payments ingestion
- [x] First successful reviews ingestion
- [x] First successful geolocation ingestion

### Testing

- [x] Metadata tests
- [x] Storage tests
- [x] Base connector tests
- [x] Customer connector tests
- [x] Orders connector tests
- [x] Order-items connector tests
- [x] Products connector tests
- [x] Sellers connector tests
- [x] Runner tests
- [x] End-to-end customer ingestion test
- [x] Multi-connector end-to-end ingestion tests
- [x] End-to-end ingestion test across all source connectors

### Framework Review

- [x] Complete remaining CSV connectors
- [x] Review repeated CSV connector patterns
- [x] Decide whether a shared CSV connector abstraction is justified
- [x] Refactor shared CSV behavior if justified by completed connector implementations

---

# Sprint 2 — Cloud Raw Platform & Historical Replay

## Google Cloud Foundation

- [x] Create GCP project
- [x] Enable required APIs
- [x] Configure authentication

## Cloud Storage

- [x] Create Cloud Storage bucket
- [x] Implement GCSStorageManager
- [x] Upload Raw files to Cloud Storage
- [x] Preserve Raw landing hierarchy
- [x] Implement atomic create-only uploads
- [x] Validate GCS SHA-256 integrity
- [x] Validate duplicate protection

## Source Delivery

- [x] Define initial vs incremental source-delivery patterns
- [x] Implement Olist source simulation
- [x] Implement initial/reference source deliveries
- [x] Implement daily incremental source deliveries
- [x] Preserve valid zero-record deliveries
- [x] Introduce SourceDelivery abstraction
- [x] Introduce SourceDeliveryBatch abstraction
- [x] Validate expected source membership

## BigQuery Raw

- [x] Create Raw dataset
- [x] Implement explicit Raw schemas
- [x] Implement BigQueryRawLoader
- [x] Implement reference-table loading
- [x] Implement transactional date-partition loading
- [x] Preserve source-faithful Raw values
- [x] Validate BigQuery loading with automated tests
- [x] Validate transactional partition loading against real BigQuery
- [x] Validate reference-table loading against real BigQuery

## Historical Replay

- [x] Introduce source-delivery provider abstraction
- [x] Implement OlistSimulatedSourceProvider
- [x] Implement HistoricalReplayRunner
- [x] Separate initial/reference load from daily historical replay
- [x] Validate daily expected-source membership
- [x] Reject structurally empty source-delivery batches
- [x] Preserve valid zero-record source deliveries
- [x] Implement date-range historical replay
- [x] Route transactional sources to correct BigQuery partitions
- [x] Validate historical replay against real GCS and BigQuery
- [x] Validate one-off reference load against real GCS and BigQuery

## Replay State & Recovery

### ADR-010 Phase 1 — State Foundation

- [x] Define ReplayStatus
- [x] Define ReplayStage
- [x] Define ReplayStateRecord
- [x] Enforce valid status/stage combinations
- [x] Define ReplayStateStore abstraction
- [x] Implement append-only replay event model
- [x] Implement BigQueryReplayStateStore
- [x] Create explicit replay-state BigQuery schema
- [x] Partition replay metadata by delivery date
- [x] Cluster replay metadata by source object
- [x] Implement replay history queries
- [x] Implement latest-state queries
- [x] Implement date-completeness domain validation
- [x] Keep replay metadata separate from Raw business data
- [x] Complete Phase 1 automated regression suite — 847 tests passing

### ADR-010 Phase 2 — Runner Integration

- [x] Finalise latest-attempt vs logical-completion semantics
- [x] Integrate ReplayStateStore with HistoricalReplayRunner
- [x] Introduce run_id across replay executions
- [x] Persist source-level ingestion state
- [x] Persist source-level warehouse state
- [x] Preserve ingestion/warehouse stage separation
- [x] Attempt all safe independent source work within a date
- [x] Support partial source availability
- [x] Derive date completeness from durable state
- [x] Preserve monotonic logical completion after later failed attempts
- [x] Stop range progression after incomplete dates
- [x] Validate Phase 2 against real GCP
- [x] Complete Phase 2 automated regression suite — 924 tests passing

### ADR-010 Phase 3 — Targeted Recovery

- [ ] Identify incomplete source deliveries
- [ ] Distinguish failure stage
- [ ] Avoid rerunning already-complete source work
- [ ] Reuse immutable GCS artifacts where appropriate
- [ ] Retry warehouse-only failures safely
- [ ] Reconcile physical data with control-plane state
- [ ] Re-evaluate date completeness after recovery
- [ ] Validate recovery against real GCP

### ADR-011 — Data Security, Privacy, and Data-Leak Prevention

  - [x] Complete security audit of Mercury's persistence, logging, exception, storage, orchestration, and cloud boundaries.
  - [x] Identify and document potential sensitive-data leakage paths.
  - [x] Introduce the safe `OperationalError` contract for persisted operational failures.
  - [x] Remove raw exception text from connector and historical replay persisted failure state.
  - [x] Preserve exception chaining for transient in-process debugging without persisting provider exception content.
  - [x] Add regression tests proving sensitive exception content cannot reach persisted operational metadata.
  - [x] Inspect GCS Raw bucket security configuration and IAM.
  - [x] Confirm Public Access Prevention is enforced on the Raw bucket.
  - [x] Confirm Uniform Bucket-Level Access is enabled on the Raw bucket.
  - [x] Create the dedicated `mercury-runtime` service account.
  - [x] Grant runtime only the GCS object-creation capability required for Raw ingestion.
  - [x] Grant runtime BigQuery job execution capability.
  - [x] Grant explicit runtime access to the existing `raw` and `metadata` datasets.
  - [x] Validate that runtime can create new Raw GCS objects.
  - [x] Validate Raw object immutability using create-only generation preconditions.
  - [x] Validate that runtime cannot delete Raw GCS objects.
  - [x] Validate that runtime cannot broadly list project buckets.
  - [x] Validate that runtime can submit BigQuery jobs.
  - [x] Validate that runtime can write to the existing `raw` dataset.
  - [x] Validate that runtime can write to and query the existing `metadata` dataset.
  - [x] Validate that runtime cannot create arbitrary BigQuery datasets.
  - [x] Validate `BigQueryReplayStateStore.ensure_resources()` under the restricted runtime identity.
  - [x] Remove broad `projectReaders`, `projectWriters`, and `projectOwners` access from `raw`.
  - [x] Remove broad `projectReaders`, `projectWriters`, and `projectOwners` access from `metadata`.
  - [x] Re-test legitimate runtime operations after dataset ACL hardening.
  - [x] Establish a human/infrastructure provisioning boundary separate from Mercury runtime execution.
  - [x] Validate a keyless runtime model using short-lived service-account impersonation rather than downloaded service-account keys.
  - [x] Document the security audit and infrastructure validation under `docs/security/`.

---

# Sprint 3 — Analytics Engineering

## Dataform

### Raw Layer Integration

- [ ] Declare BigQuery Raw sources in Dataform
- [ ] Validate Raw source contracts

### Staging Layer

- [ ] stg_customers
- [ ] stg_orders
- [ ] stg_order_items
- [ ] stg_products
- [ ] stg_sellers
- [ ] stg_payments
- [ ] stg_reviews
- [ ] stg_geolocation

### Canonical Model

- [ ] dim_customer
- [ ] dim_product
- [ ] dim_seller
- [ ] dim_date
- [ ] dim_location
- [ ] fct_orders
- [ ] fct_order_items
- [ ] fct_payments
- [ ] fct_reviews

### Data Quality

- [ ] Primary key tests
- [ ] Composite key tests
- [ ] Not null tests
- [ ] Referential integrity
- [ ] Business rule assertions

---

# Sprint 4 — Data Products

## Customer Analytics

- [ ] Customer 360
- [ ] Customer Segmentation
- [ ] Customer Lifetime Value

## Sales Analytics

- [ ] Sales Performance
- [ ] Revenue Trends
- [ ] Product Performance

## Operations Analytics

- [ ] Delivery Performance
- [ ] Seller Performance
- [ ] Payment Analytics

---

# Sprint 5 — Production Cloud Platform

## Infrastructure

- [ ] Terraform project
- [ ] Manage Cloud Storage with Terraform
- [ ] Manage BigQuery with Terraform
- [ ] Service Accounts
- [ ] IAM
- [ ] Cloud Run
- [ ] Cloud Scheduler

## Deployment

- [ ] Deploy ingestion service
- [ ] Scheduled ingestion
- [ ] Cloud logging
- [ ] Monitoring
- [ ] Replay/recovery operational workflow

---

# Sprint 6 — Applications

## Business Intelligence

- [ ] Looker Studio dashboard

## Internal Application

- [ ] Streamlit application

### Features

- [ ] Customer explorer
- [ ] Order explorer
- [ ] Seller explorer
- [ ] Platform monitoring

---

# Sprint 7 — Production Readiness

## CI/CD

- [ ] GitHub Actions
- [ ] Automated test execution
- [ ] Code formatting
- [ ] Linting
- [ ] Deployment pipeline

## Documentation

- [ ] Architecture diagrams
- [ ] Connector documentation
- [ ] Data dictionary
- [ ] Developer guide
- [ ] Operations guide
- [ ] Replay and recovery runbook

---

# Stretch Goals

These are intentionally out of scope for Version 1 but are potential future enhancements.

- [ ] Salesforce connector
- [ ] Shopify connector
- [ ] Stripe connector
- [ ] REST API ingestion
- [ ] Change Data Capture
- [ ] DuckDB local analytics
- [ ] Machine learning feature store
- [ ] Great Expectations integration
- [ ] Apache Iceberg
- [ ] Kubernetes deployment

---

# Current Progress

## Sprint 1 — Foundation & Ingestion Framework

✅ Complete

Mercury has a reusable, tested eight-source ingestion framework with shared CSV behaviour and storage-independent connectors.

## Sprint 2 — Cloud Raw Platform & Historical Replay

🟡 In progress

Completed:

- Cloud Storage Raw landing
- BigQuery Raw loading
- initial and incremental source simulation
- historical replay orchestration
- real GCS + BigQuery replay validation
- ADR-010 Phase 1 replay-state foundation
- ADR-010 Phase 2 stateful replay integration
- source-level failure isolation within a business date
- latest-attempt vs monotonic logical-completion semantics
- real GCP validation of successful, reattempt and partial-failure replay scenarios
- complete automated regression suite — 924 tests passing

Current focus:

- ADR-010 Phase 3 targeted recovery
- incomplete-source identification
- stage-aware retry behavior
- reconciliation of physical Raw data and control-plane state

---

# Sprint Log

## Day 1

- [x] Repository created
- [x] Mercury vision established
- [x] Project charter completed
- [x] README created

## Day 2

- [x] Nova Commerce business context documented
- [x] Architecture documentation created
- [x] Foundational ADRs completed
- [x] Ingestion framework designed

## Day 3

- [x] IngestionMetadata implemented
- [x] LocalStorageManager implemented
- [x] BaseConnector implemented
- [x] CustomerConnector implemented
- [x] IngestionRunner implemented
- [x] First real Olist customer ingestion completed
- [x] Raw file integrity verified with SHA-256
- [x] Full automated test suite passed

## Day 4

- [x] OrdersConnector implemented
- [x] Orders connector test suite passed
- [x] Real Olist orders ingestion completed
- [x] Orders Raw integrity verified with SHA-256
- [x] Customers + Orders executed successfully in one batch

## Day 5

### Order Items

- [x] Designed OrderItemsConnector contract
- [x] Defined order-item grain and composite source key
- [x] Implemented OrderItemsConnector
- [x] Order-items connector test suite passed
- [x] Real Olist order-items ingestion completed
- [x] Raw file integrity verified with SHA-256

### Products

- [x] Designed ProductsConnector contract
- [x] Defined product grain and source key
- [x] Implemented ProductsConnector
- [x] Products connector test suite passed
- [x] Real Olist products ingestion completed
- [x] Raw file integrity verified with SHA-256
- [x] Preserved source column semantics in Raw
- [x] Deferred product-category translation to downstream modelling

### Sellers

- [x] Designed SellersConnector contract
- [x] Defined seller grain and source key
- [x] Implemented SellersConnector
- [x] Sellers connector test suite passed
- [x] Real Olist sellers ingestion completed
- [x] Raw file integrity verified with SHA-256

### Engineering Lessons

- [x] Applied dataset grain concepts to order-level and item-level sources
- [x] Identified composite source keys without enforcing business uniqueness during ingestion
- [x] Maintained the boundary between technical ingestion validation and business data quality
- [x] Preserved source semantics in the immutable Raw layer
- [x] Deliberately deferred CSV abstraction until enough connector implementations existed to identify stable shared behavior

## Day 6

- [x] PaymentsConnector implemented and validated
- [x] ReviewsConnector implemented and validated
- [x] GeolocationConnector implemented and validated
- [x] All eight Olist source connectors completed
- [x] Full eight-source ingestion batch completed successfully
- [x] 1,550,851 source records ingested in one batch
- [x] Reviewed repeated CSV connector patterns
- [x] ADR-005 documented shared CSV connector abstraction
- [x] BaseCsvConnector implemented
- [x] Eight concrete connectors refactored to use BaseCsvConnector
- [x] Full regression suite passed — 478 tests
- [x] Post-refactor eight-source integration batch passed
- [x] Post-refactor record counts and SHA-256 checksums remained unchanged

## Day 7 — Cloud Raw Landing & Storage Abstraction

- [x] Review local storage architecture before introducing cloud storage
- [x] Document storage abstraction decision in ADR-006
- [x] Introduce `StorageManager` abstraction
- [x] Refactor `LocalStorageManager` to implement the shared storage contract
- [x] Update `BaseConnector` to depend on `StorageManager` rather than local storage
- [x] Verify all eight connectors remain storage-backend agnostic
- [x] Add abstraction-level tests and preserve existing local behavior
- [x] Implement `GCSStorageManager`
- [x] Configure Google Cloud authentication using Application Default Credentials
- [x] Preserve the existing Raw Landing hierarchy in Google Cloud Storage
- [x] Implement atomic create-only GCS uploads using generation preconditions
- [x] Preserve SHA-256 integrity metadata across local and cloud storage backends
- [x] Verify single-source ingestion against the real GCS bucket
- [x] Independently verify local and downloaded GCS SHA-256 hashes match
- [x] Verify duplicate ingestion is rejected without overwriting the existing Raw artifact
- [x] Run the complete automated test suite — 508 tests passing
- [x] Run all eight connectors against GCS successfully
- [x] Validate 1,550,851 total source records landed across the eight-source cloud batch

**Outcome:** Mercury now supports interchangeable local and Google Cloud Storage Raw Landing backends through a common storage abstraction. All eight source connectors can land immutable, byte-preserved source artifacts to GCS without cloud-specific connector logic. The cloud Raw Landing layer is validated and ready to become the source for BigQuery Raw loading.

## Day 8 — Incremental Source Simulation

- [x] Define initial vs incremental source-delivery strategy
- [x] Document source-delivery design in the ingestion framework
- [x] Add ADR-007 for historical source-delivery simulation
- [x] Implement `OlistSourceSimulator`
- [x] Keep source simulation upstream of connectors and storage
- [x] Simulate one-off deliveries for customers, products, sellers, and geolocations
- [x] Simulate daily Orders using `order_purchase_timestamp`
- [x] Derive daily Order Items from parent Orders
- [x] Derive daily Payments from parent Orders
- [x] Simulate independently arriving Reviews using `review_creation_date`
- [x] Support valid header-only zero-record daily deliveries
- [x] Preserve source schemas, values, duplicates, and row order
- [x] Implement immutable and failure-safe simulated deliveries
- [x] Validate simulation-critical source fields
- [x] Add comprehensive automated simulator tests
- [x] Validate simulator against the real Olist dataset
- [x] Verify daily parent-child relationships
- [x] Validate historical replay through `LocalStorageManager`
- [x] Validate historical replay through `GCSStorageManager`
- [x] Confirm all 580 automated tests pass

**Outcome:** Mercury can reproduce realistic initial and daily historical source deliveries without contaminating connector or storage responsibilities. The simulator provides deterministic source deliveries for historical replay and future orchestration testing.

## Day 9 — BigQuery Raw, Historical Replay & Recovery Foundation

### ADR-008 — BigQuery Raw Loading

- [x] Design BigQuery Raw loading as a separate warehouse responsibility
- [x] Implement explicit BigQuery Raw schemas
- [x] Implement `BigQueryRawLoader`
- [x] Define one-off/reference loading semantics
- [x] Define date-partitioned transactional loading semantics
- [x] Preserve source-faithful values in BigQuery Raw
- [x] Keep BigQuery logic out of source connectors
- [x] Add comprehensive Raw-loader automated tests
- [x] Validate transactional loading against real BigQuery
- [x] Validate reference-table loading against real BigQuery

### ADR-009 — Historical Replay Orchestration

- [x] Introduce `SourceDelivery` and `SourceDeliveryBatch`
- [x] Introduce source-provider abstraction
- [x] Implement `OlistSimulatedSourceProvider`
- [x] Implement `HistoricalReplayRunner`
- [x] Separate initial/reference loading from daily incremental replay
- [x] Validate expected initial source membership
- [x] Validate expected daily source membership
- [x] Reject empty source-delivery batches
- [x] Preserve valid zero-record deliveries
- [x] Fail clearly on unsupported source objects
- [x] Preserve connector-produced landing paths for warehouse handoff
- [x] Implement chronological date-range replay
- [x] Preserve storage and warehouse abstraction boundaries
- [x] Complete automated replay regression suite
- [x] Validate historical replay for 2017-05-12 through 2017-05-15 against real GCS and BigQuery
- [x] Verify all four transactional BigQuery partitions for each replayed date
- [x] Validate one-off initial load for customers, products, sellers, and geolocations against real GCS and BigQuery

### Real Historical Replay Validation

Successfully replayed:

```text
2017-05-12
2017-05-13
2017-05-14
2017-05-15
```

for:

```text
orders
order_items
payments
reviews
```

Verified:

- [x] 4/4 sources succeeded for every replay date
- [x] Correct BigQuery date partitions created
- [x] GCS Raw artifacts landed under the expected ingestion dates
- [x] Connector row counts matched warehouse load results
- [x] Historical replay completed successfully end to end

### Real Initial / Reference Load Validation

Successfully loaded:

```text
customers      99,441 rows
products       32,951 rows
sellers         3,095 rows
geolocations 1,000,163 rows
```

Verified:

- [x] 4/4 reference sources succeeded
- [x] GCS Raw artifacts created
- [x] BigQuery Raw tables created and loaded
- [x] One-off source semantics remained separate from transactional replay

### ADR-010 Phase 1 — Replay State Foundation

- [x] Define source-level replay state architecture
- [x] Define `ReplayStatus`
- [x] Define `ReplayStage`
- [x] Implement immutable `ReplayStateRecord`
- [x] Enforce `SUCCESS | WAREHOUSE` as the only successful terminal state
- [x] Introduce `ReplayStateStore` backend-independent contract
- [x] Adopt append-only replay event history
- [x] Implement `BigQueryReplayStateStore`
- [x] Define explicit replay-state BigQuery schema
- [x] Keep operational metadata outside the Raw dataset
- [x] Partition replay state by `delivery_date`
- [x] Cluster replay state by `source_object`
- [x] Implement replay history retrieval
- [x] Implement latest-state retrieval
- [x] Implement latest-per-source date retrieval
- [x] Implement derived date-completeness helper
- [x] Enforce single-date input for completeness evaluation
- [x] Complete Phase 1 automated regression suite — 847 tests passing

### ADR-010 Phase 2 — Design & Working Implementation

- [x] Define `run_id` semantics
- [x] Define source-level partial-success execution model
- [x] Decide to preserve ingestion/warehouse stage separation
- [x] Decide to attempt all safe independent source work within a date
- [x] Separate source availability from date completeness
- [x] Define incomplete-date range stopping semantics
- [x] Produce initial Phase 2 implementation and automated tests
- [ ] Revise latest-attempt vs logical-completion semantics
- [ ] Establish stable Phase 2 implementation checkpoint
- [ ] Validate Phase 2 against real GCP

**Important checkpoint:** The initial Phase 2 implementation exposed an important recovery-state distinction before production validation:

```text
latest replay attempt state
        ≠
logical source completion state
```

Under Mercury's immutable historical delivery model, an earlier successful warehouse materialisation must not become logically incomplete merely because a later replay attempt fails.

This semantic revision will be completed before ADR-010 Phase 2 is treated as stable.

### Day 9 Outcome

Mercury now has a validated end-to-end cloud Raw path:

```text
Historical Source Delivery
        ↓
Source Provider
        ↓
Historical Replay Runner
        ↓
Reusable Connectors
        ↓
Immutable GCS Raw
        ↓
BigQuery Raw
```

Both incremental historical replay and one-off reference loading have been validated against real Google Cloud infrastructure.

The platform also has the first durable control-plane foundation for source-level replay history and future targeted recovery.

The next engineering checkpoint is to finalise ADR-010 Phase 2's distinction between replay-attempt state and logical source completion before implementing automatic recovery.

## Day 10 — Historical Replay State & Failure Isolation

### ADR-010 Phase 2 — Stateful Historical Replay

- [x] Integrate `ReplayStateStore` into `HistoricalReplayRunner`
- [x] Introduce one `run_id` per top-level replay invocation
- [x] Preserve unique `event_id` values for individual replay-state transitions
- [x] Track replay state independently for each `(delivery_date, source_object)`
- [x] Preserve explicit ingestion and warehouse stage boundaries
- [x] Execute each daily connector independently through `IngestionRunner`
- [x] Preserve connector-level `IngestionMetadata` during replay orchestration
- [x] Attempt all safe ingestion work within a business date
- [x] Prevent one source ingestion failure from blocking sibling sources
- [x] Attempt warehouse loading independently for every successfully ingested source
- [x] Prevent one warehouse failure from blocking eligible sibling sources
- [x] Skip warehouse loading for sources that failed ingestion
- [x] Preserve successfully materialised Raw data when another source for the same date fails
- [x] Attach `partial_day_result` to incomplete-date replay errors
- [x] Derive date completeness only after all safe work for the date has been attempted
- [x] Stop historical range progression after the first genuinely incomplete date
- [x] Treat replay-state persistence as control-plane state and fail immediately if it cannot be recorded

### Replay-State Semantics

- [x] Distinguish latest replay attempt from logical source completion
- [x] Add `get_completed_for_date()` to the replay-state contract
- [x] Implement logical-completion queries in `BigQueryReplayStateStore`
- [x] Define `SUCCESS | WAREHOUSE` as the only successful source-completion state
- [x] Make logical completion monotonic once a source has successfully materialised in BigQuery Raw
- [x] Ensure a later failed replay attempt does not erase an earlier successful completion
- [x] Preserve failed reattempts in append-only history for diagnostics and auditability
- [x] Keep `is_date_complete()` as a pure completeness function operating on logical-completion records

### Automated Validation

- [x] Expand replay-state and orchestration coverage for Phase 2
- [x] Validate successful per-source state-event sequences
- [x] Validate shared `run_id` semantics across a replay invocation
- [x] Validate unique `event_id` values for individual transitions
- [x] Validate ingestion-failure isolation within a date
- [x] Validate warehouse-failure isolation within a date
- [x] Validate partial-day results after source failure
- [x] Validate incomplete-date range stopping
- [x] Validate monotonic logical completion after later failed attempts
- [x] Run the complete automated test suite — 924 tests passing

### Real GCP Integration Validation

- [x] Execute a successful three-day historical replay for 2017-05-16 through 2017-05-18
- [x] Validate all 12 transactional source deliveries through GCS Raw and BigQuery Raw
- [x] Validate replay-state persistence in `metadata.historical_replay_state`
- [x] Validate expected successful state sequence: `RUNNING | INGESTION` → `RUNNING | WAREHOUSE` → `SUCCESS | WAREHOUSE`
- [x] Validate one shared `run_id` across the complete three-day `run_range()` invocation
- [x] Validate 36 append-only replay-state events across 3 dates × 4 sources
- [x] Re-run an already-complete date and validate that all four new ingestion attempts can fail without regressing logical completion
- [x] Confirm latest-attempt state can be `FAILED | INGESTION` while logical completion remains `SUCCESS | WAREHOUSE`
- [x] Create a controlled partial-failure scenario by pre-landing only Payments in immutable GCS Raw for 2017-05-19
- [x] Validate Payments fails ingestion because its immutable destination already exists
- [x] Validate Orders, Order Items, and Reviews continue independently through ingestion and BigQuery Raw loading
- [x] Validate the partial replay returns 3/4 successful ingestion results and 3 successful warehouse results
- [x] Validate Payments receives no warehouse attempt after failed ingestion
- [x] Validate the business date is correctly classified as incomplete because Payments has never reached `SUCCESS | WAREHOUSE`
- [x] Validate successfully materialised sibling sources remain available despite the incomplete date
- [x] Clean local simulator, GCS Raw, BigQuery Raw, and replay-state test data after integration validation
- [x] Preserve empty BigQuery Raw table structures for future full historical replay

**Outcome:** ADR-010 Phase 2 is implemented and validated. Mercury now maintains durable, append-only source-level replay state while treating each business date as a completeness boundary containing independent source deliveries. Source failures no longer discard or block safe sibling work: successfully ingested sources continue to BigQuery Raw and remain available even when another source fails. Latest-attempt state is deliberately distinct from monotonic logical completion, allowing operational failures to remain visible without incorrectly invalidating data that was successfully materialised by an earlier run. An incomplete date stops progression to later dates only after all safe work for that date has been attempted. Targeted recovery execution remains Phase 3 of ADR-010.

## Day 11 - Data Security, Privacy, and Data-Leak Prevention

ADR-011 was introduced before continuing targeted recovery execution to ensure
Mercury's operational and infrastructure boundaries are safe for customer data.

Completed:

- **Phase 1 — Security Audit**
  - Audited persistence, logging, exception, storage, orchestration, and cloud
    boundaries for potential data leakage.
  - Identified unsafe propagation of raw exception text into persisted
    operational metadata.

- **Phase 2 — Safe Operational Errors**
  - Introduced Mercury-authored `OperationalError` values.
  - Removed persistence of raw exception text from connector and replay failure
    paths.
  - Preserved exception chaining for transient debugging.
  - Added security regression tests preventing sensitive exception content from
    reaching persisted operational state.

- **Phase 3 — Infrastructure Security and Least Privilege**
  - Introduced a dedicated `mercury-runtime` service account.
  - Applied least-privilege GCS and BigQuery permissions.
  - Validated immutable Raw object creation and denied runtime deletion.
  - Confirmed runtime cannot create arbitrary BigQuery datasets.
  - Removed broad BigQuery `projectReaders`, `projectWriters`, and
    `projectOwners` dataset access.
  - Validated explicit runtime access after IAM hardening.
  - Confirmed `BigQueryReplayStateStore` operates correctly within the
    restricted runtime boundary.
  - No long-lived service-account keys are required.

Detailed security findings and validation evidence are maintained under
`docs/security/`.

**Status:** Complete.

With ADR-011 complete, development resumes with ADR-010 Phase 3B — targeted
recovery execution.

  **Outcome:** Mercury now has an explicitly validated least-privilege runtime boundary, safe persisted operational errors, immutable Raw storage behavior, restricted destructive cloud access, explicit BigQuery dataset access, and separation between infrastructure administration and application runtime.

  