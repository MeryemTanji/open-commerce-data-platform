# Mercury

> A cloud-native commerce data platform built on Google Cloud.

Mercury is an end-to-end commerce data platform that demonstrates how modern organizations build reliable, cloud-native data systems.

The platform ingests raw operational data, transforms it into trusted analytical models, and publishes reusable data products for business intelligence, operational reporting, and machine learning.

---

## Why Mercury?

Modern e-commerce businesses generate data across many operational systems including orders, customers, payments, products, reviews, and logistics.

Without a structured data platform, these systems often lead to inconsistent reporting, duplicated business logic, and unreliable metrics.

Mercury demonstrates how these disconnected operational datasets can be transformed into governed, reusable data products through modern Analytics Engineering practices.

---

## Design Philosophy

Mercury is intentionally built as if it were the internal data platform of a growing e-commerce company.

Every architectural decision, repository structure, and engineering practice reflects how a modern platform engineering team would design, build, and operate production analytics infrastructure.

The goal is not to build a tutorial project.

The goal is to build a platform.

---

## Overview

Mercury is a cloud-native commerce data platform that transforms raw operational data into trusted, reusable data products.

Built using modern Analytics Engineering and Data Engineering practices, Mercury demonstrates how organizations design scalable data platforms using layered architecture, infrastructure as code, automated testing, and cloud-native services.

---

## Architecture

## Architecture

```text
┌──────────────┐
│   Sources    │
└──────┬───────┘
       │
       ▼
┌──────────────┐
│ Raw Landing  │
└──────┬───────┘
       │
       ▼
┌──────────────┐
│   Staging    │
└──────┬───────┘
       │
       ▼
┌──────────────┐
│ Canonical    │
│ Data Model   │
└──────┬───────┘
       │
       ▼
┌──────────────┐
│ Data Products│
└──────┬───────┘
       │
       ▼
Dashboards • APIs • Apps
```

> A detailed architecture diagram will be added as the platform evolves.

 > A detailed architecture diagram will be added as the platform evolves.

---

## Core Capabilities

- Data ingestion
- Immutable raw storage
- Data quality validation
- Dimensional modelling
- Feature engineering
- Data products
- Infrastructure as Code
- Observability
- CI/CD

---

## Technology Stack

| Capability      | Technology            | Purpose                    |
| --------------- | --------------------- | -------------------------- |
| Programming     | Python                | Data ingestion & utilities |
| Warehouse       | BigQuery              | Analytical storage         |
| Transformations | Dataform              | SQL modelling              |
| Infrastructure  | Terraform             | Infrastructure as Code     |
| Orchestration   | Cloud Run + Scheduler | Automated ingestion        |
| BI              | Looker Studio         | Dashboards                 |
| Applications    | Streamlit             | Internal tools             |

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

---

## Roadmap

### Phase 0 — Foundation
- [x] Project Charter
- [x] Repository Structure
- [ ] Architecture Documentation

### Phase 1 — Local Development
- [ ] Source Connectors
- [ ] Raw Landing Zone
- [ ] Initial Transformations

### Phase 2 — Cloud Platform
- [ ] BigQuery
- [ ] Cloud Storage
- [ ] Dataform

### Phase 3 — Production
- [ ] Terraform
- [ ] Cloud Run
- [ ] CI/CD

### Phase 4 — Data Products
- [ ] Customer 360
- [ ] Sales Analytics
- [ ] Delivery Analytics

---

## Documentation

Project documentation is available in the `architecture/` directory.

This includes:

- Architecture Decision Records (ADRs)
- Design principles
- Architecture diagrams
- Project charter

---

## Engineering Principles

Mercury is developed according to the following principles:

- Build what belongs.
- Document why it exists.
- Automate how it runs.
- Design for maintainability.
- Prefer clarity over cleverness.
- Build reusable capabilities before reusable code.

---

## License

This project is licensed under the MIT License.