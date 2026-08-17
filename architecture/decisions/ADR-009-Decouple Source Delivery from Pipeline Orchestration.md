# ADR-009: Decouple Source Delivery from Pipeline Orchestration

## Status

Accepted

## Date

2026-08-17

---

## Context

Mercury currently ingests the Olist e-commerce dataset as the first implementation of its source-ingestion framework.

The Olist dataset is distributed as static historical CSV files. To make this dataset behave more like operational source systems, Mercury introduced `OlistSourceSimulator`, which can:

- generate initial deliveries for master and reference datasets;
- generate date-specific incremental deliveries for transactional datasets;
- preserve source values and schemas;
- derive related transactional deliveries from order purchase dates where appropriate;
- represent empty daily deliveries as valid header-only CSV files.

This allows Mercury to simulate realistic daily source deliveries while remaining grounded in the temporal information available in the source data.

The current simulated delivery patterns are:

### Initial / Master-Reference Sources

- customers;
- products;
- sellers;
- geolocations.

### Daily Incremental Sources

- orders;
- order items;
- payments;
- reviews.

The simulator has been validated independently from the ingestion framework.

Generated deliveries can be passed through the existing connectors, persisted through `GCSStorageManager`, and subsequently loaded into BigQuery Raw through `BigQueryRawLoader`.

This establishes the current flow:

```text
Olist Historical CSVs
        ↓
OlistSourceSimulator
        ↓
Generated Local CSV Delivery
        ↓
Source Connector
        ↓
GCSStorageManager
        ↓
Immutable GCS Raw Landing
        ↓
BigQueryRawLoader
        ↓
BigQuery Raw
```

However, directly coupling future pipeline orchestration to `OlistSourceSimulator` would make the orchestration layer aware of a specific dataset and a specific source-delivery mechanism.

That would conflict with Mercury's broader platform objective.

Mercury is intended to demonstrate a reusable data-platform architecture capable of supporting heterogeneous operational source systems.

A real commerce environment may receive data through mechanisms such as:

- REST APIs;
- scheduled file deliveries;
- SFTP;
- cloud object storage;
- database exports;
- managed platform connectors;
- other batch-oriented interfaces.

The Olist CSV implementation should therefore be treated as the first source adapter rather than as the permanent source contract of Mercury.

---

## Problem

Mercury needs historical replay orchestration so that simulated daily source deliveries can be processed automatically across a date range.

Without orchestration, loading historical data would require manually repeating the following process for every business date:

```text
Generate daily delivery
        ↓
Run source connectors
        ↓
Land artifacts in GCS
        ↓
Load GCS artifacts into BigQuery
        ↓
Repeat for next date
```

For several years of historical data, manual execution would be impractical and error-prone.

A straightforward implementation could make a historical replay runner directly call:

```python
OlistSourceSimulator.generate_daily_load(...)
```

However, this would create an undesirable dependency:

```text
HistoricalReplayRunner
        ↓
OlistSourceSimulator
```

The orchestration layer would then depend directly on:

- the Olist dataset;
- local CSV files;
- the simulation implementation;
- the current source-delivery mechanism.

Introducing a REST API or another source transport later could consequently require rewriting or significantly modifying orchestration logic.

Mercury therefore needs a stable boundary between:

1. obtaining a source delivery; and
2. processing that delivery through the platform.

---

## Decision

Mercury will introduce a **Source Delivery Provider abstraction** between source acquisition or simulation and pipeline orchestration.

Pipeline orchestration will depend on the provider contract rather than directly on `OlistSourceSimulator` or any future source transport.

The architecture becomes:

```text
Source System / Simulation
        ↓
SourceDeliveryProvider
        ↓
SourceDeliveryBatch
        ↓
HistoricalReplayRunner
        ↓
Source Connectors
        ↓
GCSStorageManager
        ↓
BigQueryRawLoader
        ↓
BigQuery Raw
```

The first provider implementation will wrap the existing Olist simulation framework.

Future provider or connector implementations may introduce REST APIs or other source-delivery mechanisms without requiring the downstream platform architecture to be redesigned.

