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

# Sprint 2 — BigQuery Foundation

## Google Cloud

- [x] Create GCP project
- [x] Enable required APIs
- [x] Configure authentication

## Storage

- [x] Create Cloud Storage bucket
- [x] Implement GCSStorageManager
- [x] Upload raw files to Cloud Storage

## BigQuery

- [x] Create datasets
- [ ] Create raw layer
- [ ] Load raw source tables
- [ ] Create ingestion audit table

---

# Sprint 3 — Analytics Engineering

## Dataform

### Raw Layer

- [ ] Raw customers
- [ ] Raw orders
- [ ] Raw order items
- [ ] Raw products
- [ ] Raw sellers
- [ ] Raw payments
- [ ] Raw reviews
- [ ] Raw geolocation

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

# Sprint 5 — Cloud Platform

## Infrastructure

- [ ] Terraform project
- [ ] Cloud Storage
- [ ] BigQuery
- [ ] Service Accounts
- [ ] IAM
- [ ] Cloud Run
- [ ] Cloud Scheduler

## Deployment

- [ ] Deploy ingestion service
- [ ] Scheduled ingestion
- [ ] Cloud logging
- [ ] Monitoring

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
- [ ] Automated tests
- [ ] Code formatting
- [ ] Linting
- [ ] Deployment pipeline

## Documentation

- [ ] Architecture diagrams
- [ ] Connector documentation
- [ ] Data dictionary
- [ ] Developer guide
- [ ] Operations guide

---

# Stretch Goals

These are intentionally out of scope for Version 1 but are potential future enhancements.

- [ ] Salesforce connector
- [ ] Shopify connector
- [ ] Stripe connector
- [ ] REST API ingestion
- [ ] Incremental loading
- [ ] Change Data Capture
- [ ] DuckDB local analytics
- [ ] Machine learning feature store
- [ ] Great Expectations integration
- [ ] Apache Iceberg
- [ ] Kubernetes deployment

---

# Current Progress

## Sprint 1

### Phase 0 — Foundation

✅ Complete

### Phase 1 — Local Development

✅ Complete

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
- [x] Orders raw integrity verified with SHA-256
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
- [x] Deliberately deferred CSV abstraction until enough connector implementations exist to identify stable shared behavior

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

### Day 7 — Cloud Raw Landing & Storage Abstraction

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