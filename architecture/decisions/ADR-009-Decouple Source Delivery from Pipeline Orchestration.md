# ADR-009: Historical Replay Orchestration

## Status

Accepted

## Date 

2026-08-17

---

## Context

Mercury requires a repeatable way to simulate and execute historical ingestion over the Olist dataset without manually running individual scripts for every business date.

The project already provides the core ingestion components:

- source simulation;
- source-specific connectors;
- immutable Raw landing through `StorageManager` / `GCSStorageManager`;
- connector-level ingestion metadata;
- `IngestionRunner`;
- `BigQueryRawLoader`;
- explicit BigQuery Raw schemas.

These components intentionally have separate responsibilities.

The simulator is responsible for reproducing how source data becomes available.

Connectors are responsible for validating and landing individual source artifacts into Raw storage.

The warehouse loader is responsible for loading landed Raw artifacts into BigQuery.

What was missing was an orchestration layer capable of coordinating those components across historical dates.

Without such an orchestration layer, replaying several years of incremental data would require manually:

1. generating a simulated source delivery for a date;
2. identifying the generated files;
3. constructing the appropriate connectors;
4. running ingestion;
5. locating the resulting GCS landing paths;
6. loading those artifacts into BigQuery;
7. repeating the process for the next date.

That approach is unsuitable for a reusable data platform and would make historical replay operationally fragile.

Mercury therefore requires a historical replay abstraction that automates this workflow while preserving the boundaries already established by the ingestion architecture.

---

## Decision

Mercury will provide a dedicated historical replay orchestration layer built around:

- `SourceDelivery`;
- `SourceDeliveryBatch`;
- `SourceDeliveryProvider`;
- `OlistSimulatedSourceProvider`;
- `HistoricalReplayRunner`.

The orchestration layer coordinates existing components rather than duplicating their responsibilities.

The architecture is:

```text
Source system / simulator
          |
          v
SourceDeliveryProvider
          |
          v
SourceDeliveryBatch
          |
          v
HistoricalReplayRunner
          |
          +----------------------+
          |                      |
          v                      v
     Connectors             BigQueryRawLoader
          |
          v
     Raw Storage
       (GCS)
```

For the current Olist implementation:

```text
Olist source dataset
        |
        v
OlistSourceSimulator
        |
        v
OlistSimulatedSourceProvider
        |
        v
HistoricalReplayRunner
```

The orchestration layer does not contain Olist simulation logic, connector validation logic, storage implementation logic, or BigQuery schema logic.

It coordinates those existing components through their public contracts.

---

# Source Delivery Contract

## SourceDelivery

`SourceDelivery` represents one source artifact that has become available for ingestion.

It contains only information required to describe that source delivery, including:

- `source_object`;
- source file path;
- optional `delivery_date`;
- `record_count`.

It deliberately does not contain:

- GCS configuration;
- BigQuery configuration;
- connector implementation details;
- ingestion IDs;
- warehouse destination logic.

A delivery with:

```text
record_count = 0
```

is valid.

A zero-record delivery represents a real source artifact containing no business rows, such as a header-only CSV.

This is fundamentally different from an absent delivery.

---

## SourceDeliveryBatch

`SourceDeliveryBatch` represents the set of source artifacts delivered together for one source-delivery boundary.

For an incremental daily delivery, all contained deliveries must have the same `delivery_date` as the batch.

For an initial delivery, the batch and its deliveries are undated.

An empty batch is invalid.

This distinction is intentional:

```text
one or more SourceDelivery objects with record_count = 0
    -> valid delivery containing zero business rows

zero SourceDelivery objects
    -> invalid provider response
```

Without this distinction, an accidentally empty provider result could otherwise be mistaken for a successful zero-row business day.

---

# SourceDeliveryProvider

Mercury introduces `SourceDeliveryProvider` as the abstraction between source acquisition and ingestion orchestration.

The provider exposes the conceptual operations required by historical replay:

```text
get_initial_delivery()
get_daily_delivery(delivery_date)
```

The provider is responsible only for making source deliveries available.

It has no knowledge of:

- GCS;
- BigQuery;
- warehouse schemas;
- connector execution;
- replay range orchestration.

