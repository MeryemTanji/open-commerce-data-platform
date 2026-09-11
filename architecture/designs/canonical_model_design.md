# Mercury Canonical Model Design

## Status

Draft

## Date

2026-09-11

## Purpose

This document defines the logical and implementation design for Mercury's canonical business model.

The canonical layer transforms validated staging relations into stable, reusable business entities that are independent of individual source-system schemas. It provides the governed foundation from which downstream data products, analytical models, dashboards, and applications can be built.

This design translates Mercury's architectural decisions, staging contracts, anomaly dispositions, and relationship findings into explicit canonical model boundaries.

## Governing Decisions

This design implements the following architectural decisions:

- [ADR-001: Adopt a Layered Data Platform Architecture](../decisions/ADR-001-Adopt%20a%20Layered%20Data%20Platform%20Architecture.md)
- [ADR-003: Adopt a Canonical Business Model](../decisions/ADR-003-Adopt%20a%20Canonical%20Business%20Model.md)
- [ADR-004: Publish Reusable Data Products](../decisions/ADR-004-Publish%20Reusable%20Data%20Products.md)
- [ADR-011: Data Security, Privacy, and Data-Leak Prevention](../decisions/ADR-011-Data%20Security,%20Privacy,%20and%20Data-Leak%20Prevention.md)
- [ADR-012: Staging Layer Standardization and Semantic Contracts](../decisions/ADR-012-Staging%20Layer%20Standardization%20and%20Semantic%20Contracts.md)
- [ADR-013: Data Quality Anomaly Disposition and Monitoring Contract](../decisions/ADR-013-Data%20Quality%20Anomaly%20Disposition%20and%20Monitoring%20Contract.md)

The first implementation is informed by the validated [Olist Relationship Profile](../../docs/analytics/relationships/olist_relationship_profile.md) and [Olist Anomaly Disposition Register](../../docs/analytics/staging/olist_anomaly_disposition.md).

## 1. Scope

This document defines:

- the responsibility and boundary of the canonical layer;
- the canonical dataset ownership model;
- permitted canonical relation types;
- model grains, keys, and relationships;
- source-to-canonical dependency rules;
- identity-resolution requirements;
- anomaly-disposition implementation;
- join-amplification safeguards;
- canonical quality and publication controls;
- Dataform dependency and execution requirements;
- the initial Olist canonical model direction.

This document does not define:

- Raw or staging transformation contracts;
- source-specific profiling evidence;
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
- approved preparation relations;
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

Orders, order items, payments, and reviews represent different business processes and must remain independently modelled at their natural grains.

They must not be joined into one detailed relation merely because they share `order_id`.

### 5.3 Aggregate independently before combining

When multiple one-to-many child relations contribute measures to a parent-grain model, each child must first be aggregated independently to the parent key.

This prevents multiplication of item, payment, and review measures.

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

## 7. Initial Canonical Model Inventory

The first canonical implementation uses the validated Olist staging relations while expressing source-independent business concepts.

### 7.1 Dimensions

| Relation | Grain | Business responsibility | Primary staging input |
| --- | --- | --- | --- |
| `dim_customer` | One row per `customer_unique_id` | Represents persistent customer identity independently of order-specific customer records | `stg_customers` |
| `dim_product` | One row per `product_id` | Represents reusable product and catalogue attributes | `stg_products` |
| `dim_seller` | One row per `seller_id` | Represents sellers and their governed geographic attributes | `stg_sellers` |
| `dim_date` | One row per calendar date | Provides reusable calendar attributes and role-playing date relationships | Generated from canonical date boundaries |
| `dim_location` | One row per ZIP-code prefix | Provides deterministically resolved geographic attributes | `stg_geolocations` |

### 7.2 Facts

| Relation | Grain | Business responsibility | Primary staging input |
| --- | --- | --- | --- |
| `fct_orders` | One row per `order_id` | Represents the order lifecycle and independently aggregated order-level measures | `stg_orders` |
| `fct_order_items` | One row per `(order_id, order_item_id)` | Represents individual product–seller line items and their commercial values | `stg_order_items` |
| `fct_payments` | One row per `(order_id, payment_sequential)` | Represents individual payment events associated with an order | `stg_payments` |
| `fct_reviews` | One row per `review_id` | Represents distinct review payloads and feedback chronology | `stg_reviews` |

