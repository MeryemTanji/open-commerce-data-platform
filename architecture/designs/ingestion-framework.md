# Mercury Ingestion Framework

## Purpose

The ingestion framework defines how source data enters Mercury and progresses through the Raw data platform.

Its purpose is to provide a consistent, reusable pattern for receiving data from independent source systems, preserving immutable source artifacts, loading source-faithful warehouse tables, and maintaining the operational state required to replay, recover, and reconcile ingestion activity safely.

The framework separates source-specific behavior from shared platform capabilities such as:

- source delivery;
- connector execution;
- validation;
- metadata generation;
- Raw object storage;
- warehouse loading;
- replay orchestration;
- operational state;
- recovery;
- provenance;
- reconciliation.

This allows new source integrations to reuse the platform rather than rebuilding ingestion infrastructure for every source.

---

## Design Goals

The ingestion framework should:

- support multiple independent source systems;
- support sources with different refresh and delivery patterns;
- preserve source data without analytical transformation;
- use consistent connector and storage interfaces;
- produce structured ingestion metadata;
- support historical replay of incremental deliveries;
- support repeatable and idempotent execution;
- isolate independent source failures where safe;
- maintain durable operational state;
- preserve physical lineage between Raw artifacts and warehouse loads;
- recover failed work using the minimum safe physical action;
- reconcile ambiguous execution state from durable evidence;
- fail clearly and safely when deterministic automation is not justified;
- remain simple enough to run locally;
- support deployment to cloud execution services;
- minimize source-specific code outside source-specific components.

---

## Scope

Mercury Version 1 supports batch ingestion from public datasets, including:

- one-off reference loads;
- simulated daily incremental deliveries;
- immutable Raw object storage;
- BigQuery Raw loading;
- historical replay;
- durable replay state;
- targeted recovery;
- physical provenance;
- reconciliation.

The framework currently ingests the Olist e-commerce dataset, with individual files treated as separate Nova Commerce operational source objects.

The current implementation does not include:

- real-time streaming;
- change data capture;
- direct production API integrations;
- distributed processing;
- automatic schema evolution.

These capabilities may be introduced later when justified by a concrete platform requirement.

---

## Framework Overview

Mercury separates the physical data path from the operational control plane.

### Data Path

```text
Source
   ↓
Source Delivery
   ↓
Connector
   ↓
Immutable Raw Artifact
   ↓
BigQuery Raw
```

The data path is responsible for moving source data into durable Raw storage without applying analytical transformations.

### Operational Control Plane

```text
Replay State
     +
Provenance
     ↓
Recovery Planning
     ↓
Recovery Execution
     ↓
Reconciliation
```

The control plane records what Mercury attempted, what physically exists, and what work can safely be performed when execution fails or becomes ambiguous.

Operational metadata is stored separately from business Raw data.

### Source-System Model

Although the initial data originates from one public dataset, Mercury treats each business function as an independent operational source.

| Mercury Source | Source Object | Reference Dataset |
| --- | --- | --- |
| Customer Platform | Customers | `olist_customers_dataset.csv` |
| Order Platform | Orders | `olist_orders_dataset.csv` |
| Order Platform | Order Items | `olist_order_items_dataset.csv` |
| Product Catalogue | Products | `olist_products_dataset.csv` |
| Marketplace Platform | Sellers | `olist_sellers_dataset.csv` |
| Payment Platform | Payments | `olist_order_payments_dataset.csv` |
| Review Platform | Reviews | `olist_order_reviews_dataset.csv` |
| Public Geographic Source | Geolocations | `olist_geolocation_dataset.csv` |

Each source is ingested independently and receives its own configuration, execution metadata, and Raw Landing path.

This separation allows failures and recovery decisions to operate at source-object level rather than treating an entire business date as one indivisible ingestion job.

### Source Delivery Patterns

Mercury does not assume that every source system delivers data at the same frequency or using the same loading pattern.

In a real commerce environment, some operational sources continuously produce new transactional data, while other sources behave more like master or reference datasets and may change less frequently.

The Olist dataset is provided as a collection of static historical CSV files. To make Mercury behave more like a real data platform, the ingestion framework simulates different source-delivery patterns using temporal information that actually exists in the source data.

Mercury Version 1 distinguishes between:

**1. initial / one-off source loads;**
**2. daily incremental source loads.**

The framework does not fabricate timestamps or artificial update histories for datasets that do not contain reliable temporal information.

### Initial / One-Off Loading Jobs

The following sources are treated as master or reference datasets during Version 1:

| Source Object | Version 1 Loading Pattern | Rationale |
| --- | --- | --- |
| Customers | Initial load | The Olist customer dataset does not contain a reliable customer-created timestamp. Mercury therefore treats the available customer population as an existing customer master at the beginning of the simulation. |
| Products | Initial load | Product creation or update timestamps are not available. Mercury Version 1 assumes the product catalogue remains stable during the simulated period rather than inventing product-history events. |
| Sellers | Initial load | Seller creation or onboarding timestamps are not available. Mercury therefore treats the seller population as an existing marketplace master dataset. |
| Geolocations | Initial load | Geolocation data is external geographic reference data rather than transactional business activity and is treated as static during Version 1. |

These sources may change in a real production environment.

For example, a real commerce platform would onboard new customers, products, and sellers over time. Mercury deliberately does not simulate those changes unless the source data provides a defensible way to determine when they occurred.

This keeps the simulation grounded in the source rather than manufacturing temporal behaviour solely for demonstration purposes.

Reference sources currently remain outside the transactional replay and targeted-recovery lifecycle.

#### Daily Incremental Loading Jobs

Transactional sources with reliable temporal information are replayed as daily incremental deliveries.

| Source Object | Incremental Date Logic |
| --- | --- |
| Orders | `order_purchase_timestamp` |
| Order Items | Derived from the parent Order's `order_purchase_timestamp` |
| Payments | Derived from the parent Order's `order_purchase_timestamp` |
| Reviews | `review_creation_date` |

Each simulated daily delivery contains only the records associated with that business date.

This is an **incremental delivery model**, not a cumulative snapshot model.

For example:

    2017-05-01
        orders created on 2017-05-01

    2017-05-02
        orders created on 2017-05-02

    2017-05-03
        orders created on 2017-05-03

A valid incremental source delivery may contain zero business records.

A zero-record delivery remains a valid delivery and is distinct from a source delivery being absent altogether.

#### Simulated Delivery and Ingestion Dates

Mercury distinguishes the business date represented by a source delivery from the date on which that delivery is ingested.

For the Olist historical simulation:

    delivery_date
        = business date represented by the source records

    ingestion_date
        = simulated date on which Mercury processes that delivery

Transactional daily deliveries are simulated as being ingested on the following calendar day:

    ingestion_date = delivery_date + 1 day

For example:

    order_purchase_timestamp = 2017-05-19
    delivery_date             = 2017-05-19
    ingestion_date            = 2017-05-20

The two dates have different infrastructure responsibilities.

```text
delivery_date
     ↓
logical business date
     ↓
BigQuery partition_date
```

while:

```text
ingestion_date
     ↓
Raw landing path
```

The +1 day relationship is specific to the Olist historical simulation.

It is not a generic Mercury ingestion rule and must not be encoded into reusable connector, storage, warehouse-loading, replay, recovery, or reconciliation components.

A future production source integration should provide its actual delivery and processing timing according to that source's real delivery behaviour.

### Connector Framework

Source-specific ingestion is implemented through reusable connector abstractions.

The framework separates:

```text
source-specific knowledge
          ↓
       connector
          ↓
shared ingestion capabilities
```

Shared connector behavior includes responsibilities such as:

- validating expected source structure;
- producing consistent ingestion metadata;
- calculating integrity information;
- writing through the configured storage backend;
- reporting success or failure through a common execution contract.

Source-specific connectors define only the behavior required to understand their source object.

This avoids duplicating shared ingestion mechanics across individual connectors.

The current Olist implementation contains connectors for all eight source objects.

Detailed connector design decisions are documented in [ADR-005](../decisions/ADR-005-Introduce%20a%20Shared%20CSV%20Connector%20Abstraction.md).

### Raw Storage

Connectors do not directly depend on one physical storage implementation.

Mercury uses a storage abstraction so ingestion logic can operate against interchangeable backends.

Current implementations support:

    Local Storage
        or
    Google Cloud Storage

Local storage supports development and testing.

Google Cloud Storage provides the cloud Raw Landing implementation.

The GCS Raw layer is immutable.

Objects are created using deterministic Raw paths and create-only semantics so an existing artifact cannot be silently overwritten by a later execution.

Raw artifacts also carry integrity metadata including SHA-256 checksums.

A typical Raw path follows:

```text
raw/
└── <source_system>/
    └── <source_object>/
        └── ingestion_date=YYYY-MM-DD/
            └── <source_file>
```

The Raw layer preserves source data rather than applying analytical transformations.

Detailed storage decisions are documented in [ADR-006](../decisions/ADR-006-Abstract%20Raw%20Landing%20Storage%20Behind%20a%20StorageManager%20Interface.md).

