# ADR-008: Define the BigQuery Raw Loading Strategy

## Status

Accepted

## Date

2026-08-17

---

## Context

Mercury preserves source deliveries in an immutable Raw Landing layer before making them available for analytical processing.

The ingestion architecture currently follows this flow:

```text
Source System
    ↓
Source Delivery
    ↓
Source Connector
    ↓
StorageManager
    ↓
Google Cloud Storage Raw Landing
```

Google Cloud Storage is the durable source-artifact layer.

Each successfully landed source delivery is stored under a deterministic hierarchy such as:

```text
raw/<source_system>/<source_object>/ingestion_date=YYYY-MM-DD/<source_file>
```

For example:

```text
raw/order_platform/orders/
    ingestion_date=2017-05-10/
        olist_orders_dataset.csv
```

The Raw Landing layer preserves the delivered source artifact without applying business transformations.

Mercury now requires a warehouse-loading capability that makes these landed artifacts queryable in BigQuery while preserving the architectural separation between:

1. source ingestion;
2. source preservation;
3. warehouse loading;
4. transformation and business modelling.

The BigQuery Raw layer must therefore remain close to the source representation and must not become an implicit transformation layer.

---

## Decision Drivers

The BigQuery Raw loading design should:

- preserve the source schema as closely as practical;
- avoid applying business transformations during warehouse loading;
- support deterministic and reproducible loads;
- support historical replay;
- support daily incremental source deliveries;
- prevent duplicate rows when a delivery is replayed;
- support BigQuery partition pruning for transactional Raw data;
- keep source data separate from Mercury platform metadata;
- avoid unnecessary intermediate tables;
- use explicit, version-controlled schemas;
- fail clearly when warehouse loading cannot be completed;
- provide a clean boundary for the future Dataform staging layer;
- remain simple enough for the first production-inspired version of Mercury.

---

## Decision

Mercury will load immutable source artifacts from Google Cloud Storage directly into final BigQuery Raw tables.

The BigQuery Raw layer will use:

1. **direct GCS-to-BigQuery load jobs**;
2. **explicit version-controlled Raw schemas**;
3. **source fields represented as `STRING` in Version 1**;
4. **ingestion-time partitioning for incremental transactional Raw tables**;
5. **explicit historical partition targeting during replay**;
6. **unpartitioned tables for Version 1 master/reference sources**;
7. **`WRITE_TRUNCATE` within the delivery-owned destination scope**;
8. **separate platform metadata rather than adding lineage columns to source rows**.

The BigQuery Raw loader will not perform business transformations.

---

## BigQuery Raw Layer Responsibility

The BigQuery Raw layer exists to make successfully landed source artifacts queryable.

Its responsibility is:

```text
Immutable GCS Source Artifact
            ↓
      BigQuery Raw Loader
            ↓
    Queryable Raw Table
```

It is not responsible for:

- business-rule application;
- semantic modelling;
- deduplication based on business logic;
- source enrichment;
- canonical entity construction;
- business metric calculation;
- timestamp normalization;
- numeric conversion;
- null standardization;
- cross-source joins.

Those responsibilities belong to downstream transformation layers.

---

## Direct GCS-to-BigQuery Loading

Mercury will load source artifacts directly from Google Cloud Storage into their final BigQuery Raw tables.

For example:

```text
gs://<raw-bucket>/
    raw/order_platform/orders/
        ingestion_date=2017-05-10/
            olist_orders_dataset.csv

                    ↓

BigQuery

raw.orders
```

Mercury Version 1 will not introduce an intermediate BigQuery staging table solely for Raw loading.

The source artifact has already been durably preserved in GCS.

Introducing another temporary warehouse layer would add:

- additional tables;
- additional SQL;
- additional orchestration;
- additional cleanup behavior;
- additional failure states;

without providing sufficient value for the current Raw-loading requirements.

Temporary warehouse tables may be introduced later if a concrete requirement justifies them.

---

## Source Schema Preservation

BigQuery Raw tables will preserve source columns without adding business transformations.

For example, the source Orders CSV contains fields such as:

```text
order_id
customer_id
order_status
order_purchase_timestamp
order_approved_at
order_delivered_carrier_date
order_delivered_customer_date
order_estimated_delivery_date
```