This boundary is intentional.

The current implementation uses:

```text
OlistSimulatedSourceProvider
```

but future implementations may include providers backed by:

- REST APIs;
- SaaS APIs;
- SFTP;
- object storage;
- database exports;
- other external delivery mechanisms.

A future provider can implement the same `SourceDeliveryProvider` contract without requiring the historical replay orchestration, connectors, Raw storage layer, or warehouse loader to be redesigned.

---

# Olist Simulation Adapter

`OlistSimulatedSourceProvider` adapts the existing `OlistSourceSimulator` into the generic source-delivery contract.

It does not duplicate Olist simulation behavior.

The provider delegates generation to the simulator and converts the resulting simulated files into:

```text
SourceDelivery
SourceDeliveryBatch
```

objects.

The simulator remains responsible for:

- temporal filtering;
- Olist-specific source rules;
- filename mapping;
- generation of initial deliveries;
- generation of daily deliveries.

The provider remains responsible for adapting those outputs to the orchestration contract.

---

# Existing Simulated Deliveries

Historical replay may encounter source deliveries that were generated during an earlier execution.

The provider therefore supports already-generated delivery directories.

If the expected delivery directory already exists and contains the complete expected source set, the provider adapts those existing files rather than attempting to regenerate them.

This preserves the simulator's create-only behavior.

Record counts for existing CSV files are recomputed using CSV-aware parsing so that valid CSV features such as quoted multiline values do not produce incorrect counts.

---

# Partial Simulated Deliveries

An existing delivery directory must never silently be treated as complete when expected files are missing.

If a directory exists but contains only part of the required source delivery, the provider raises an error identifying the missing source objects.

It does not:

- delete the partial directory;
- overwrite existing files;
- regenerate the directory automatically;
- silently return an incomplete batch.

This preserves source-delivery immutability and makes partial source generation visible to the operator.

---

# Expected Source Membership

Historical replay validates that the provider returned exactly the expected source objects before ingestion begins.

The current Olist source groups are intentionally explicit.

## Initial / Reference Sources

```text
customers
products
sellers
geolocations
```

## Incremental / Daily Sources

```text
orders
order_items
payments
reviews
```

The orchestration layer owns these expectations independently of the simulator.

This prevents orchestration correctness from depending on Olist simulation internals.

A future provider therefore does not need to depend on the simulator implementation.

---

# Batch Membership Validation

Before connector execution, `HistoricalReplayRunner` validates the source-delivery batch.

The actual `source_object` set must exactly equal the expected source set for the requested operation.

The runner rejects:

- missing expected sources;
- unexpected sources;
- incorrect source classification;
- unsupported source objects.

These failures occur before ingestion begins.

This prevents a malformed provider response from creating a partially valid Raw ingestion without the orchestration layer first recognizing that the delivery itself was incorrect.

---

# Connector Mapping

Historical replay uses an explicit mapping between source objects and existing connector classes.

Conceptually:

```text
customers      -> CustomerConnector
products       -> ProductConnector
sellers        -> SellerConnector
geolocations   -> GeolocationConnector

orders         -> OrderConnector
order_items    -> OrderItemConnector
payments       -> PaymentConnector
reviews        -> ReviewConnector
```

The implementation uses the actual connector class names defined by the repository.

The replay layer does not reimplement connector logic.

Each connector remains responsible for its existing validation, metadata generation, and Raw landing behavior.

An unsupported source object fails explicitly rather than surfacing an accidental dictionary `KeyError`.

---

# HistoricalReplayRunner

`HistoricalReplayRunner` is the orchestration component responsible for coordinating:

```text
source delivery
    ->
connector execution
    ->
Raw landing
    ->
warehouse loading
```

It does not itself implement:

- source simulation;
- source-specific validation;
- file persistence;
- GCS behavior;
- BigQuery schema definitions.

Its responsibility is sequencing and coordination.

---

# Initial Load

The initial/reference load is executed through:

```text
run_initial_load(ingestion_date)
```

The provider supplies the expected initial source objects:

```text
customers
products
sellers
geolocations
```

An explicit `ingestion_date` is still required even though these BigQuery Raw tables are not ingestion-date partitioned.

