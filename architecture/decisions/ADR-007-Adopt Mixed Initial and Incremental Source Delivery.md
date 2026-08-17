# ADR-007 — Adopt Mixed Initial and Incremental Source Delivery Patterns

## Status

Accepted

## Date

2026-08-16

---

## Context

Mercury uses the public Olist e-commerce dataset as its initial source environment.

Olist is distributed as static historical CSV files. Loading each full file once is sufficient to prove basic ingestion, but it does not resemble how operational commerce systems typically deliver data over time.

Real platforms commonly combine different delivery patterns.

Transactional systems continuously generate new business events, while master and reference sources may be loaded initially and refreshed on separate schedules.

Mercury should exercise realistic temporal behavior so that later platform capabilities can demonstrate:

- recurring ingestion;
- daily incremental delivery;
- historical replay;
- ingestion history;
- partitioned warehouse loading;
- late-arriving related data;
- idempotent execution;
- different source refresh frequencies;
- source-to-Raw lineage.

However, Mercury must not manufacture source history that cannot be supported by the available data.

Some Olist sources contain defensible temporal information.

For example:

- Orders contain `order_purchase_timestamp`;
- Reviews contain `review_creation_date`.

Other sources do not contain reliable creation or change timestamps from which their historical availability can be reconstructed.

A source-delivery strategy is therefore required that reflects the temporal evidence actually present in the dataset.

---

## Decision

Mercury Version 1 will use a **mixed source-delivery model**.

Sources with defensible temporal information will be replayed as **daily incremental deliveries**.

Sources without reliable temporal information will be treated as **initial master or reference loads** and remain static during the Version 1 simulation.

Mercury will not fabricate timestamps or artificial update histories simply to make every source incremental.

The guiding principle is:

> Simulate temporal behaviour where the source provides defensible temporal information; otherwise treat the source as an initial master or reference load.

This decision models source-delivery behavior only.

It does not change the existing connector or Raw Landing contracts.

---

## Source Classification

| Source Object | Version 1 Delivery Pattern | Temporal Basis |
|---|---|---|
| Customers | Initial load | No reliable customer creation timestamp |
| Products | Initial load | No reliable product creation/change timestamp |
| Sellers | Initial load | No reliable seller onboarding/change timestamp |
| Geolocations | Initial load | Static geographic reference data |
| Orders | Daily incremental | `order_purchase_timestamp` |
| Order Items | Daily incremental | Derived from parent Order |
| Payments | Daily incremental | Derived from parent Order |
| Reviews | Daily incremental | `review_creation_date` |

This classification reflects Olist's available temporal evidence.

It does **not** imply that Customers, Products, or Sellers are inherently static in real commerce systems.

---

## Initial / Master-Reference Sources

### Customers

Olist does not provide a reliable customer creation timestamp.

Mercury therefore treats the available customer dataset as an existing customer master available at the start of the simulation.

Mercury will not infer customer creation from the first observed Order because that would introduce derived business interpretation into source simulation.

---

### Products

Olist does not provide reliable product creation, activation, or modification timestamps.

Products are therefore treated as an initial catalogue that remains unchanged during Version 1.

This is a simulation limitation, not an assertion that product catalogues are static in production.

---

### Sellers

Olist does not provide reliable seller onboarding or modification timestamps.

Sellers are therefore treated as an existing marketplace master dataset available at simulation start.

---

### Geolocations

Geolocations are treated as static reference data.

They do not represent transactional business activity and are loaded once during the initial source load.

---

## Daily Incremental Sources

### Orders

Orders define the main transactional replay timeline.

A source Order is delivered on:

```text
DATE(order_purchase_timestamp)
```

Each Order therefore appears in exactly one simulated Orders delivery.

For example:

```text
2017-05-10
    only Orders purchased on 2017-05-10

2017-05-11
    only Orders purchased on 2017-05-11
```

This is an incremental delivery model, not a cumulative daily snapshot.

---

### Order Items

Order Items do not contain the source timestamp required to determine when their parent Order entered the simulated platform.