---

## Source Delivery Contract

Mercury will define a common representation for source deliveries.

A source delivery represents an artifact made available by an upstream source for ingestion into Mercury.

The initial contract will contain the information required by the current file-based ingestion framework.

Conceptually:

```python
@dataclass(frozen=True, slots=True)
class SourceDelivery:
    source_object: str
    path: Path
    delivery_date: date | None
    record_count: int
```

A collection of related source deliveries will be represented as a batch:

```python
@dataclass(frozen=True, slots=True)
class SourceDeliveryBatch:
    deliveries: tuple[SourceDelivery, ...]
    delivery_date: date | None
```

The exact implementation may introduce additional validation where required, but the abstraction should remain intentionally small.

The delivery contract must not contain:

- GCS-specific configuration;
- BigQuery-specific configuration;
- warehouse schemas;
- partition decorators;
- transformation logic;
- business metrics.

These belong to downstream platform components.

---

## Source Delivery Provider

Mercury will define a provider interface responsible for making source deliveries available to the ingestion pipeline.

Conceptually:

```python
class SourceDeliveryProvider(ABC):

    @abstractmethod
    def get_initial_delivery(self) -> SourceDeliveryBatch:
        ...

    @abstractmethod
    def get_daily_delivery(
        self,
        delivery_date: date,
    ) -> SourceDeliveryBatch:
        ...
```

The provider answers questions such as:

> What source artifacts are available for the initial load?

and:

> What source artifacts are available for this business date?

It does not determine how those artifacts are stored in GCS or loaded into BigQuery.

---

## Initial Provider Implementation

The first implementation will be an Olist simulated source provider.

```text
Olist Historical CSVs
        ↓
OlistSourceSimulator
        ↓
OlistSimulatedSourceProvider
        ↓
SourceDeliveryBatch
```

The provider will adapt the simulator's existing result objects into the common source-delivery contract.

It will not duplicate the simulation logic.

Conceptually:

```python
class OlistSimulatedSourceProvider(SourceDeliveryProvider):

    def get_initial_delivery(self):
        simulation_result = self.simulator.generate_initial_load()
        return adapt_to_source_delivery_batch(simulation_result)

    def get_daily_delivery(self, delivery_date):
        simulation_result = self.simulator.generate_daily_load(
            delivery_date
        )
        return adapt_to_source_delivery_batch(simulation_result)
```

`OlistSourceSimulator` therefore remains responsible for:

- filtering source records by simulation date;
- deriving order-related incremental deliveries;
- preserving source schemas and values;
- producing initial and daily source artifacts;
- validating simulation-critical fields;
- preventing accidental overwrite of generated deliveries.

The provider is responsible only for exposing those artifacts through Mercury's common source-delivery interface.

---

## Historical Replay Orchestration

Mercury will introduce a dedicated orchestration layer for historical replay.

The orchestration layer will live separately from source simulation, ingestion, storage, and warehouse loading.

The relevant repository structure will become:

```text
mercury_ingestion/
├── sources/
│   ├── __init__.py
│   ├── base.py
│   └── simulated_olist.py
│
├── simulation/
│   ├── __init__.py
│   └── olist.py
│
├── orchestration/
│   ├── __init__.py
│   └── replay.py
│
├── connectors/
│
├── common/
│
├── warehouse/
│   ├── schemas.py
│   └── bigquery_loader.py
│
└── runner.py
```

The existing top-level `runner.py` remains the ingestion runner responsible for executing multiple connectors.

The new orchestration layer has a broader responsibility.

```text
IngestionRunner
    → executes a collection of connectors

HistoricalReplayRunner
    → coordinates source delivery,
      ingestion,
      warehouse loading,
      and historical date progression
```

---

## HistoricalReplayRunner Responsibilities

`HistoricalReplayRunner` will coordinate existing Mercury components rather than reimplement their behavior.

It may expose operations conceptually similar to:

```python
run_initial_load()
generate_range(start_date, end_date)
run_day(delivery_date)
run_range(start_date, end_date)
```