The date is required by the ingestion infrastructure and metadata conventions and must not be silently manufactured inside the runner.

Initial BigQuery destinations remain unpartitioned.

Conceptually:

```text
raw.customers
raw.products
raw.sellers
raw.geolocations
```

rather than:

```text
raw.customers$YYYYMMDD
```

---

# Daily Incremental Replay

A single historical business date is executed through:

```text
run_day(delivery_date)
```

The provider supplies:

```text
orders
order_items
payments
reviews
```

for that delivery date.

The same business date is propagated through the ingestion and warehouse layers.

The resulting Raw landing paths use the ingestion-date convention:

```text
.../ingestion_date=YYYY-MM-DD/...
```

and the corresponding BigQuery Raw transactional tables use ingestion-time/date partition destinations equivalent to:

```text
raw.orders$YYYYMMDD
raw.order_items$YYYYMMDD
raw.payments$YYYYMMDD
raw.reviews$YYYYMMDD
```

The orchestration layer does not reconstruct the GCS landing path.

It uses the landing path produced by connector ingestion metadata and passes that path directly to the warehouse loader.

This preserves the connector/storage layer as the authority over Raw object location.

---

# Range Replay

Historical ranges are executed through:

```text
run_range(start_date, end_date)
```

The range is inclusive.

For example:

```text
start_date = 2017-05-12
end_date   = 2017-05-15
```

processes:

```text
2017-05-12
2017-05-13
2017-05-14
2017-05-15
```

The runner validates:

```text
start_date <= end_date
```

before execution.

Date iteration is performed sequentially.

Historical replay is intentionally deterministic and does not introduce parallel date execution.

---

# Raw-Layer Immutability

Historical replay does not implement an overwrite mode.

There is no:

```text
force=True
overwrite=True
replace=True
```

behavior.

Raw landing immutability remains the responsibility of the storage layer.

If an existing immutable destination prevents a connector from landing the same source again, the existing connector/storage failure path is allowed to surface through orchestration.

HistoricalReplayRunner does not bypass or weaken this behavior.

This prevents historical replay from accidentally overwriting previously landed Raw artifacts.

---

# BigQuery Loading

The replay runner uses the existing `BigQueryRawLoader`.

It does not:

- duplicate warehouse schemas;
- infer schemas;
- reconstruct GCS paths;
- implement BigQuery client behavior;
- modify BigQuery overwrite semantics.

For each warehouse-eligible source, the loader receives the actual:

```text
source_object
landing_path
ingestion_date
```

produced by the upstream ingestion path.

This preserves clean ownership between orchestration and warehouse loading.

---

# Failure Semantics Established by ADR-009

The initial implementation of ADR-009 established conservative fail-fast orchestration.

Its primary purpose was to prove that Mercury could reliably execute:

```text
simulate
    ->
source delivery
    ->
connector ingestion
    ->
immutable GCS Raw landing
    ->
BigQuery Raw loading
```

over historical ranges.

At that stage, automatic recovery was deliberately out of scope.

The implementation therefore prioritized:

- deterministic sequencing;
- explicit failures;
- no automatic retry;
- no overwrite;
- no silent continuation after an incomplete replay date.

This provided a safe baseline from which operational recovery behavior could later be designed using observed real failure boundaries rather than assumptions.

---

# Subsequent Evolution: Source-Level Partial Success

ADR-010 extends the execution semantics established by ADR-009.

The daily delivery remains the date-level orchestration and completeness boundary, but the individual source objects are independent ingestion units.

A failure in one independent source should not make valid data from unrelated successful sources unavailable.

Mercury therefore evolves the daily replay model to distinguish:

```text
SOURCE AVAILABILITY
```

from:

```text
DATE COMPLETENESS
```

These concepts are intentionally not equivalent.

---

# Revised Daily Execution Model

For a daily replay, Mercury follows two ordered execution phases.

```text
SourceDeliveryBatch
        |
        v
validate complete expected membership
        |
        v
+--------------------------+
|     INGESTION PHASE      |
|                          |
| attempt all expected     |
| independent sources      |
+------------+-------------+
             |
             v
      collect individual
      connector outcomes
             |
             v
+--------------------------+
|      WAREHOUSE PHASE     |
|                          |
| load every source whose  |
| ingestion succeeded      |
+------------+-------------+
             |
             v
   derive date completeness
```

