# ADR-007 — Adopt Mixed Initial and Incremental Source Delivery Patterns

## Status

Accepted

---

## Context

Mercury uses the public Olist e-commerce dataset as the initial source environment for development and portfolio demonstration.

The Olist dataset is distributed as a collection of static historical CSV files. Ingesting each complete file only once is sufficient to validate the basic ingestion framework, but it does not represent how a production commerce data platform typically receives data over time.

Real source systems commonly expose different delivery patterns.

Transactional systems may continuously produce new orders, payments, events, or reviews, while master and reference datasets may be loaded initially and refreshed on a different schedule.

Mercury should exercise these different ingestion patterns so that later platform capabilities can demonstrate:

- recurring ingestion;
- incremental warehouse loading;
- ingestion history;
- historical replay;
- ingestion-date partitioning;
- late-arriving related data;
- idempotent execution;
- different source refresh frequencies;
- source-to-Raw lineage.

However, Mercury must not manufacture source history that cannot be supported by the available data.

Some Olist datasets contain reliable temporal information that can be used to reconstruct when records should appear in a simulated source delivery.

Others do not.

For example, Orders contain `order_purchase_timestamp` and Reviews contain `review_creation_date`.

Products, Sellers, Customers, and Geolocations do not contain reliable creation or change timestamps from which their historical source availability can be reconstructed.

A design decision is therefore required regarding how Mercury should simulate source deliveries across datasets with different levels of temporal information.

---

## Decision

Mercury will adopt a **mixed source-delivery model** for Version 1.

Sources with defensible temporal information will be replayed as **daily incremental deliveries**.

Sources without reliable temporal information will be treated as **initial master or reference loads** and will remain static during the Version 1 simulation.

Mercury will not fabricate timestamps or artificial change histories solely to make every source appear incremental.

The guiding principle is:

> Simulate temporal behaviour where the source provides defensible temporal information; otherwise treat the source as an initial master or reference load.

This decision describes the simulated source behaviour.

It does not change the existing Mercury connector or Raw Landing contracts.

---

## Source Classification

Mercury Version 1 classifies the eight Olist source objects as follows:

| Source Object | Delivery Pattern | Temporal Basis |
|---|---|---|
| Customers | Initial load | No reliable customer creation timestamp |
| Products | Initial load | No reliable product creation or change timestamp |
| Sellers | Initial load | No reliable seller onboarding or change timestamp |
| Geolocations | Initial load | Static geographic reference data |
| Orders | Daily incremental | `order_purchase_timestamp` |
| Order Items | Daily incremental | Derived from parent Order |
| Payments | Daily incremental | Derived from parent Order |
| Reviews | Daily incremental | `review_creation_date` |

This classification is specific to the temporal information available in the Olist source and the scope of Mercury Version 1.

It is not intended to imply that Customers, Products, or Sellers are inherently static entities in a real commerce platform.

---

## Incremental Delivery Rules

### Orders

Orders define the primary transactional timeline.

An Order is delivered on the business date represented by:

`DATE(order_purchase_timestamp)`

Each Order therefore appears in exactly one simulated Orders delivery.

For example:

```text
2017-05-01
    Orders purchased on 2017-05-01

2017-05-02
    Orders purchased on 2017-05-02

2017-05-03
    Orders purchased on 2017-05-03
```