### BigQuery Raw Loading

Warehouse loading is intentionally separate from connector ingestion.

```text
Connector
    ↓
Immutable Raw Artifact
    ↓
BigQuery Raw Loader
    ↓
BigQuery Raw
```

This separation keeps object storage and warehouse materialisation independently testable and replaceable.

Mercury uses explicit BigQuery schemas rather than schema autodetection.

#### Transactional Sources

    orders
    order_items
    payments
    reviews

are loaded into date-partitioned BigQuery Raw tables.

The business delivery_date determines the target warehouse partition.

#### Reference Sources

    customers
    products
    sellers
    geolocations

are loaded as one-off, non-partitioned Raw reference tables.

The BigQuery Raw layer remains source-faithful and does not perform analytical normalisation.

Detailed warehouse-loading decisions are documented in [ADR-008](../decisions/ADR-008-Define%20the%20BigQuery%20Raw%20Loading%20Strategy.md).

### Historical Replay

Mercury supports deterministic historical replay of transactional source deliveries.

For each business date, replay coordinates the expected transactional source population:

    orders
    order_items
    payments
    reviews

Each source is processed independently through:

```text
Source Delivery
      ↓
Connector Ingestion
      ↓
Immutable Raw Landing
      ↓
BigQuery Raw
```

Replay validates expected source membership before ingestion.

A valid source delivery containing zero business records remains valid.

An empty delivery batch where expected source deliveries are absent is not treated as equivalent to a zero-record delivery.

Independent source failures are isolated where safe.

A failure in one source does not prevent unrelated sibling sources for the same business date from completing eligible work.

Progression to later dates stops only after safe work for the current date has been attempted and the date remains logically incomplete.

Detailed replay orchestration is documented in [ADR-009](../decisions/ADR-009-Decouple%20Source%20Delivery%20from%20Pipeline%20Orchestration.md) and [ADR-010](../decisions/ADR-010-Persist%20Source-Level%20Historical%20Replay%20State%20and%20Derive%20Date-Level%20Completion.md).

### Replay State

Transactional historical replay maintains durable, append-only source-level operational state.

The logical source-job identity is:

    delivery_date + source_object

Execution attempts additionally receive a:

    run_id

and persisted state transitions receive unique event identities.

Replay state distinguishes execution history from logical completion.

In particular:

    latest execution attempt
            ≠
    logical source completion

A source that has previously reached durable warehouse success remains logically complete even if a later re-attempt fails.

This prevents newer failed attempts from erasing evidence of earlier successful completion.

Replay state is operational metadata and remains outside the business Raw layer.

Detailed state semantics are defined by [ADR-010](../decisions/ADR-010-Persist%20Source-Level%20Historical%20Replay%20State%20and%20Derive%20Date-Level%20Completion.md).

### Targeted Recovery

Mercury does not assume that every failed or incomplete source requires the entire ingestion path to be rerun.

Recovery is stage-aware.

The recovery planner evaluates durable history and available evidence and selects the minimum safe action.

Current recovery actions are:

    SKIP
    INGEST_AND_LOAD
    LOAD_ONLY
    RECONCILE
    MANUAL_REVIEW

Conceptually:

```text
Replay History + Evidence
           ↓
     RecoveryPlanner
           ↓
       RecoveryPlan
           ↓
     RecoveryExecutor
```

Examples include:

- skipping work that is already complete;
- rerunning ingestion and warehouse loading when required;
- reusing an already validated immutable Raw artifact for warehouse-only recovery;
- reconciling ambiguous physical/control-plane state;
- blocking automation when evidence is insufficient.

Recovery execution receives a fresh execution identity and appends new state rather than rewriting earlier operational history.

Detailed recovery behavior is defined by [ADR-010](../decisions/ADR-010-Persist%20Source-Level%20Historical%20Replay%20State%20and%20Derive%20Date-Level%20Completion.md).

### Physical Provenance

Mercury records append-only provenance for the physical data path.

Two provenance entities connect Raw artifacts with warehouse materialisation:

    RawArtifactProvenance
            ↓
    WarehouseLoadProvenance

Together they establish lineage across:

```text
Source Delivery
      ↓
Immutable Raw Artifact
      ↓
Raw Artifact Provenance
      ↓
Warehouse Load
      ↓
Warehouse Load Provenance
      ↓
BigQuery Raw
```

Raw artifact provenance records the physical identity and integrity characteristics of a landed artifact.

Warehouse-load provenance records the warehouse materialisation created from that artifact.

The shared provenance identity links a warehouse load to the exact immutable Raw artifact from which it originated.