The exact public API may be refined during implementation.

### `run_initial_load()`

Coordinates the initial master/reference load:

```text
SourceDeliveryProvider
        ↓
customers
products
sellers
geolocations
        ↓
Source Connectors
        ↓
GCSStorageManager
        ↓
BigQueryRawLoader
        ↓
Unpartitioned BigQuery Raw Tables
```

This follows the source-delivery classification established in ADR-007.

### `generate_range(start_date, end_date)`

Generates source deliveries for a historical range without ingesting them into the cloud platform.

This operation keeps source simulation independently executable.

It is useful for:

- inspecting simulated source deliveries;
- validating historical replay behavior;
- debugging;
- testing;
- preparing source artifacts before platform ingestion.

### `run_day(delivery_date)`

Coordinates the complete transactional pipeline for one business date:

```text
SourceDeliveryProvider
        ↓
Daily SourceDeliveryBatch
        ↓
Orders Connector
Order Items Connector
Payments Connector
Reviews Connector
        ↓
IngestionRunner
        ↓
GCSStorageManager
        ↓
Successful GCS Landing Metadata
        ↓
BigQueryRawLoader
        ↓
Corresponding BigQuery Raw Partitions
```

A single business date is the natural unit of execution and recovery.

### `run_range(start_date, end_date)`

Automates historical replay by repeatedly executing the single-day workflow:

```text
Day 1
    obtain source delivery
    ingest
    warehouse load
    verify execution outcome

Day 2
    obtain source delivery
    ingest
    warehouse load
    verify execution outcome

Day 3
    ...

until end_date
```

Conceptually:

```python
for delivery_date in requested_date_range:
    run_day(delivery_date)
```

This eliminates the need to manually execute hundreds of daily ingestion and warehouse-loading commands.

---

## Independent Execution of Pipeline Stages

Although `HistoricalReplayRunner` can coordinate the complete pipeline, the underlying stages must remain independently executable.

The following operations must continue to work without the historical replay runner.

### Source Simulation Only

```text
OlistSourceSimulator
        ↓
Local Simulated Delivery
```

This allows source simulation to be developed, tested, and inspected independently.

### Ingestion Only

```text
Existing Local Delivery
        ↓
Connector
        ↓
GCSStorageManager
```

This allows the ingestion framework to operate against already-existing source deliveries.

### Warehouse Loading Only

```text
Existing GCS Artifact
        ↓
BigQueryRawLoader
        ↓
BigQuery Raw
```

This allows BigQuery Raw to be reconstructed or individual loads to be replayed directly from immutable GCS artifacts.

The orchestration layer is therefore a convenience and automation layer, not a replacement for the existing components.

This separation improves:

- testing;
- debugging;
- replayability;
- recovery;
- component reuse;
- future orchestration options.

---

## Component Responsibility Boundaries

Mercury will preserve clear responsibility boundaries between components.

### Source Provider

Responsible for:

- obtaining or preparing source deliveries;
- exposing those deliveries through a common contract.

Not responsible for:

- GCS persistence;
- BigQuery loading;
- warehouse schemas;
- transformations.

### Source Connector

Responsible for:

- source-specific structural validation;
- ingestion metadata generation;
- invoking the configured storage implementation;
- reporting ingestion success or failure.

Not responsible for:

- historical replay;
- BigQuery loading;
- source simulation;
- business transformations.

### GCSStorageManager

Responsible for:

- immutable physical persistence of Raw source artifacts in Google Cloud Storage;
- deterministic Raw landing paths;
- checksum and storage result behavior.

Not responsible for:

- source generation;
- warehouse loading;
- BigQuery schemas;
- transformations.

### BigQueryRawLoader

Responsible for:

- loading already-landed GCS artifacts into BigQuery Raw;
- explicit Raw schemas;
- master/reference table loading;
- transactional partition routing;
- partition-scoped idempotent replay behavior.

Not responsible for:

- obtaining source data;
- creating simulated source deliveries;
- uploading source artifacts to GCS;
- historical date iteration.