Mercury therefore derives their delivery membership from Orders.

For each business date:

1. select Orders purchased on that date;
2. collect their `order_id` values;
3. select all Order Items whose `order_id` belongs to that set.

Conceptually:

```text
Orders for Day D
        ↓
Order IDs for Day D
        ↓
Order Items for those Order IDs
```

All Order Items associated with an Order are delivered with that Order in Version 1.

Mercury does not use `shipping_limit_date` as an artificial Order Item creation date.

---

### Payments

Payments use the same parent-derived strategy.

For each business date:

1. select the daily Orders;
2. collect their `order_id` values;
3. deliver all Payment rows associated with those Orders.

Multiple or split payment rows remain preserved.

Mercury does not fabricate a payment creation timestamp.

---

### Reviews

Reviews follow their own temporal field:

```text
review_creation_date
```

They do not inherit the purchase date of the parent Order.

This intentionally allows related records to arrive independently.

For example:

```text
2017-05-01
    Order ABC arrives

2017-05-08
    Review for Order ABC arrives
```

This gives Mercury realistic late-arriving related data for downstream warehouse and transformation testing.

---

## Initial and Daily Delivery Shape

Conceptually:

```text
INITIAL DELIVERY

customers
products
sellers
geolocations
        ↓
Mercury ingestion
```

followed by:

```text
DAILY DELIVERY — Day D

orders
order_items
payments
reviews
        ↓
Mercury ingestion
```

The four daily transactional sources are generated for every requested replay date.

A valid daily source may contain zero records.

---

## Empty Daily Deliveries

A source can legitimately have no business records for a particular day.

Mercury represents this as a valid **header-only CSV**, rather than omitting the source file.

This distinguishes:

```text
delivery succeeded with zero records
```

from:

```text
delivery failed or never arrived
```

The resulting connector metadata should therefore report:

```text
record_count = 0
```

while still treating the source delivery as valid.

---

## Historical Replay

Mercury preserves the historical Olist business dates during simulation.

It does not rewrite historical source events to the current execution date.

For example:

```text
simulation_date = 2017-05-10
```

may later land as:

```text
raw/order_platform/orders/
    ingestion_date=2017-05-10/
        olist_orders_dataset.csv
```

The date on which the developer physically executes the replay is a separate runtime concern.

This allows Mercury to reconstruct a meaningful historical ingestion timeline.

---

## Source Simulation Boundary

Source simulation is upstream of the ingestion framework.

```text
Immutable Olist Files
        ↓
OlistSourceSimulator
        ↓
Initial / Daily Simulated CSV
        ↓
Existing Connector
        ↓
StorageManager
        ↓
Raw Landing
```

The simulator determines **which rows are delivered in a batch**.

It does not change the source values themselves.

The simulator must not:

- rename source columns;
- reorder columns;
- cast source values;
- normalize timestamps;
- trim or clean values;
- deduplicate records;
- enrich records;
- translate source values;
- apply business-quality rules;
- modify the immutable original Olist files;
- write directly to GCS;
- write directly to BigQuery.

Existing connectors continue to receive valid CSV files following their existing source contracts.

No connector requires incremental-delivery logic merely because a source is simulated daily.

---

## Source Preservation

The original Olist files remain immutable source material.

Generated simulation data is stored separately.

Conceptually:

```text
data/
├── source/
│   └── olist/
│       └── immutable original files
│
└── simulated/
    └── olist/
        ├── initial/
        └── daily/
            ├── 2017-05-10/
            ├── 2017-05-11/
            └── ...
```

Generated simulation files are reproducible artifacts and are not the authoritative original dataset.

---

## Why Mercury Does Not Fabricate Temporal Data

Mercury could assign artificial dates to Customers, Products, or Sellers to make all eight sources incremental.

This is rejected.

For example, assigning a Customer creation date based on their earliest observed Order may be analytically useful, but it does not prove that the customer record entered the operational source on that date.

Likewise, randomly assigning Product or Seller creation dates would create entirely synthetic history.

