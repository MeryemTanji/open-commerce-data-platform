# Mercury Canonical Model Design

## Status

Draft

## Date

2026-09-11

## Purpose

This document defines the logical and implementation design for Mercury's canonical business model.

The canonical layer transforms validated staging relations into stable, reusable business entities that are independent of individual source-system schemas. It provides the governed foundation from which downstream data products, analytical models, dashboards, and applications can be built.

This design translates Mercury's architectural decisions into platform-wide canonical modelling, implementation, and publication requirements. Source-specific canonical contracts apply these requirements to individual source systems.

## Governing Decisions

This design implements the following architectural decisions:

- [ADR-001: Adopt a Layered Data Platform Architecture](../decisions/ADR-001-Adopt%20a%20Layered%20Data%20Platform%20Architecture.md)
- [ADR-003: Adopt a Canonical Business Model](../decisions/ADR-003-Adopt%20a%20Canonical%20Business%20Model.md)
- [ADR-004: Publish Reusable Data Products](../decisions/ADR-004-Publish%20Reusable%20Data%20Products.md)
- [ADR-011: Data Security, Privacy, and Data-Leak Prevention](../decisions/ADR-011-Data%20Security,%20Privacy,%20and%20Data-Leak%20Prevention.md)
- [ADR-012: Staging Layer Standardization and Semantic Contracts](../decisions/ADR-012-Staging%20Layer%20Standardization%20and%20Semantic%20Contracts.md)
- [ADR-013: Data Quality Anomaly Disposition and Monitoring Contract](../decisions/ADR-013-Data%20Quality%20Anomaly%20Disposition%20and%20Monitoring%20Contract.md)

Source-specific implementation contracts must reference the applicable staging contracts, relationship findings, and anomaly-disposition registers.

## 1. Scope

This document defines:

- the responsibility and boundary of the canonical layer;
- the canonical dataset ownership model;
- permitted canonical relation types;
- platform-wide grain, key, and relationship requirements;
- source-to-canonical dependency rules;
- identity-resolution requirements;
- anomaly-disposition implementation requirements;
- join-amplification safeguards;
- temporal modelling requirements;
- canonical quality and publication controls;
- Dataform dependency and execution requirements;
- requirements for source-specific canonical implementation contracts.

This document does not define:

- Raw or staging transformation contracts;
- source-specific canonical model inventories;
- source-specific column, grain, or key registries;
- source-specific profiling evidence or anomaly baselines;
- operational quality-history infrastructure;
- notification delivery channels;
- dashboard-specific models;
- machine-learning feature tables;
- final data-product schemas.

Those concerns remain governed by their corresponding architectural decisions and implementation documentation.

## 2. Canonical Layer Responsibility

The canonical layer represents stable business concepts rather than source-system structures.

It must:

- expose clearly named business entities;
- declare one explicit grain for every relation;
- define stable primary and relationship keys;
- preserve traceability to source and staging identifiers;
- maintain meaningful one-to-many and many-to-many relationships;
- implement approved anomaly dispositions visibly;
- prevent unintended join amplification;
- preserve independently meaningful measures;
- support reuse across multiple downstream data products;
- include automated validation of its published contracts.

The canonical layer must not:

- silently rewrite source-quality anomalies;
- reproduce staging relations under different names;
- collapse different business grains into one uncontrolled wide table;
- embed dashboard-specific presentation logic;
- select arbitrary records from repeated or ambiguous observations;
- infer missing business events without an approved deterministic rule;
- overwrite one valid measure merely to reconcile it with another.

## 3. Layer Boundary

Mercury's analytical flow is:

```text
Raw
    ↓
Staging
    ↓
Quality and relationship controls
    ↓
Canonical business model
    ↓
Reusable data products
```

Staging remains source-oriented and preserves valid source observations.

The canonical layer applies governed business semantics, resolves approved ambiguities, and publishes reusable entities at documented grains.

Data products remain consumer- or problem-oriented and may aggregate, filter, or combine canonical entities for defined analytical purposes.

## 4. Infrastructure Ownership

The canonical BigQuery dataset is:

```text
mercury-data-platform-dev.canonical
```

The ownership boundary is:

```text
Terraform
    ↓
canonical dataset and IAM

Dataform
    ↓
canonical relations and controls
```

Terraform manages:

- dataset identity;
- regional location;
- dataset labels and description;
- dataset-scoped IAM.