The corresponding BigQuery Raw table will contain the same source fields.

Mercury will not rename those fields during Raw loading.

---

## Explicit Raw Schemas

Mercury will define BigQuery Raw schemas explicitly in version-controlled code.

BigQuery schema autodetection will not be used for production Raw loading.

The loader must therefore know the expected schema for each supported source object.

Conceptually:

```text
customers
    → customers Raw schema

orders
    → orders Raw schema

order_items
    → order_items Raw schema

products
    → products Raw schema

sellers
    → sellers Raw schema

payments
    → payments Raw schema

reviews
    → reviews Raw schema

geolocations
    → geolocations Raw schema
```

Explicit schemas provide:

- deterministic table definitions;
- reproducible deployments;
- reviewable schema changes;
- protection from sample-dependent type inference;
- a stable contract between Raw and staging.

Schema definitions will live in the Mercury codebase rather than being configured manually only in the BigQuery console.

---

## Raw Data Types

In Mercury Version 1, source fields in BigQuery Raw tables will be represented as:

```text
STRING
```

unless a future requirement provides a compelling reason to introduce another Raw representation.

For example:

```text
order_purchase_timestamp
```

will enter Raw as:

```text
"2017-05-10 14:32:41"
```

rather than being converted to a BigQuery `TIMESTAMP` during warehouse loading.

Likewise, a source value such as:

```text
"120.50"
```

will remain its source textual representation in Raw rather than being interpreted as `NUMERIC`.

The staging layer will later own conversions such as:

```text
STRING
    ↓
TIMESTAMP
```

and:

```text
STRING
    ↓
NUMERIC
```

This preserves the architectural boundary:

```text
Raw
    → source-shaped data

Staging
    → typed and structurally cleaned data

Core
    → canonical business entities
```

---

## Source Data and Platform Metadata

Mercury will not add platform lineage fields to every BigQuery Raw source row.

For example, Raw source tables will not add fields such as:

```text
ingestion_id
ingestion_date
source_file_name
landing_path
checksum
```

to the source schema solely for lineage purposes.

These values describe Mercury's ingestion process rather than the source business record.

Detailed ingestion lineage will therefore be maintained separately from the source rows.

Conceptually:

```text
raw.orders

order_id
customer_id
order_status
order_purchase_timestamp
...
```

while platform metadata is represented separately:

```text
metadata.ingestion_runs

ingestion_id
source_system
source_object
ingestion_date
source_file_name
landing_path
file_size_bytes
checksum
record_count
status
started_at
completed_at
schema_version
error_message
```

The exact metadata persistence implementation will be defined separately.

This separation keeps the distinction clear between:

```text
SOURCE DATA
```

and:

```text
PLATFORM OPERATIONAL METADATA
```

---

## Source Loading Patterns

ADR-007 defines two source-delivery patterns:

1. initial / one-off master-reference deliveries;
2. daily incremental transactional deliveries.

The BigQuery Raw loading strategy will preserve this distinction.

---

## Master and Reference Sources

The following Version 1 sources are treated as initial master/reference datasets:

| Source Object | BigQuery Raw Table | Partitioning |
|---|---|---|
| Customers | `raw.customers` | Unpartitioned |
| Products | `raw.products` | Unpartitioned |
| Sellers | `raw.sellers` | Unpartitioned |
| Geolocations | `raw.geolocations` | Unpartitioned |

These tables will not be partitioned in Version 1.

The available Olist data does not provide a defensible temporal history for these sources, and Mercury currently models them as initial source populations.

Creating artificial partitions for a single initial delivery would add complexity without providing a meaningful query or lifecycle benefit.

This decision may be revisited if these sources later become incremental.

---

## Transactional Sources

The following Version 1 sources are delivered incrementally:

| Source Object | BigQuery Raw Table | Partitioning |
|---|---|---|
| Orders | `raw.orders` | Ingestion-time partitioned |
| Order Items | `raw.order_items` | Ingestion-time partitioned |
| Payments | `raw.payments` | Ingestion-time partitioned |
| Reviews | `raw.reviews` | Ingestion-time partitioned |

These tables will use BigQuery ingestion-time partitioning.

Mercury will not add a physical `ingestion_date` source column solely to support partitioning.