The absence of temporal information is treated as a limitation of the source rather than something the ingestion layer should silently manufacture.

Derived temporal concepts may later be created explicitly in Dataform or analytical models where their business meaning can be documented.

---

## Relationship to Raw and BigQuery

This decision establishes the **source delivery pattern**.

It does not dictate storage or warehouse implementation details.

The downstream flow is:

```text
Simulated Source Delivery
        ↓
Connector
        ↓
Immutable GCS Raw Artifact
        ↓
BigQuery Raw Loader
        ↓
Queryable Raw Table / Partition
```

ADR-008 separately defines how these delivery patterns are represented in BigQuery:

- initial/master-reference sources → unpartitioned whole-table loads;
- daily transactional sources → historical ingestion-time partitions.

---

## Alternatives Considered

### Alternative 1 — Load Every Olist Dataset Once

Rejected because it would prove only one-time batch loading and would not exercise:

- recurring ingestion;
- historical replay;
- incremental warehouse loading;
- partitioning;
- late-arriving related data.

---

### Alternative 2 — Re-Ingest Every Complete Olist File Every Day

Rejected because this would create artificial full snapshots containing large amounts of repeated data.

It would create partitions without demonstrating genuine incremental source behavior.

---

### Alternative 3 — Make Every Source Incremental

Rejected because Customers, Products, Sellers, and Geolocations lack defensible temporal fields for reconstructing their historical source availability.

Architectural uniformity is not sufficient justification for inventing source history.

---

### Alternative 4 — Infer Missing Master-Data Dates from Transactions

For example, Mercury could use a Customer's earliest Order date as the customer's creation date.

Rejected for source simulation because an inferred first observed transaction is not necessarily equivalent to source-system creation or availability.

Such derivations belong downstream if analytically useful.

---

### Alternative 5 — Build a REST API Before Simulating File Deliveries

Deferred.

REST/API ingestion is valuable, but the immediate goal is to model:

- daily incremental delivery;
- historical replay;
- Raw partitioning;
- idempotent loading;
- late-arriving data.

A future source abstraction and API adapter can introduce HTTP transport without changing the temporal rules established here.

ADR-009 defines the architectural boundary that allows this later extension.

---

## Consequences

### Positive

Mercury can demonstrate:

- initial and recurring source deliveries;
- genuine daily incremental batches;
- historical replay;
- different source refresh patterns;
- late-arriving related data;
- zero-record successful deliveries;
- partition-oriented warehouse loading;
- idempotent replay;
- source-to-Raw lineage.

The existing connector and storage abstractions remain unchanged.

The simulation stays grounded in source evidence instead of fabricated history.

### Trade-Offs

The Version 1 source environment is intentionally simplified.

Customers, Products, and Sellers appear to exist from the beginning of the simulated timeline even though real systems would evolve them over time.

Order Items and Payments are assumed to arrive with their parent Order even though production systems may expose them at different times.

The simulation is therefore a defensible replay model, not a perfect reconstruction of a production source system.

---

## Future Evolution

Future source systems may provide:

- reliable creation timestamps;
- update timestamps;
- CDC logs;
- API cursors;
- extraction timestamps;
- deletion events;
- master-data change history.

If reliable temporal information becomes available, currently static sources may move to incremental or change-based delivery.

That does not invalidate this decision.

The principle remains:

> Mercury should model source delivery from defensible source information rather than fabricate history for architectural convenience.

---

## Decision Summary

Mercury Version 1 uses a mixed source-delivery model.

```text
Initial / Master-Reference
--------------------------
customers
products
sellers
geolocations

Daily Incremental
-----------------
orders          → order_purchase_timestamp
order_items     → parent Order
payments        → parent Order
reviews         → review_creation_date
```

Simulation happens upstream of connectors.

The simulator changes delivery membership, not source values.

Historical Olist dates are preserved.

Valid zero-record daily deliveries remain explicit.

This decision provides realistic incremental behavior while keeping the Raw ingestion path faithful to the information actually available in the source.