Dataform manages:

- canonical dimensions;
- canonical facts;
- canonical bridges;
- approved intermediate relations;
- canonical assertions;
- non-blocking canonical quality views where required.

Canonical transformations execute through:

```text
mercury-dataform@mercury-data-platform-dev.iam.gserviceaccount.com
```

The identity may manage relations inside `canonical` but may not create datasets, administer IAM, modify Raw data, or access the operational metadata dataset.

## 5. Design Principles

### 5.1 Grain before joins

Every canonical relation must declare and enforce its grain before relationships are added.

No join may be introduced unless its effect on the relation's grain is understood and validated.

### 5.2 Preserve distinct business processes

Distinct business processes must remain independently modelled at their natural grains.

For example, orders, order items, payments, and reviews must not be joined into one detailed relation merely because they share an order identifier.

### 5.3 Aggregate independently before combining

When multiple one-to-many child relations contribute measures to a parent-grain model, each child must first be aggregated independently to the parent key.

This prevents multiplication of measures across independent business processes.

### 5.4 Separate entities from associations

A reusable entity and its association with another entity may require separate relations.

Many-to-many relationships must be represented through an explicit bridge when consolidation would lose valid associations or change the entity grain.

### 5.5 Preserve source traceability

Canonical relations must retain the identifiers required to trace a record back through staging to its source representation.

Canonical identifiers must not obscure materially different source identity semantics.

### 5.6 Apply corrections explicitly

A deterministic downstream correction may be applied only when it is authorised by a documented anomaly disposition.

The canonical relation must preserve or expose:

- the original source-derived value;
- the resolved value;
- the applied resolution method;
- an anomaly or mismatch indicator where required.

### 5.7 Preserve usable records

A non-blocking anomaly must not cause an entire otherwise valid record to be discarded.

Records may be conditionally excluded only from measures or outputs affected by the anomaly.

### 5.8 Make publication testable

Every canonical relation must define automated controls appropriate to its grain and purpose.

These may include:

- primary-key uniqueness;
- required-value validation;
- accepted-domain validation;
- referential-integrity checks;
- row-count reconciliation;
- measure reconciliation;
- join-amplification detection;
- disposition-specific safeguards.

A canonical relation is not considered publishable until its blocking controls pass.

## 6. Canonical Relation Types

Mercury permits the following relation types within the canonical layer.

| Relation type | Prefix | Responsibility |
| --- | --- | --- |
| Dimension | `dim_` | Represents a reusable business entity or governed descriptive reference |
| Fact | `fct_` | Represents a measurable business event or process at a declared grain |
| Bridge | `bridge_` | Preserves a governed many-to-many association between canonical entities |
| Intermediate | `int_` | Applies reusable preparation or aggregation required by canonical models |
| Quality view | `dq_` | Surfaces non-blocking canonical quality conditions |
| Assertion | Dataform-generated or `assert_` | Enforces blocking canonical publication requirements |

Dimensions, facts, and bridges form the published canonical contract.

Intermediate relations are implementation dependencies rather than consumer-facing business entities. They must have a documented purpose and grain and must not become an undocumented alternative consumption layer.

Quality views and assertions govern publication but are not themselves canonical business entities.

## 7. Canonical Key Strategy

### 7.1 Canonical and source keys

Canonical relations must distinguish between:

| Key type | Responsibility |
| --- | --- |
| Canonical key | Provides the stable primary or foreign key used between canonical relations |
| Source identifier | Preserves the identifier supplied by the originating source |
| Source namespace | Identifies the source instance within which the source identifier is meaningful |
| Business natural key | Represents a governed non-source-specific identifier where one exists |

Canonical keys must not replace or obscure source identifiers.

Every source-derived canonical entity must retain:

- its canonical key;
- its source namespace;
- the source identifier or identifiers from which the canonical key was derived.

### 7.2 Deterministic generation

Source-derived canonical keys must be deterministic.

The conceptual input is:

```text
key version
    +
canonical entity type
    +
source namespace
    +
source identifier components
```

Mercury generates a hexadecimal SHA-256 value from a consistently serialized representation of those components.

Conceptually:

```text
canonical_key =
    SHA256(
        key_version,
        entity_type,
        source_namespace,
        source_identifiers
    )
```

The implementation must use a shared Dataform helper so serialization, component order, normalization, and key version remain consistent across models.

The initial key version is:

```text
v1
```

Changing the serialization method, component order, namespace, or key version constitutes a canonical contract change and must be reviewed explicitly.

### 7.3 Generation requirements

Canonical key generation must:

- use validated staging identifiers;
- preserve the case-sensitive value of source identifiers unless their staging contract defines normalization;
- use a stable lowercase source namespace;
- include the canonical entity type;
- include every component of a compound source key in declared order;
- reject required null key components through blocking controls;
- produce the same key on every deterministic rebuild;
- remain consistent between parent and child models.

Canonical key generation must not:

- depend on row order;
- use nondeterministic UUID generation;
- use warehouse-generated sequences;
- depend on execution time;
- treat hashing as identity resolution;
- treat hashing as anonymization.

A hashed customer identifier may still represent personal or linkable data and remains governed by Mercury's security and privacy controls.

### 7.4 Source namespaces

Every source instance contributing source-derived entities to the canonical layer must receive a stable lowercase namespace.

Reusing a namespace for a materially different source instance is prohibited because it could cause unrelated source identifiers to generate identical canonical keys.

Cross-source identity resolution must be implemented through an explicit governed mapping process. It must not be achieved by assigning different systems the same namespace or by assuming matching source identifiers represent the same business entity.

### 7.5 Non-source-derived keys

Not every canonical key requires a source namespace.

Governed reference entities may use stable business-domain keys when their identity is independent of a source system.

Each source-specific canonical contract must identify these exceptions and document their key components, normalization rules, and collision controls.

### 7.6 Collision and consistency controls

Every relation using generated canonical keys must enforce:

- canonical-key non-nullability;
- canonical-key uniqueness at the declared grain;
- consistency between each canonical key and its source components;
- absence of one canonical key mapping to multiple source-identifier combinations;
- referential compatibility between parent and child keys.

A uniqueness assertion remains required even when SHA-256 collision probability is negligible. The assertion also detects incorrect input composition, serialization defects, and unintended grain changes.

## 8. Temporal Modelling Requirements

### 8.1 Date dimension

Canonical implementations must provide a governed date dimension when facts expose reusable calendar relationships.

The date dimension must:

- declare one stable calendar grain;
- provide continuous coverage across the required canonical range;
- derive calendar attributes deterministically;
- support role-playing relationships from multiple business events;
- use a stable natural or governed canonical key;
- include blocking uniqueness and coverage controls.

### 8.2 Dates and timestamps

Canonical facts must preserve timestamps when time-of-day precision is meaningful.

Date keys supplement rather than replace timestamps. They support calendar filtering and aggregation but must not be used for elapsed-time calculations that require timestamp precision.

Source fields governed as calendar dates must not be converted into artificial midnight timestamps merely to conform to a timestamp representation.

### 8.3 Timezone conventions

Every source-specific canonical contract must declare the timezone or date-extraction convention used to derive calendar dates from timestamps.

Mercury must not infer timezone semantics from geography or apply unsupported timezone corrections.

A change to an approved timezone or date-extraction convention constitutes a canonical contract change and requires impact assessment.

### 8.4 Role-playing dates and durations

Multiple business-event dates may reference the same physical date dimension through role-specific foreign keys.

Each role must retain its own business meaning. One event date must not be substituted for another merely because the preferred value is absent.

Durations must be calculated from the most precise governed temporal values available. A duration must remain null when a required endpoint is unavailable unless an approved contract defines another treatment.

Mercury must not reorder temporal endpoints, apply absolute values to conceal negative durations, or fabricate missing lifecycle events.

### 8.5 Source-specific temporal contracts

Every source-specific canonical contract must declare:

- the temporal fields contributing to the calendar range;
- the date roles exposed by each fact;
- nullability requirements;
- the timezone or date-extraction convention;
- treatment of missing or anomalous temporal values;
- required referential and chronology controls.

## 9. Source-Specific Canonical Contracts

Every source implementation must maintain source-specific canonical documentation outside this platform-wide design.

At minimum, the source-specific documentation must define:

- the canonical model inventory;
- relation grains and source dependencies;
- the canonical key registry;
- identity and resolution rules;
- dimension contracts;
- fact and bridge contracts;
- anomaly-disposition implementation;
- reconciliation and join-amplification safeguards;
- publication controls;
- execution dependencies and completion criteria.