Mercury completes the ingestion-attempt phase before beginning the warehouse phase.

However, warehouse loading is not globally blocked merely because one independent source failed ingestion.

Instead, each successfully ingested source remains eligible for warehouse loading.

---

# Attempt-All-Safe-Work Within a Date

Within one business date, Mercury should attempt all safe independent work.

Suppose ingestion produces:

```text
orders       -> succeeded
order_items  -> succeeded
payments     -> failed
reviews      -> succeeded
```

Mercury should not stop after the `payments` failure and leave `reviews` unattempted merely because of connector ordering.

Instead, the warehouse phase becomes:

```text
orders       -> BigQuery load attempted
order_items  -> BigQuery load attempted
payments     -> BigQuery load not attempted
reviews      -> BigQuery load attempted
```

If all eligible warehouse loads succeed, the resulting Raw availability is:

```text
orders       -> available
order_items  -> available
payments     -> unavailable
reviews      -> available
```

The business date remains:

```text
INCOMPLETE
```

because not every expected source completed its required path.

This behavior maximizes safe source availability while preserving truthful completeness information.

---

# Warehouse Partial Failure

The same principle applies during warehouse loading.

If all sources successfully land in GCS but one BigQuery load fails:

```text
orders       -> BigQuery succeeded
order_items  -> BigQuery succeeded
payments     -> BigQuery failed
reviews      -> BigQuery succeeded
```

Mercury should retain the successful loads.

It must not:

- delete successfully loaded BigQuery data;
- delete immutable GCS artifacts;
- roll back unrelated successful sources;
- pretend the date is complete.

The date remains incomplete until the failed source is successfully recovered.

---

# Source Availability vs Date Completeness

The design explicitly follows:

```text
source availability != date completeness
```

This is important in a production data platform because downstream products may depend on different source combinations.

For example:

```text
orders dashboard
    -> may depend only on orders

review analytics
    -> may depend only on reviews

revenue reconciliation
    -> may require orders + payments
```

A temporary failure in a payment platform should not automatically prevent an unrelated orders or reviews product from receiving otherwise valid data.

Mercury therefore makes successfully processed independent source data available while separately exposing whether the complete expected daily delivery has been achieved.

Mercury does not attempt to determine downstream dependency requirements at the historical replay layer.

---

# Range-Level Boundary

Although Mercury attempts all safe work within the current date, historical range execution remains conservative across dates.

The intended behavior is:

```text
process date
    |
    v
attempt all source ingestions
    |
    v
warehouse all eligible sources
    |
    v
derive completeness
    |
    +---- COMPLETE ----> continue to next date
    |
    +---- INCOMPLETE --> stop range
```

For example:

```text
2017-05-12  COMPLETE
2017-05-13  COMPLETE
2017-05-14  INCOMPLETE
2017-05-15  NOT ATTEMPTED
```

This prevents a known historical completeness gap from being silently propagated through the remainder of a replay while still maximizing safe data availability for the incomplete date.

Persistent source-level state and targeted recovery for such an incomplete date are defined by ADR-010.

---

# Recovery Is Not an ADR-009 Responsibility

ADR-009 establishes historical replay orchestration.

It does not itself define automatic recovery.

In particular, ADR-009 does not implement:

- automatic retry;
- resume from checkpoint;
- skipping previously successful sources;
- targeted BigQuery-only retry;
- state-aware reuse of existing GCS artifacts;
- automatic reconciliation;
- retry policies;
- backoff.

Those behaviors require reliable knowledge of what previously happened.

ADR-010 therefore introduces persistent source-level replay state before automatic recovery behavior is added.

This follows the design principle:

> Observe and persist execution state before automating recovery from that state.

---

# REST API Boundary

ADR-009 does not implement a REST API.

This is intentional.

The current Olist simulation is adapted behind:

```text
SourceDeliveryProvider
```

which provides the architectural seam for future source implementations.

A future:

```text
RestApiSourceProvider
```

can implement the same delivery contract:

```text
get_initial_delivery()
get_daily_delivery(...)
```

while leaving downstream orchestration largely independent of how the source artifact was acquired.

This allows Mercury to first prove reliable ingestion and replay semantics using deterministic local simulation without coupling the architecture to HTTP concerns such as:

- authentication;
- pagination;
- rate limiting;
- API retries;
- network failures;
- request throttling.

The architecture is therefore API-ready without requiring a REST API to be implemented as part of ADR-009.

---

# Alternatives Considered

## Manual Historical Replay

Manually run simulation, ingestion, and BigQuery loading for every date.

Rejected because:

- it does not scale to multi-year history;
- it is error-prone;
- it is difficult to reproduce;
- it does not demonstrate production-style orchestration;
- it would require repeated operator intervention.

---

## Put Historical Replay Logic in the Simulator

Allow `OlistSourceSimulator` to loop over all dates and invoke ingestion.

Rejected because simulation and orchestration are separate responsibilities.

The simulator should model source availability, not control GCS or BigQuery execution.

---

## Put Historical Replay Logic in IngestionRunner

Extend the generic ingestion runner to understand:

- historical date ranges;
- source providers;
- simulation;
- BigQuery loading.

Rejected because this would make a generic connector runner responsible for source acquisition and warehouse orchestration.

`IngestionRunner` should remain focused on connector execution.

---

## Couple Historical Replay Directly to OlistSourceSimulator

Have `HistoricalReplayRunner` call the simulator directly.

Rejected because this would couple orchestration to the simulated Olist implementation and make future source providers harder to introduce.

`SourceDeliveryProvider` provides the required abstraction.

---

## Build the REST API First

Implement an HTTP API around the simulator before building replay orchestration.

Rejected for this phase.

The initial objective is to prove the end-to-end ingestion architecture and its operational contracts.

Introducing HTTP behavior before those contracts are stable would add authentication, transport, pagination, retry, and networking concerns without improving the underlying ingestion design.

The provider abstraction allows the API boundary to be added later without redesigning the downstream pipeline.

---

## Require All Sources to Succeed Before Any Warehouse Loading

Treat the daily source set as an all-or-nothing warehouse gate.

This was useful as an initial conservative implementation while ADR-009 was being proven.

It is not the preferred long-term production behavior.

Rejected as the final operational model because independent downstream products should not lose access to valid source data merely because another unrelated source failed.

ADR-010 therefore evolves the execution model toward partial source availability with explicit date-level completeness.

---

## End-to-End Source-by-Source Interleaving

Execute:

```text
orders
    -> GCS
    -> BigQuery

order_items
    -> GCS
    -> BigQuery

payments
    -> GCS
    -> BigQuery

reviews
    -> GCS
    -> BigQuery
```

Rejected as the preferred orchestration model.

Mercury instead preserves clean stage separation:

```text
attempt all ingestion
        ->
collect connector outcomes
        ->
warehouse eligible sources
```

This makes operational boundaries easier to understand and debug while still allowing successful independent sources to become available.

---

# Consequences

## Positive

Historical replay becomes automated and repeatable.

The architecture remains modular:

```text
source acquisition
simulation
connector execution
storage
warehouse loading
orchestration
```

remain separate concerns.

The provider abstraction allows future source implementations without redesigning the replay runner.

Historical ranges can be replayed without manually invoking each date.

The same existing connector, storage, and warehouse components are reused.

Raw-layer immutability remains enforced.

BigQuery loading uses actual connector-produced landing paths rather than reconstructed paths.

Initial/reference and daily/incremental delivery semantics remain explicit.

The architecture supports future REST/API-backed source acquisition.

The evolved partial-success model maximizes safe source availability.

Source-level failures do not unnecessarily block unrelated independent data.

Date-level completeness remains explicit rather than being inferred from the mere presence of some data.

The architecture provides a clean foundation for source-level operational state and targeted recovery.

---

## Negative

Historical replay introduces another orchestration abstraction that must be maintained.

A date may intentionally become partially available in BigQuery.

Consumers that require complete daily inputs must therefore use completeness information rather than assuming that the presence of one partition implies that every expected source is available.

Recovery becomes a separate concern requiring persistent operational state.