### HistoricalReplayRunner

Responsible for:

- coordinating components in the correct execution order;
- iterating through historical business dates;
- passing outputs from one stage into the next;
- reporting execution outcomes;
- stopping replay when a required stage cannot complete correctly.

Not responsible for:

- CSV filtering;
- source-specific extraction logic;
- GCS upload implementation;
- BigQuery schema definitions;
- partition decorator construction;
- business transformations.

---

## Data Handoff Between Components

Components should exchange result objects rather than reconstruct information already produced upstream.

For example, after successful ingestion:

```text
Connector
        ↓
IngestionMetadata
        ↓
landing_path
        ↓
HistoricalReplayRunner
        ↓
BigQueryRawLoader
```

The orchestration layer should use the GCS landing path returned by ingestion metadata rather than reconstructing the expected GCS URI independently.

Conceptually:

```python
bigquery_loader.load(
    source_object=connector_result.metadata.source_object,
    gcs_uri=connector_result.metadata.landing_path,
    ingestion_date=delivery_date,
)
```

This reduces duplicated path logic and preserves ownership boundaries between components.

---

## Failure and Replay Model

Historical replay must be deterministic and observable.

For the initial implementation, a business date will be treated as a logical replay unit.

If all required stages for a date complete successfully:

```text
Day N
    source delivery    SUCCESS
    GCS ingestion      SUCCESS
    BigQuery loading   SUCCESS

→ continue to Day N + 1
```

If a required stage fails:

```text
Day N
    source delivery    SUCCESS
    GCS ingestion      SUCCESS
    BigQuery loading   FAILED

→ stop replay
→ report failing date and source
→ do not silently continue
```

This avoids creating a historical warehouse whose completeness boundary is unclear.

More sophisticated recovery strategies such as:

- configurable retries;
- partial-source continuation;
- checkpoints;
- resume modes;
- automated backfills;

may be introduced later when justified.

---

## Immutability and Existing Deliveries

The historical replay runner must respect the immutability guarantees already established by Mercury.

It must not silently delete or overwrite existing simulated source deliveries or GCS Raw artifacts in order to make a replay succeed.

Existing immutable destinations should surface through explicit behavior rather than destructive cleanup.

Replay and resume semantics will be introduced deliberately rather than by weakening the storage guarantees of the underlying components.

BigQuery Raw remains independently replayable from immutable GCS artifacts according to the idempotent loading strategy defined in ADR-008.

This distinction is important:

```text
GCS Raw Landing
    → immutable source artifact

BigQuery Raw
    → replayable query representation
```

If a BigQuery Raw table or partition needs to be reconstructed, the immutable GCS artifact remains the recovery source.

---

## REST API Extensibility

Mercury is intentionally being designed so that source acquisition is not permanently coupled to local CSV simulation.

The future architecture may support multiple source mechanisms:

```text
                         Source Delivery
                               │
              ┌────────────────┴────────────────┐
              │                                 │
              ▼                                 ▼
     Olist Simulation                     REST API
              │                                 │
              ▼                                 ▼
OlistSimulatedSourceProvider          REST/API Adapter
              │                                 │
              └────────────────┬────────────────┘
                               ▼
                    Pipeline Orchestration
                               ▼
                         Raw Landing
                               ▼
                          BigQuery
```

The exact API architecture is intentionally deferred.

Possible future capabilities include:

- HTTP source requests;
- JSON responses;
- pagination;
- authentication;
- retries;
- request timeouts;
- rate-limit handling;
- API-specific connectors;
- transient-error handling;
- incremental cursor or watermark strategies.

These concerns should be introduced as source-specific capabilities rather than embedded in the historical replay runner.

---

## Why the REST API Is Not Implemented in This Decision

REST API ingestion is considered an important future capability for Mercury.

However, implementing an HTTP service at this stage would introduce additional concerns including:

- API server lifecycle;
- endpoint design;
- request and response contracts;
- JSON serialization;
- pagination;
- retries;
- timeouts;
- authentication;
- HTTP status handling;
- rate limiting;
- API client implementation and testing.