Source-specific contracts must reference their staging contracts, relationship profiles, and anomaly-disposition registers rather than duplicate detailed profiling evidence.

The initial implementation is documented in:

- [Olist Canonical Model Overview](../../docs/analytics/canonical/olist/olist_canonical_model_overview.md);
- [Olist Dimension Contracts](../../docs/analytics/canonical/olist/olist_dimension_contracts.md).

Olist fact and publication contracts will be added alongside these documents as their designs are completed.

## 10. Canonical Publication Requirements

### 10.1 Relation contracts

Every published canonical relation must document:

- its business responsibility;
- its declared grain;
- its primary key;
- its source dependencies;
- its canonical parent and child relationships;
- required and nullable attributes;
- accepted domains where applicable;
- source identifiers retained for traceability;
- anomaly dispositions affecting publication;
- blocking and non-blocking controls.

### 10.2 Blocking controls

Blocking controls protect structural integrity and publication safety.

They must cover, where applicable:

- primary-key uniqueness and non-nullability;
- required attribute availability;
- deterministic key consistency;
- accepted structural domains;
- referential compatibility;
- expected row-count preservation;
- absence of unintended join amplification;
- reconciliation of governed additive measures.

A failed blocking control prevents dependent canonical publication.

### 10.3 Non-blocking observations

Source anomalies that do not violate the structural canonical contract may remain non-blocking only when they have an approved disposition.

The canonical implementation must preserve the affected source evidence and expose any flag, status, resolved value, or conditional-exclusion behavior required by that disposition.

Non-blocking does not mean unmonitored. Applicable controls remain subject to the historical recording, baseline evaluation, ownership, and response requirements defined by ADR-013.

### 10.4 Reconciliation and amplification

Measures from independent one-to-many relationships must be reconciled and aggregated at their own governed grains before they are combined.

Canonical implementations must validate that:

- joins preserve the intended relation grain;
- parent rows are not multiplied by child relationships;
- additive measures remain attributable to their originating process;
- independent source measures are not overwritten merely to force agreement;
- material reconciliation differences remain visible and governed.

### 10.5 Publishability

A canonical relation is publishable only when:

- its implementation matches its documented contract;
- all blocking dependencies completed successfully;
- its blocking controls pass;
- required non-blocking conditions are exposed as documented;
- source traceability is preserved;
- no unreviewed grain change or join amplification is present.

## 11. Dataform Dependency and Execution Requirements

### 11.1 Dependency declaration

Canonical SQLX actions must use Dataform references for managed relation dependencies.

Dependencies must reflect the documented model graph. Canonical actions must not bypass governed staging or intermediate relations by reading equivalent Raw relations directly.

### 11.2 Execution order

The canonical graph must establish an explicit dependency order equivalent to:

```text
validated staging relations
        ↓
approved intermediate resolutions and summaries
        ↓
canonical dimensions and parent facts
        ↓
dependent facts and bridges
        ↓
canonical quality controls
```

The exact graph remains source-specific, but no relation may depend on a downstream consumer or create a circular dependency.

### 11.3 Intermediate relations

An intermediate relation may be introduced only when it provides reusable preparation required by one or more canonical models.

Every intermediate relation must declare:

- its grain;
- its purpose;
- its source dependencies;
- whether it performs resolution, deduplication, or aggregation;
- the canonical relations that consume it;
- controls preventing unintended row or measure changes.

Intermediate relations are not consumer-facing substitutes for documented canonical entities.

### 11.4 Materialization and naming

Dimensions, facts, and bridges must be materialized according to their documented refresh and consumption requirements.

Relation names must use the prefixes defined in this design. Source-specific physical-design choices such as partitioning, clustering, incremental processing, and full-refresh behavior must be recorded with the implementation contract.

### 11.5 Documentation and metadata

Canonical Dataform actions must include descriptions that identify their business responsibility and declared grain.

Published columns must use stable, documented names. A change to relation grain, canonical key composition, source namespace, measure semantics, or required field behavior constitutes a contract change and requires documentation and downstream impact review.

### 11.6 Validation sequence

Every source-specific implementation must be validated through:

1. Dataform compilation;
2. warehouse dry runs;
3. execution under the dedicated transformation identity;
4. blocking assertion execution;
5. non-blocking quality-output validation;
6. row-count and measure reconciliation;
7. resulting BigQuery schema and relation inspection.

The source-specific publication contract must record the evidence required to declare the implementation complete.