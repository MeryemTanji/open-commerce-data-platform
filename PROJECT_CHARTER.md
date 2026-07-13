# Open Commerce Data Platform — Project Charter

## 1. Vision

Build a production-inspired e-commerce data platform that ingests,
transforms, validates, and publishes trusted data products using modern
Analytics Engineering and Data Engineering practices.

The first implementation focuses on e-commerce, while shared capabilities
such as ingestion, testing, orchestration, observability, security, and
deployment are designed to be reusable.

## 2. Problem Statement

E-commerce data is commonly distributed across systems responsible for
customers, orders, products, payments, sellers, reviews, and delivery events.

Without a reliable data platform, these sources can produce:

- inconsistent business definitions;
- duplicated or incomplete records;
- unreliable reporting;
- limited visibility into data quality;
- tightly coupled source-to-dashboard pipelines;
- difficulty reproducing or reprocessing historical data.

This project will build a layered platform that converts raw source data into
tested and documented data products.

## 3. Target Users

The platform supports:

- Analytics Engineers
- Data Engineers
- Data Analysts
- Data Scientists
- Operations teams
- Commercial and product stakeholders
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

1. Source data
2. Immutable raw storage
3. Staging and standardization
4. Core dimensional model
5. Data products and feature tables
6. Dashboards, applications, and analytical outputs

## 7. Core Platform Capabilities

The platform will provide:

- repeatable source ingestion;
- immutable raw payload retention;
- ingestion audit metadata;
- standardized transformations;
- dimensional data modeling;
- automated data quality tests;
- orchestration;
- structured logging and observability;
- infrastructure as code;
- automated testing and deployment;
- documented and versioned data products.

## 8. Version 1 Scope

Version 1 will include:

- one public e-commerce dataset;
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
8. A new source can reuse the established ingestion and quality patterns.

## 11. Portfolio Goal

This repository should demonstrate:

- Python and SQL development;
- dimensional data modeling;
- Analytics Engineering;
- cloud data engineering;
- automated testing;
- orchestration;
- observability;
- infrastructure as code;
- CI/CD;
- architecture decisions and engineering trade-offs.