Instead, BigQuery's partition metadata will represent the technical ingestion partition.

---

## Historical Partition Targeting

Historical replay must preserve the simulated source-delivery date.

For example:

```text
simulation_date = 2017-05-10
```

produces a GCS artifact such as:

```text
raw/order_platform/orders/
    ingestion_date=2017-05-10/
        olist_orders_dataset.csv
```

The warehouse loader will explicitly load that artifact into the BigQuery partition corresponding to:

```text
2017-05-10
```

rather than allowing the current warehouse execution date to determine the partition.

Conceptually:

```text
GCS

orders/
    ingestion_date=2017-05-10/
        olist_orders_dataset.csv

                ↓

BigQuery

raw.orders$20170510
```

The next delivery:

```text
ingestion_date=2017-05-11
```

will target:

```text
raw.orders$20170511
```

This enables Mercury to replay historical source deliveries while maintaining the same partition structure that daily production ingestion would create.

---

## Business Date vs Ingestion Partition

The ingestion partition is a technical platform concept and must not be confused with business timestamps contained in source data.

For example, an Order may contain:

```text
order_purchase_timestamp = 2017-05-10 14:32:41
```

while its BigQuery ingestion partition represents:

```text
_PARTITIONDATE = 2017-05-10
```

These values happen to align in the current historical simulation because Orders are replayed according to purchase date.

Mercury does not assume they must always align.

In a future production scenario, a source delivery may arrive late.

For example:

```text
Business event:
    2017-05-10

Source delivery:
    2017-05-11
```

The architecture must preserve the distinction between those concepts.

Business timestamps remain source fields.

The BigQuery partition represents the technical ingestion/replay boundary.

---

## Idempotency and Replay

Mercury must support safe replay of a previously landed source delivery.

A replay must not blindly append duplicate records.

Mercury therefore defines the following invariant:

> One source delivery owns one replaceable BigQuery Raw destination scope.

The destination scope depends on the source-delivery pattern.

---

## Master / Reference Replay Semantics

For an initial master/reference source, the delivery owns the complete Raw table.

For example:

```text
Initial Customers Delivery
        ↓
raw.customers
```

The loader will use:

```text
WRITE_TRUNCATE
```

at the table level.

Replaying the same initial source therefore replaces the Raw table rather than appending duplicate records.

Conceptually:

```text
99,441 customers
        ↓ first load
raw.customers = 99,441 rows

99,441 customers
        ↓ replay
raw.customers = 99,441 rows
```

not:

```text
198,882 rows
```

---

## Transactional Replay Semantics

For a transactional source, one daily delivery owns one BigQuery partition.

For example:

```text
Orders delivery for 2017-05-10
        ↓
raw.orders$20170510
```

The loader will use:

```text
WRITE_TRUNCATE
```

against that specific partition.

This means:

```text
2017-05-10 load
    → partition contains 116 rows

2017-05-10 replay
    → same partition is replaced
    → partition still contains 116 rows
```

while:

```text
2017-05-09
2017-05-11
```

remain untouched.

The loader must never truncate the entire transactional table when replaying a single daily delivery.

---

## Why `WRITE_APPEND` Is Not the Default

A naive incremental loading strategy could use:

```text
WRITE_APPEND
```

for every daily batch.

However, replaying a delivery would then duplicate its records.

For example:

```text
2017-05-10 first load
    → 116 rows

2017-05-10 replay
    → another 116 rows

result
    → 232 rows
```

Preventing this would require additional deduplication logic.

Because Mercury's simulated source deliveries are deterministic and each delivery has a clearly owned partition, replacing the partition provides simpler and stronger idempotency semantics.

`WRITE_APPEND` is therefore rejected as the default Version 1 transactional replay strategy.

---

## Loader Input Contract

The warehouse loader should receive the information required to identify both the source artifact and its destination explicitly.

Conceptually:

```python
loader.load(
    source_object="orders",
    gcs_uri="gs://.../orders/ingestion_date=2017-05-10/olist_orders_dataset.csv",
    ingestion_date=date(2017, 5, 10),
)
```

The loader should not depend on parsing arbitrary GCS path strings to discover the ingestion date.

The ingestion date is already known by Mercury's ingestion process and should remain an explicit platform value.

The GCS path may later be validated against that metadata as an additional consistency check.