These concerns are valuable when Mercury specifically begins demonstrating API-based ingestion, but they are not required to validate the current core platform path:

```text
Source Delivery
        ↓
Ingestion
        ↓
Immutable Raw Storage
        ↓
Queryable Raw Warehouse
        ↓
Transformation
```

Mercury will therefore **design for REST extensibility now without implementing the REST transport yet**.

This avoids unnecessary complexity while preventing the current CSV implementation from becoming an architectural constraint.

---

## Future REST/API Integration

When API ingestion is introduced, Mercury should not require a redesign of:

- `GCSStorageManager`;
- `BigQueryRawLoader`;
- BigQuery Raw schemas;
- Dataform staging;
- historical warehouse structure;
- pipeline orchestration.

Depending on the API response format and ingestion requirements, the future implementation may introduce:

```text
RestApiSourceProvider
```

and/or API-specific connectors such as:

```text
OrdersApiConnector
PaymentsApiConnector
```

rather than forcing JSON responses through the existing CSV connectors.

For example:

```text
CSV Source
    ↓
CSV Connector
    ┐
    │
    ├────────→ Common Raw Landing Boundary
    │                    ↓
    │                   GCS
    │                    ↓
    │                 BigQuery
    │
REST API
    ↓
API Connector
    ┘
```

This allows different source transports to converge on the same downstream platform architecture.

The future API implementation should therefore extend Mercury rather than replace the existing ingestion framework.

---

## Architectural Goal

The long-term objective is not to demonstrate that Mercury can process Olist CSV files.

The objective is to demonstrate that Mercury provides a reusable ingestion and analytics platform in which source acquisition can evolve independently from downstream storage, warehouse, transformation, and data-product layers.

The desired architectural property is:

```text
Change Source Transport
        ↓
Do Not Redesign the Platform
```

For example:

```text
CSV
REST API
SFTP
Database Export
Cloud Object Storage
        ↓
Source-Specific Acquisition / Adapter
        ↓
Mercury Raw Landing Contract
        ↓
GCS
        ↓
BigQuery Raw
        ↓
Dataform
        ↓
Core / Features / Data Products
```

Source independence is therefore a deliberate architectural property of Mercury rather than a future implementation detail.

---

## Consequences

### Positive

#### Source Transport Is Decoupled from Orchestration

The historical replay runner does not need to know whether a delivery originated from Olist simulation, an API, or another future source.

#### Current CSV Work Remains Useful

The existing simulator and connectors become the first implementation of a broader source architecture rather than temporary code that must later be discarded.

#### REST Ingestion Can Be Introduced Incrementally

Mercury can add API-specific capabilities later without rewriting the GCS or BigQuery layers.

#### Historical Replay Becomes Automated

Several years of transactional source history can be replayed without manually executing ingestion and warehouse-loading commands for every date.

#### Pipeline Stages Remain Independently Testable

Simulation, ingestion, storage, and warehouse loading can still be executed and validated separately.

#### Failure Recovery Remains Understandable

A single business date provides a clear execution and recovery boundary for historical replay.

#### BigQuery Can Be Reconstructed from GCS

Because immutable GCS artifacts remain independent from their BigQuery representation, warehouse data can be replayed without reacquiring the original source.

#### Portfolio Architecture Becomes More Representative

Mercury demonstrates architectural separation between source acquisition, ingestion, storage, warehouse loading, and orchestration rather than presenting a dataset-specific ETL script.

---

### Negative

#### Additional Abstraction

The source-provider interface introduces another layer between simulation and ingestion.

For the current Olist implementation, direct calls to `OlistSourceSimulator` would be simpler.

This additional abstraction is accepted because Mercury explicitly intends to support multiple source-delivery mechanisms.

#### More Result Objects and Adapters

Simulation results must be adapted into the common source-delivery contract.

#### REST Support Is Not Immediate

This decision creates the architectural extension point but does not itself demonstrate HTTP ingestion.

A later implementation will still be required to prove REST/API ingestion.

#### Replay and Resume Behavior Requires Careful Design

