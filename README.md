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

Future innovation should focus on creating business value—not rebuilding data foundations.

---

## Overview

Mercury follows a layered architecture that separates operational data ingestion, standardisation, business modelling and data product generation.

Each layer has a clearly defined responsibility, allowing the platform to evolve incrementally while maintaining consistency across data products.

This architecture enables new analytical use cases to reuse existing platform capabilities rather than rebuilding transformation logic for every project.

---

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

---

## Core Capabilities

- Standardised source ingestion
- Immutable raw data storage
- Layered data transformation
- Canonical business modelling
- Reusable data products
- Data quality validation
- Infrastructure as Code
- Platform observability
- Automated deployment

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