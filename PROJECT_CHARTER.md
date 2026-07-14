# Open Commerce Data Platform — Project Charter

## 1. Vision

Build a reusable cloud-native data foundation that transforms raw operational data into trusted, reusable data products.

Mercury demonstrates how modern organizations can standardize data ingestion, transformation, testing, and publishing through a layered platform architecture.

The first implementation focuses on e-commerce using publicly available datasets, while the platform itself is intentionally designed so its architectural patterns can be applied across industries.

Mercury is founded on one simple principle:

Future innovation should focus on creating business value rather than rebuilding data foundations.

## 2. Problem Statement

Many organizations generate operational data across multiple independent systems.

Over time, project-specific pipelines, duplicated transformation logic, inconsistent business definitions, and isolated analytical solutions create significant engineering overhead.

As new business requirements emerge, engineering teams often spend more time rebuilding data foundations than delivering business value.

Mercury addresses this challenge by establishing a reusable data foundation that standardizes ingestion, modelling, testing, and publishing.

The objective is to enable future analytical use cases to build upon trusted platform capabilities rather than recreating them for every project.

## 3. Target Users

The platform supports:

- Analytics Engineers
- Data Engineers
- Data Analysts
- Data Scientists
- Operations teams
- Commercial and product stakeholders
- Platform Engineers
- Applications consuming curated data products

## 4. Primary Use Cases

### Sales Performance

Measure:

- revenue;
- order volume;
- average order value;
- product category performance;
- revenue trends.

### Customer 360

Provide a trusted customer-level view containing:

- order history;
- total spend;
- purchase frequency;
- most recent purchase;
- customer segments;
- review behaviour.

### Delivery Reliability

Measure:

- estimated versus actual delivery time;
- delayed orders;
- fulfilment duration;
- delivery performance by seller and location.

### Seller Performance

Measure:

- seller revenue;
- orders fulfilled;
- average review score;
- cancellation and delay rates;
- product performance.

## 5. Data Domains

The initial domain model includes:

- customers;
- orders;
- order items;
- products;
- sellers;
- payments;
- reviews;
- delivery events;
- dates and locations.

## 6. Platform Layers

1. Operational source systems
2. Immutable raw storage
3. Staging and standardization
4. Core dimensional model
5. Data products and feature tables
6. Dashboards, applications, and analytical outputs

## 7. Core Platform Capabilities

The platform will provide:

- standardized source ingestion;
- immutable raw data retention;
- reusable transformation patterns;
- canonical business modelling;
- automated data quality validation;
- reusable data products;
- orchestration;
- observability;
- infrastructure as code;
- automated testing and deployment;
- documented architecture and engineering decisions.

## 8. Version 1 Scope

Version 1 will include:

- public e-commerce datasets representing multiple operational systems;
- local ingestion using Python;
- raw files stored without modification;
- raw data loaded into BigQuery;
- staging transformations;
- a dimensional warehouse model;
- automated data quality assertions;
- sales and customer data products;
- one dashboard or lightweight application;
- scheduled cloud execution;
- Terraform infrastructure;
- basic CI/CD.

## 9. Out of Scope for Version 1

Version 1 will not include:

- real-time streaming;
- Kubernetes;
- multi-cloud deployment;
- enterprise-scale governance tooling;
- complex machine learning operations;
- direct integration with a real commercial e-commerce platform;
- production workloads containing personal customer information.

## 10. Success Criteria

Version 1 is successful when:

1. Source data can be ingested reproducibly.
2. Original source files are preserved for replay.
3. Raw data is transformed into trusted dimensional models.
4. Data quality rules are tested automatically.
5. Sales and customer data products are available to consumers.
6. A dashboard or application demonstrates business value.
7. The platform can be deployed from documented code.
8. New analytical use cases can reuse existing platform capabilities without redesigning the architecture.

## 11. Engineering Objectives

Mercury is designed to demonstrate modern data platform engineering practices including:

- cloud-native architecture;
- reusable ingestion patterns;
- layered data modelling;
- dimensional warehouse design;
- data quality engineering;
- observability;
- infrastructure as code;
- continuous integration and deployment;
- architectural decision making;
- reusable data products.