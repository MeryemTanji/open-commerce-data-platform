# Olist Production Runtime Contract

## Status

Implemented locally; deployed validation pending.

## Purpose

This document defines Olist-specific production behavior within Mercury’s reusable orchestration, ingestion, Raw, and transformation boundaries.

It governs how a finite historical dataset is used to simulate a daily incremental source.

It does not redefine Mercury’s platform-wide production architecture.

## 1. Source Character

Olist is a historical static dataset.

Mercury uses the complete source files as immutable simulation input and derives controlled daily deliveries from them.

The complete source files are not loaded into the daily Raw pipeline as one bulk transactional delivery.

Instead, each production execution generates one governed historical daily batch.

## 2. Date Semantics

Mercury distinguishes:

| Date | Meaning |
| --- | --- |
| Logical `delivery_date` | Historical business date represented by the simulated source batch |
| Simulated `ingestion_date` | Historical date on which Mercury treats that batch as having become available |
| Actual execution timestamp | Real time at which Cloud Workflows and Cloud Run execute |

The governed timing rule is:

```text
ingestion_date = delivery_date + 1 calendar day
```

The actual production execution date does not replace either historical date.

The logical `delivery_date` is a Mercury batch concept. It must not be confused with Olist fields such as `order_delivered_customer_date`.

## 3. Immutable Simulation Input

The approved complete Olist CSV files are stored in durable GCS input storage.

The production ingestion identity receives read-only access to this input.

At runtime:

1. the files are materialized into temporary Cloud Run storage;
2. the existing Olist simulator reads them;
3. only the selected historical daily batch is generated;
4. generated temporary files are passed to the existing ingestion framework;
5. temporary files disappear when the Job terminates.

The production image contains no mutable source deliveries.

## 4. Daily Transactional Membership

Every selected daily delivery contains exactly these governed source objects:

```text
orders
order_items
payments
reviews
```

Daily membership is derived as follows:

| Source object | Daily selection rule |
| --- | --- |
| `orders` | Order purchase date equals the logical delivery date |
| `order_items` | Record belongs to an order selected for the logical delivery date |
| `payments` | Record belongs to an order selected for the logical delivery date |
| `reviews` | Review creation date equals the logical delivery date |

Relationship-dependent sources are therefore selected through their governed parent-order membership rather than an invented independent transaction date.

The simulator preserves source rows and duplicates according to the existing ingestion contracts.

## 5. Initial Reference Delivery

The following source objects belong to the initial reference delivery:

```text
customers
products
sellers
geolocations
```

They are not part of the four-object daily transactional contract.

Initial/reference ingestion remains a separate bootstrap concern and must not be silently repeated as part of every scheduled daily execution.

A deployed bootstrap or recovery procedure must be governed separately.

## 6. Scheduled Simulation Clock

Scheduled execution advances through a configured inclusive historical range:

```text
simulation_start_date
    through
simulation_end_date
```

The workflow queries durable replay-state evidence and selects:

```text
the earliest historical date that has not completed
all four governed daily source objects
```

Exactly one historical date may be processed per scheduled workflow execution.

The workflow must not derive the simulated historical date from the current real-world calendar.

When the entire configured range is complete, the workflow returns:

```text
final_status = no_work_remaining
```

No ingestion or Dataform execution occurs in that branch.

## 7. Manual Execution

Manual execution requires an explicit historical `delivery_date`.

It supports:

- controlled reruns;
- idempotency validation;
- operational diagnosis;
- replay of a known date;
- approved recovery.

Manual execution does not mutate a separate cursor.

Durable replay state remains the source of truth for logical completion.

## 8. Completion Contract

A logical daily delivery is complete only when all four expected source objects have durable:

```text
status = success
stage = warehouse
```

Completion is monotonic.

A later failed attempt does not revoke an earlier successful Raw landing and BigQuery Raw load.

Unexpected completed source objects cause readiness evaluation to block transformation.

## 9. Downstream Release

Dataform execution is permitted only after:

1. `run-day` completes successfully;
2. `check-readiness` independently confirms the exact daily completion set.

Dataform then publishes the approved staging and canonical graph.

This produces incremental downstream behavior even though the original Olist dataset is historical and static.

## 10. Failure and Retry Behavior

If ingestion fails:

- Dataform does not run;
- durable successful source evidence is preserved;
- the logical date remains incomplete when any required source is missing;
- a later scheduled execution may select the same date again.

Immutable Raw destinations must not be overwritten during retry.

Replay-state and provenance evidence must remain append-only.

## 11. Portability Boundary

The following behaviors are source-specific:

- historical simulation;
- daily membership rules;
- `delivery_date + 1` ingestion timing;
- historical range exhaustion;
- initial reference-source membership.

The following behaviors remain reusable Mercury platform controls:

- immutable source input;
- ephemeral runtime workspace;
- connector validation;
- Raw landing;
- warehouse loading;
- replay state;
- provenance;
- exact readiness gating;
- structured execution summaries;
- orchestration failure propagation;
- downstream transformation gating.