Based on `source_object`, the loader determines:

- target BigQuery table;
- explicit Raw schema;
- whether the source is partitioned;
- target partition when applicable;
- appropriate write disposition.

---

## Loader Responsibility

The BigQuery Raw loader will own:

- validating loader-level input;
- mapping supported source objects to Raw tables;
- retrieving the explicit Raw schema;
- configuring CSV load behavior;
- skipping the source CSV header;
- selecting partitioned vs unpartitioned loading behavior;
- targeting the correct historical partition;
- selecting the appropriate write disposition;
- submitting the BigQuery load job;
- waiting for job completion;
- surfacing warehouse-loading failures clearly.

The loader will not own:

- source extraction;
- source simulation;
- GCS upload;
- source business validation;
- business transformations;
- deduplication;
- Dataform execution;
- downstream dimensional modelling.

---

## Failure Boundaries

GCS landing and BigQuery loading are separate platform operations.

A successful GCS landing does not imply a successful BigQuery load.

For example:

```text
Source Delivery
      ↓
GCS Landing
      ↓
SUCCESS
      ↓
BigQuery Load
      ↓
FAILURE
```

must leave the GCS Raw artifact intact.

The loader must not delete, modify, or replace the source GCS artifact when a warehouse load fails.

This enables the same immutable source artifact to be retried later.

Warehouse-loading failures should propagate clearly to the caller.

Automatic retry policy and operational alerting are outside the scope of this decision and may be introduced during productionization.

---

## Empty Daily Deliveries

ADR-007 permits valid daily source deliveries containing zero records.

These are represented as header-only CSV files.

A zero-record delivery means:

> The source successfully delivered data for this date, but there were no business records.

It does not mean:

> The source failed to deliver.

The BigQuery loader must preserve this distinction.

The exact BigQuery behavior for replacing an existing partition with a valid zero-record delivery must be verified during implementation and integration testing.

Mercury must not silently treat a valid empty delivery as a missing source artifact.

---

## Schema Evolution

Automatic schema evolution is outside the scope of Mercury Version 1.

If a source schema changes, Mercury should fail clearly rather than silently altering the BigQuery Raw schema.

A schema change should be handled deliberately through:

1. source-contract review;
2. explicit schema update in version-controlled code;
3. corresponding connector validation changes where required;
4. downstream staging review;
5. automated tests.

This keeps schema evolution visible and reviewable.

---

## Alternatives Considered

### Alternative 1 — BigQuery Schema Autodetection

BigQuery could infer column types from each CSV during loading.

Rejected because:

- inferred schemas may depend on sampled source values;
- schema behavior becomes less deterministic;
- type inference introduces interpretation into Raw;
- schema changes become less visible in code review;
- repeated loads should not depend on inference.

Explicit schemas provide a stronger Raw contract.

---

### Alternative 2 — Add `ingestion_date` to Every Raw Row

Mercury could append:

```text
ingestion_date
```

to every source record and partition on that field.

Rejected for Version 1 because the field does not originate from the source.

Adding it directly to the source-shaped Raw schema would blur the boundary between:

```text
source data
```

and:

```text
platform metadata
```

Mercury instead uses BigQuery partition metadata for technical partitioning and maintains detailed ingestion lineage separately.

---

### Alternative 3 — Temporary BigQuery Landing Tables

Mercury could first load every GCS artifact into a temporary BigQuery table and then insert into the final Raw table.

Rejected for Version 1 because the current Raw-loading requirements do not require transformation between GCS and BigQuery Raw.

The additional layer would introduce complexity without sufficient benefit.

This option may be reconsidered if future requirements require:

- row-level technical metadata injection;
- complex validation;
- schema reconciliation;
- multi-file consolidation;
- provider-specific normalization.

---

### Alternative 4 — `WRITE_APPEND` for Incremental Loads

Mercury could append every daily delivery to the transactional Raw table.

Rejected as the default because replaying the same delivery would duplicate records.

Partition-scoped `WRITE_TRUNCATE` provides deterministic replay behavior for the current daily-delivery model.

---

### Alternative 5 — Partition All Raw Tables

Mercury could partition customers, products, sellers, and geolocations for architectural uniformity.

Rejected because Version 1 models these sources as one-off master/reference deliveries.