### 7.3 Bridges

| Relation | Grain | Business responsibility | Primary staging input |
| --- | --- | --- | --- |
| `bridge_order_reviews` | One row per `(order_id, review_id)` | Preserves every validated association between orders and reviews | `stg_reviews` |

### 7.4 Intermediate Relations

The initial implementation is expected to require the following internal relations:

| Relation | Grain | Responsibility |
| --- | --- | --- |
| `int_geolocation_resolution` | One row per ZIP-code prefix | Resolves repeated geolocation observations into governed location attributes |
| `int_order_item_summary` | One row per `order_id` | Aggregates item counts and monetary measures before joining to order grain |
| `int_order_payment_summary` | One row per `order_id` | Aggregates payment counts and values before joining to order grain |
| `int_order_review_summary` | One row per `order_id` | Aggregates review-association counts without selecting an arbitrary review |

Intermediate relation names may be refined during their individual implementation contracts, but their declared grains and responsibilities must remain explicit.

## 8. Initial Relationship Structure

The initial canonical relationships are:

| Parent relation | Child or associated relation | Relationship |
| --- | --- | --- |
| `dim_customer` | `fct_orders` | One persistent customer to zero or more orders |
| `dim_location` | `fct_orders` | One resolved location to zero or more order-context customer addresses |
| `dim_product` | `fct_order_items` | One product to zero or more order items |
| `dim_seller` | `fct_order_items` | One seller to zero or more order items |
| `fct_orders` | `fct_order_items` | One order to zero or more order items |
| `fct_orders` | `fct_payments` | One order to zero or more payment events |
| `fct_orders` | `bridge_order_reviews` | One order to zero or more review associations |
| `fct_reviews` | `bridge_order_reviews` | One review to one or more order associations |
| `dim_date` | Canonical facts | One calendar date to zero or more fact events through role-specific date keys |

Canonical relationships do not imply that all relations may be joined simultaneously at their detailed grains.

Order items, payments, and review associations are independent one-to-many relationships from orders. Any order-grain model that uses their measures must aggregate each relation independently to `order_id` before combining them.

## 9. Excluded Initial Relations

The initial canonical model will not create a separate delivery fact.

The available delivery attributes describe the lifecycle of an order but do not establish an independently identified delivery entity or a validated one-to-many delivery grain. Delivery timestamps and derived durations therefore remain part of `fct_orders`.

A separate delivery relation may be introduced later if Mercury integrates a fulfilment source containing independently identified shipments, delivery attempts, carriers, or packages.

The initial model will also not create:

- a single denormalised order-wide table containing detailed items, payments, and reviews;
- a permanent seller attribute on `dim_product`;
- a single current-location attribute selected arbitrarily for `dim_customer`;
- dashboard-specific aggregates;
- customer-scoring or machine-learning feature tables.

Those structures either violate validated relationship behavior or belong in downstream data products.

## 10. Canonical Key Strategy

### 10.1 Canonical and source keys

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

### 10.2 Deterministic generation

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

The initial implementation will generate a hexadecimal SHA-256 value from a consistently serialized representation of those components.

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

### 10.3 Generation requirements

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

### 10.4 Non-source-derived keys

Not every canonical key requires a source namespace.

Governed reference entities may use stable business-domain keys when their identity is independent of a source system.

The initial exceptions are:

| Relation | Stable key |
| --- | --- |
| `dim_date` | Calendar date |
| `dim_location` | Country code and postal-code prefix |

A Brazilian ZIP-code prefix is not globally unique without geographic context. The location key must therefore include:

```text
country_code
postal_code_prefix
```

### 10.5 Collision and consistency controls

Every relation using generated canonical keys must enforce:

- canonical-key non-nullability;
- canonical-key uniqueness at the declared grain;
- consistency between each canonical key and its source components;
- absence of one canonical key mapping to multiple source-identifier combinations;
- referential compatibility between parent and child keys.

A uniqueness assertion remains required even when SHA-256 collision probability is negligible. The assertion also detects incorrect input composition, serialization defects, and unintended grain changes.

## 11. Canonical Key Registry

### 11.1 Primary keys

| Relation | Primary key | Generation basis |
| --- | --- | --- |
| `dim_customer` | `customer_key` | `v1`, customer entity, source namespace, `customer_unique_id` |
| `dim_product` | `product_key` | `v1`, product entity, source namespace, `product_id` |
| `dim_seller` | `seller_key` | `v1`, seller entity, source namespace, `seller_id` |
| `dim_date` | `date_key` | Calendar date |
| `dim_location` | `location_key` | `v1`, location entity, country code, postal-code prefix |
| `fct_orders` | `order_key` | `v1`, order entity, source namespace, `order_id` |
| `fct_order_items` | `order_item_key` | `v1`, order-item entity, source namespace, `order_id`, `order_item_id` |
| `fct_payments` | `payment_key` | `v1`, payment entity, source namespace, `order_id`, `payment_sequential` |
| `fct_reviews` | `review_key` | `v1`, review entity, source namespace, `review_id` |
| `bridge_order_reviews` | (`order_key`, `review_key`) | Canonical order and review keys |

The bridge uses (`order_key`, `review_key`) as its composite primary key and does not require a generated surrogate key.

### 11.2 Preserved source identifiers

| Relation | Preserved source identifiers |
| --- | --- |
| `dim_customer` | `source_customer_id` |
| `dim_product` | `source_product_id` |
| `dim_seller` | `source_seller_id` |
| `dim_date` | Not applicable |
| `dim_location` | `source_postal_code_prefix` |
| `fct_orders` | `source_order_id`, `source_customer_record_id` |
| `fct_order_items` | `source_order_id`, `source_order_item_id` |
| `fct_payments` | `source_order_id`, `source_payment_sequence` |
| `fct_reviews` | `source_review_id` |
| `bridge_order_reviews` | `source_order_id`, `source_review_id` |

### 11.3 Foreign-key propagation

Canonical foreign keys must be generated or obtained through the same governed key logic as their parent relation.

The initial foreign-key relationships are:

| Child relation | Foreign key | Parent relation |
| --- | --- | --- |
| `fct_orders` | `customer_key` | `dim_customer` |
| `fct_orders` | `customer_location_key` | `dim_location` |
| `fct_orders` | Role-specific lifecycle date keys | `dim_date` |
| `fct_order_items` | `order_key` | `fct_orders` |
| `fct_order_items` | `product_key` | `dim_product` |
| `fct_order_items` | `seller_key` | `dim_seller` |
| `fct_order_items` | `shipping_limit_date_key` | `dim_date` |
| `fct_payments` | `order_key` | `fct_orders` |
| `fct_reviews` | `review_creation_date_key` | `dim_date` |
| `fct_reviews` | `review_answer_date_key` | `dim_date` |
| `bridge_order_reviews` | `order_key` | `fct_orders` |
| `bridge_order_reviews` | `review_key` | `fct_reviews` |
| `dim_seller` | `location_key` | `dim_location` |

Order lifecycle dates and timestamps will use role-specific date keys referencing `dim_date`. Their exact column contracts will be defined with `fct_orders`.

Timestamps remain available on their facts when time-of-day precision is analytically relevant. A date key supplements rather than replaces its corresponding timestamp.

### 11.4 Source namespace

The first implementation uses:

```text
source_namespace = "olist"
```

The source namespace identifies the Olist source instance represented by the current development data.

A future source must receive its own stable namespace. Reusing a namespace for a materially different source instance is prohibited because it could cause unrelated source identifiers to generate identical canonical keys.

Cross-source identity resolution must be implemented through an explicit governed mapping process. It must not be achieved by assigning different systems the same namespace or by assuming matching source identifiers represent the same business entity.