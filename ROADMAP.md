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
- [ ] OrdersConnector
- [ ] ProductsConnector
- [ ] SellersConnector
- [ ] PaymentsConnector
- [ ] ReviewsConnector
- [ ] GeolocationConnector
- [x] Runner

### Local Raw Landing

- [x] First successful customer ingestion
- [x] Verify customer raw file integrity with SHA-256
- [x] Execute CustomerConnector through IngestionRunner
- [ ] First successful orders ingestion
- [ ] First successful products ingestion
- [ ] First successful payments ingestion
- [ ] First successful reviews ingestion
- [ ] First successful sellers ingestion
- [ ] First successful geolocation ingestion

### Testing

- [x] Metadata tests
- [x] Storage tests
- [x] Base connector tests
- [x] Customer connector tests
- [x] Runner tests
- [x] End-to-end customer ingestion test
- [ ] Multi-connector end-to-end ingestion tests

---

# Sprint 2 — BigQuery Foundation

## Google Cloud

- [ ] Create GCP project
- [ ] Enable required APIs
- [ ] Configure authentication

## Storage

- [ ] Create Cloud Storage bucket
- [ ] Implement GCSStorageManager
- [ ] Upload raw files to Cloud Storage

## BigQuery

- [ ] Create datasets
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
- [ ] stg_products
- [ ] stg_sellers
- [ ] stg_payments
- [ ] stg_reviews

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

🟩🟩🟩🟩🟩⬜⬜⬜

Current milestone:

➡ Complete remaining source connectors

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