Provenance is append-only so repeated execution attempts preserve historical evidence rather than replacing it.

Detailed provenance semantics are defined by [ADR-010](../decisions/ADR-010-Persist%20Source-Level%20Historical%20Replay%20State%20and%20Derive%20Date-Level%20Completion.md).

### Reconciliation

Some failures are ambiguous.

For example, a cloud operation may have physically completed while the process failed before durable replay state was persisted.

Mercury does not automatically assume either success or failure in this situation.

Instead, reconciliation compares durable provenance with independently observable cloud metadata.

```text
RecoveryAction.RECONCILE
          ↓
   RecoveryReconciler
       ↙       ↘
      ↙         ↘
GCS Metadata   BigQuery Metadata
      ↘         ↙
       ↘       ↙
       Provenance
           ↓
   CONFIRMED / BLOCKED
```

Reconciliation uses metadata-only inspection where possible.

For GCS, Mercury can validate evidence such as:

- object existence;
- checksum metadata;
- object size;
- expected ingestion-date path.

For BigQuery, Mercury can validate:

- destination identity;
- partition existence;
- row count.

Automatic confirmation requires the available evidence to agree.

If evidence is missing, malformed, or contradictory, reconciliation blocks rather than inventing a conclusion.

Confirmed reconciliation does not repeat physical work merely to recreate control-plane state.

Detailed reconciliation rules and evidence requirements are defined by [ADR-010](../decisions/ADR-010-Persist%20Source-Level%20Historical%20Replay%20State%20and%20Derive%20Date-Level%20Completion.md).

### Failure and Safety Model

Mercury distinguishes ordinary source failures from failures affecting the integrity of the operational control plane.

Ordinary source failures are isolated where safe so independent sibling work can continue.

Failures involving critical state or provenance persistence fail closed because Mercury cannot safely reason about recovery without trustworthy operational evidence.

The framework follows several safety principles:

- do not overwrite immutable Raw evidence;
- do not silently erase previous successful completion;
- do not repeat physical work when durable evidence proves it already - exists;
- do not infer success from assumptions alone;
- do not automatically resolve contradictory evidence;
- preserve execution history append-only;
- use safe Mercury-authored operational errors rather than persisting raw provider payloads.

Security and data-leak-prevention requirements are defined by [ADR-011](../decisions/ADR-011-Data%20Security,%20Privacy,%20and%20Data-Leak%20Prevention.md).

### Current Framework Components 

The ingestion implementation now includes the following platform capabilities:

```text
ingestion/
│
├── source delivery
│   ├── reference delivery
│   └── incremental delivery
│
├── connectors
│   ├── shared CSV connector behavior
│   └── source-specific connectors
│
├── storage
│   ├── local Raw storage
│   └── Google Cloud Storage
│
├── warehouse loading
│   └── BigQuery Raw
│
├── replay
│   ├── historical orchestration
│   └── durable replay state
│
├── recovery
│   ├── recovery planning
│   └── recovery execution
│
├── provenance
│   ├── Raw artifact provenance
│   └── warehouse-load provenance
│
└── reconciliation
    ├── GCS metadata inspection
    ├── BigQuery metadata inspection
    └── provenance-backed reconciliation
```

These components form one ingestion platform while remaining separated by responsibility.

The intended relationship is:

```text
SOURCE-SPECIFIC
      │
      ▼
Source Delivery + Connector
      │
      ▼
─────────────────────────────
      SHARED PLATFORM
─────────────────────────────
      │
      ├── Raw Storage
      ├── Warehouse Loading
      ├── Replay State
      ├── Recovery
      ├── Provenance
      └── Reconciliation
```

This separation allows future source systems to reuse the operational capabilities already implemented by Mercury.

### Architecture Ownership

This document provides the implementation-level overview of Mercury's ingestion framework.

Detailed architectural rules remain owned by the relevant Architecture Decision Records:

| ADR     | Responsibility                                         |
| ------- | ------------------------------------------------------ |
| ADR-002 | Immutable Raw data                                     |
| ADR-005 | Shared CSV connector abstraction                       |
| ADR-006 | Raw Landing storage abstraction                        |
| ADR-007 | Source delivery and historical simulation              |
| ADR-008 | BigQuery Raw loading                                   |
| ADR-009 | Historical replay orchestration                        |
| ADR-010 | Replay state, recovery, provenance, and reconciliation |
| ADR-011 | Security, privacy, and data-leak prevention            |


This separation is intentional.

The ingestion framework documentation explains **how the implemented components fit together**.

The ADRs explain **why the architectural boundaries and rules exist**.