The orchestration layer must carefully distinguish:

- source failure;
- source availability;
- warehouse eligibility;
- date completeness;
- range continuation.

---

## Risks

A malformed provider response could otherwise result in incorrect replay behavior.

Mitigation:

- strict batch membership validation;
- non-empty batch invariant;
- explicit source expectations.

Repeated replay could overwrite historical Raw data.

Mitigation:

- immutable storage behavior;
- no force/overwrite mode.

A source failure could be mistaken for complete daily ingestion.

Mitigation:

- source-level outcomes;
- explicit expected-source membership;
- derived date completeness under ADR-010.

Partial availability could be mistaken by downstream consumers for full daily completeness.

Mitigation:

- persistent replay-state metadata under ADR-010;
- explicit separation of availability and completeness;
- downstream dependency-aware consumption patterns in later platform layers.

Orchestration could become tightly coupled to the Olist simulator.

Mitigation:

- `SourceDeliveryProvider` abstraction;
- explicit orchestration-owned source expectations;
- no simulator dependency in generic source-delivery contracts.

---

# Validation

ADR-009 was validated through automated tests covering:

- source-delivery construction;
- zero-record deliveries;
- invalid empty batches;
- daily delivery-date consistency;
- simulated Olist provider adaptation;
- existing simulated deliveries;
- partial existing delivery rejection;
- connector mapping;
- source membership validation;
- unsupported source handling;
- ingestion ordering;
- warehouse ordering;
- landing-path handoff;
- initial-load orchestration;
- daily orchestration;
- range orchestration;
- failure-stop semantics;
- Raw destination immutability;
- initial unpartitioned destinations;
- daily BigQuery partition destinations.

The historical replay path was also exercised against the real Mercury development GCP environment.

A multi-day incremental replay successfully processed:

```text
2017-05-12
2017-05-13
2017-05-14
2017-05-15
```

for:

```text
orders
order_items
payments
reviews
```

through:

```text
simulation
    ->
source delivery
    ->
connector ingestion
    ->
GCS Raw
    ->
BigQuery Raw
```

and the expected BigQuery partitions were verified.

The initial/reference path was separately exercised successfully for:

```text
customers
products
sellers
geolocations
```

through the same ingestion architecture into their unpartitioned BigQuery Raw tables.

These integration exercises validated the architecture before persistent recovery semantics were introduced.

---

# Relationship to Other ADRs

ADR-009 establishes the historical replay orchestration architecture.

ADR-010 builds on ADR-009 by introducing:

- persistent source-level replay state;
- append-only execution history;
- replay execution identity;
- source-level status and stage tracking;
- derived date completeness;
- the operational foundation for targeted recovery.

ADR-010 may evolve execution semantics where necessary for production recovery and availability requirements, but it does not invalidate the architectural boundaries established by ADR-009.

In particular, the following ADR-009 decisions remain foundational:

```text
SourceDeliveryProvider abstraction
SourceDelivery / SourceDeliveryBatch contracts
explicit expected-source membership
existing connector reuse
immutable Raw landing
connector-produced landing-path handoff
BigQueryRawLoader reuse
separate initial and daily replay paths
sequential historical date orchestration
```

---

# Final Decision

Mercury will use `HistoricalReplayRunner` as the orchestration layer for historical source replay.

Historical replay will remain independent from source simulation, connector implementation, storage implementation, and warehouse implementation.

Source acquisition will be abstracted through `SourceDeliveryProvider`, allowing the current deterministic Olist simulation to be replaced or supplemented by production-style source providers in the future.

A daily replay represents one completeness boundary containing multiple independent source deliveries.

Mercury will attempt all safe work for the current date and make successfully processed independent source data available rather than withholding it because another source failed.

Overall date completeness remains a separate derived concept.

An incomplete historical date stops automatic progression to later dates after all safe work for the current date has been attempted.

Persistent execution state, run identity, and targeted recovery are defined by ADR-010 rather than embedded directly into ADR-009.

This preserves the core principle:

> Historical replay coordinates existing ingestion components; it does not replace their responsibilities.

And, as the architecture evolves toward recovery:

> Maximize safe source availability without confusing partial availability with complete delivery.