Immutable source artifacts mean historical replay cannot simply overwrite existing deliveries when rerun.

Explicit resume or recovery semantics may therefore be required later.

---

## Alternatives Considered

### Alternative 1 — Couple HistoricalReplayRunner Directly to OlistSourceSimulator

```text
HistoricalReplayRunner
        ↓
OlistSourceSimulator
```

Rejected because this makes orchestration Olist-specific and couples the pipeline to the current simulation mechanism.

---

### Alternative 2 — Build the REST API Immediately

```text
Olist Data
    ↓
Fake REST API
    ↓
API Client
    ↓
Mercury
```

Deferred rather than permanently rejected.

API ingestion is valuable, but implementing HTTP transport now would add significant scope before the core platform and orchestration layers are complete.

The provider abstraction preserves a clean path to implementing this later.

---

### Alternative 3 — Keep Standalone Manual Scripts

Rejected because manually replaying several years of daily transactional deliveries would be repetitive, error-prone, difficult to resume, and unsuitable for demonstrating production-oriented orchestration.

---

### Alternative 4 — Put Orchestration Inside the Warehouse Package

Rejected because historical replay coordinates source acquisition, ingestion, storage, and warehouse loading.

It is therefore a pipeline-level concern rather than a BigQuery-specific concern.

`warehouse/` will remain focused on BigQuery Raw loading behavior.

---

### Alternative 5 — Build One Monolithic Pipeline Runner

A single component could implement simulation, CSV filtering, GCS upload, BigQuery loading, and historical iteration.

Rejected because it would duplicate responsibilities already owned by specialized components and create tight coupling between layers.

The orchestration layer will coordinate components rather than absorb their implementation logic.

---

## Implementation Direction

The first implementation following this ADR will introduce:

```text
mercury_ingestion/
├── sources/
│   ├── __init__.py
│   ├── base.py
│   └── simulated_olist.py
│
└── orchestration/
    ├── __init__.py
    └── replay.py
```

### Phase 1 — Source Abstraction

Implement:

- `SourceDelivery`;
- `SourceDeliveryBatch`;
- `SourceDeliveryProvider`;
- `OlistSimulatedSourceProvider`.

Validate that the provider can expose both initial and daily simulator outputs without changing `OlistSourceSimulator`.

### Phase 2 — Single-Day Orchestration

Implement `HistoricalReplayRunner.run_day()`.

Validate:

```text
Source Provider
        ↓
Connectors
        ↓
GCS
        ↓
BigQuery
```

for one transactional business date.

### Phase 3 — Historical Range Replay

Implement date-range iteration using the validated single-day execution path.

Conceptually:

```python
for delivery_date in date_range:
    run_day(delivery_date)
```

Historical replay should build upon the already-tested single-day workflow rather than introducing a separate loading implementation.

### Phase 4 — Initial-Load Orchestration

Automate the master/reference flow for:

- customers;
- products;
- sellers;
- geolocations.

### Phase 5 — Future Source Adapters

After Mercury's core platform is established, introduce additional source-delivery mechanisms such as REST API ingestion while preserving the downstream platform contracts.

---

## Decision Summary

Mercury will decouple source delivery from pipeline orchestration through a `SourceDeliveryProvider` abstraction.

The existing Olist simulation framework will become the first provider implementation.

Historical replay orchestration will coordinate:

```text
SourceDeliveryProvider
        ↓
Source Connectors
        ↓
GCSStorageManager
        ↓
BigQueryRawLoader
```

without absorbing the responsibilities of those components.

Pipeline stages will remain independently executable.

Historical daily replay will use a single business date as its fundamental execution and recovery unit.

Immutable GCS Raw artifacts will remain the durable recovery source, while BigQuery Raw remains an idempotently replayable warehouse representation.

REST API ingestion will not be implemented immediately, but the architecture will explicitly support its later introduction without requiring the downstream platform to be redesigned.

This decision allows Mercury to validate its current CSV-based ingestion path while preserving its long-term objective of being a reusable, source-agnostic data platform.