Creating a single artificial partition would add complexity without meaningful query or lifecycle benefits.

Partitioning may be introduced if those sources later become incremental.

---

### Alternative 6 — Partition by Business Timestamp

For example, `raw.orders` could be partitioned by:

```text
order_purchase_timestamp
```

Rejected for the Raw layer because business-event time and platform-ingestion time are separate concepts.

Business timestamps belong to the source record.

Raw partitioning is intended to represent Mercury's source-delivery boundary.

Business-oriented partitioning may be appropriate in downstream staging, core, or analytical tables.

---

## Consequences

### Positive

This decision provides:

- deterministic Raw schemas;
- strict source-shape preservation;
- explicit separation between source data and platform metadata;
- direct and simple GCS-to-BigQuery loading;
- safe historical replay;
- partition-level idempotency for transactional sources;
- table-level idempotency for initial sources;
- efficient partition pruning for incremental Raw data;
- a clean boundary for Dataform staging;
- version-controlled schema contracts;
- reproducible warehouse behavior.

It also creates a clear portfolio example of:

- immutable Raw storage;
- explicit warehouse schemas;
- partitioned BigQuery tables;
- historical replay;
- idempotent batch loading;
- separation of ingestion and transformation concerns.

### Negative

This decision also introduces trade-offs:

- Raw fields are less convenient to query because typed values remain strings;
- analysts should generally use staging/core tables instead of Raw directly;
- ingestion metadata is not immediately visible as ordinary Raw table columns;
- lineage queries may require consulting separate metadata;
- partition decorators and replay semantics add loader complexity;
- schema changes require deliberate code changes;
- master/reference tables do not retain historical snapshots in Version 1;
- ingestion-time partitions expose BigQuery-managed partition fields rather than a normal source column.

These trade-offs are accepted because they preserve stronger architectural boundaries and deterministic Raw behavior.

---

## Future Considerations

The following capabilities may be introduced later if justified:

- persisted BigQuery ingestion-run metadata;
- row-level technical lineage;
- schema-version history;
- automated schema-drift detection;
- incremental master/reference sources;
- snapshot history for master data;
- late-arriving source-delivery policies;
- automated retry orchestration;
- dead-letter handling;
- warehouse-load observability;
- Dataform staging assertions;
- infrastructure provisioning through Terraform;
- scheduled execution through Cloud Run or another GCP orchestration service.

These are deliberately excluded from the Version 1 BigQuery Raw loader unless required by a concrete implementation need.

---

## Resulting Architecture

```text
                     SOURCE SYSTEMS
                           │
                           ▼
                   Source Deliveries
                           │
                           ▼
                     Connectors
                           │
                           ▼
                     StorageManager
                           │
                           ▼
                Immutable GCS Raw Landing
                           │
                           ▼
                  BigQuery Raw Loader
                           │
              ┌────────────┴────────────┐
              │                         │
              ▼                         ▼
      Master / Reference            Transactional
         Raw Tables                  Raw Tables
              │                         │
        Unpartitioned              Ingestion-Time
        WRITE_TRUNCATE              Partitioned
        Whole Table              WRITE_TRUNCATE
                                 Target Partition
              │                         │
              └────────────┬────────────┘
                           │
                           ▼
                    BigQuery Raw
                 Source-Shaped STRING
                        Schemas
                           │
                           ▼
                       Dataform
                           │
                           ▼
                        Staging
                   Typed / Validated
                           │
                           ▼
                         Core
```

Operational lineage remains parallel to the source data:

```text
Ingestion / Warehouse Execution
             │
             ▼
      Platform Metadata
             │
             ▼
   metadata.ingestion_runs
```

---

## Decision Outcome

Mercury will use a direct, deterministic, and replay-safe BigQuery Raw loading strategy.

Immutable GCS artifacts remain the preserved source-of-truth files.

BigQuery Raw provides their queryable warehouse representation.

Transactional source deliveries are loaded into explicitly targeted ingestion-time partitions, while Version 1 master/reference sources remain unpartitioned.

Raw source fields remain source-shaped and are loaded using explicit `STRING` schemas.

Replay replaces only the destination scope owned by that source delivery.

Business typing and transformation begin downstream in Dataform staging rather than during Raw warehouse loading.