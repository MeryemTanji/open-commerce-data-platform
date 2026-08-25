# ADR-012: Staging Layer Standardization and Semantic Contracts

## Status

Accepted

## Date

2026-08-25

## Context

Mercury's ingestion architecture deliberately preserves source data rather than attempting to interpret or standardize its business meaning during ingestion.

The ingestion layer is responsible for reliably acquiring source data, validating source-specific ingestion contracts, landing immutable raw artifacts, loading them into BigQuery Raw, recording operational state and provenance, and supporting replay, recovery, and reconciliation.

BigQuery Raw therefore represents what the source provided.

For the current ingestion design, source fields are deliberately loaded using explicit `STRING` schemas rather than relying on BigQuery schema autodetection. This prevents BigQuery from implicitly interpreting source values or changing the ingestion contract based on observed data.

As a consequence, Raw may contain values such as:

- timestamps represented as `STRING`;
- monetary amounts represented as `STRING`;
- integer quantities represented as `STRING`;
- geographic coordinates represented as `STRING`;
- categorical values using source-specific casing or whitespace conventions;
- source-specific representations of missing values;
- source-specific column names.

This behavior is intentional.

Raw is the source-faithful boundary of Mercury.

However, downstream analytical modelling requires predictable semantic types, naming conventions, normalization rules, and structural guarantees.

These responsibilities must not be pushed into ingestion because doing so would couple the generic ingestion framework to source-specific analytical semantics.

They must also not be deferred to canonical models because doing so would require every downstream model to repeatedly interpret and clean source representations.

Mercury therefore requires an explicit staging boundary between Raw ingestion and canonical business modelling.

The staging layer is implemented using Dataform and establishes the semantic contract that downstream Mercury models may rely upon.

This ADR defines that contract.

---

## Decision

Mercury will implement a dedicated staging layer between BigQuery Raw and the canonical modelling layer.

The staging layer will:

1. preserve source grain;
2. convert source representations to semantic analytical data types;
3. apply Mercury naming conventions;
4. normalize structured textual values;
5. normalize source-specific missing-value representations;
6. enforce source-level structural and semantic expectations;
7. make invalid semantic conversions detectable;
8. remain source-specific in mapping but platform-standard in its conventions.

The staging layer will not:

1. join separate source entities;
2. resolve identities across source tables;
3. introduce cross-entity relationships;
4. aggregate source records into new business grains;
5. calculate analytical KPIs;
6. introduce business interpretations such as customer lifetime value, repeat-customer status, revenue definitions, delivery performance, or seller performance;
7. build canonical facts or dimensions.

The resulting architectural boundary is:

```text
SOURCE
   |
   v
INGESTION
   |
   | acquire, validate delivery, preserve
   v
BIGQUERY RAW
   |
   | source-faithful representation
   | explicit STRING schemas
   | immutable analytical landing boundary
   |
   | Dataform
   v
STAGING
   |
   | semantic typing
   | naming
   | normalization
   | source-level validation
   | source grain preserved
   v
CORE / CANONICAL
   |
   | relationships
   | entity resolution
   | conformed entities
   | business grains
   | facts and dimensions
   v
MARTS / FEATURES
   |
   | KPIs
   | analytical products
   | business logic
   | ML / AI features
   v
CONSUMPTION
```

A concise description of the layer boundaries is:

> **Raw preserves. Staging standardizes. Canonical integrates. Marts interpret.**

---

# 1. Source Grain Preservation

## STG-001 — Staging MUST preserve source grain

A staging model MUST preserve the logical grain of its Raw source.

For example:

```text
raw.orders
    |
    v
stg_orders

raw.order_items
    |
    v
stg_order_items
```

The staging transformation may change how individual values are represented, but it must not change what one source record represents.

Staging MAY:

- cast values;
- rename columns;
- trim structured strings;
- normalize casing;
- normalize missing values;
- validate source-level expectations;
- expose source-level data-quality information.

Staging MUST NOT:

- aggregate records;
- join separate source entities;
- perform cross-table entity resolution;
- silently remove legitimate business records;
- explode records into a different analytical grain;
- calculate cross-entity business metrics.

If duplicate records appear to violate the declared source grain or source key, they must be investigated and handled according to an explicit data-quality decision.

`SELECT DISTINCT` MUST NOT be used merely to hide unexplained duplicates.

---

# 2. Semantic Data Types

## STG-002 — Staging MUST convert Raw values to semantic analytical types

The physical representation of a value in Raw does not determine its staging type.

Staging types are determined by what the value means.

Mercury uses the following default semantic type conventions:

| Semantic class | Staging type |
|---|---|
| Identifier | `STRING` |
| Code | `STRING` |
| Postal code | `STRING` |
| Controlled category | `STRING` |
| Free-form text | `STRING` |
| Timestamp | `TIMESTAMP` |
| Calendar date | `DATE` |
| Monetary amount | `NUMERIC` |
| Integer / count | `INT64` |
| Decimal measurement | `NUMERIC` or `FLOAT64`, according to semantics |
| Geographic coordinate | `FLOAT64` |
| Boolean | `BOOL` |

The source representation MUST NOT be used as the sole basis for determining semantic type.

For example:

```text
Raw value: "01234"

Numerically parseable: yes
Semantic meaning: postal code

Staging type: STRING
```

Casting such a value to `INT64` would destroy significant formatting and is therefore prohibited.

---

# 3. Identifier Standardization

## STG-003 — Identifiers MUST preserve identity semantics

Identifiers SHOULD remain `STRING` unless their documented semantics explicitly require another type.

Structured identifiers SHOULD normally be normalized using boundary whitespace removal.

Conceptually:

```sql
NULLIF(TRIM(identifier), '')
```

Mercury MUST NOT automatically:

- lowercase identifiers;
- uppercase identifiers;
- convert numeric-looking identifiers to integers;
- remove leading zeros;
- otherwise rewrite identifier content without an explicit semantic contract.

The purpose of staging normalization is to standardize representation without changing identity.

---

# 4. Code Standardization

## STG-004 — Codes MUST preserve significant formatting

Code-like values MUST normally remain `STRING`.

Examples include:

- postal codes;
- state or province codes;
- country codes;
- product codes;
- campaign codes;
- other categorical identifiers where formatting is meaningful.

Leading zeros and other significant formatting MUST be preserved.

Casing rules MAY be applied where the semantic class defines a canonical representation.

---

# 5. Structured Whitespace Normalization

## STG-005 — Structured textual attributes MUST remove surrounding whitespace

Structured textual attributes SHOULD use:

```sql
TRIM(value)
```

where surrounding whitespace has no semantic meaning.

Examples include:

- identifiers;
- codes;
- cities;
- states;
- controlled categories;
- statuses;
- structured names.

Whitespace normalization MUST NOT be applied blindly to fields where whitespace may be semantically meaningful.

Free-form textual content is governed separately by STG-008.

---

# 6. Geographic Standardization

## STG-006 — Geographic attributes MUST follow Mercury casing conventions

Mercury defines the following default representation for geographic attributes:

```text
city / locality
    -> LOWER(TRIM(value))

state / region code
    -> UPPER(TRIM(value))
```

Equivalent geographic attributes from different sources SHOULD therefore produce the same normalized representation at the staging boundary.

For example:

```text
" Amsterdam "
"AMSTERDAM"
"Amsterdam"

        ->

"amsterdam"
```

and:

```text
"sp"
"Sp"
" SP "

        ->

"SP"
```

These rules MUST be applied by staging even when the current source already conforms.

Source cleanliness is not considered a substitute for a staging contract.

---

# 7. Controlled Categorical Values

## STG-007 — Controlled categories MUST use a consistent representation

Controlled categorical fields SHOULD be normalized to a predictable representation.

Unless a domain-specific contract requires otherwise, Mercury's default convention is:

```sql
LOWER(TRIM(value))
```

For example:

```text
"Delivered"
"DELIVERED"
" delivered "

        ->

"delivered"
```

This convention is appropriate for fields such as statuses, types, and other controlled source categories.

A source-specific staging contract MAY define a different canonical representation where required by the domain.

Normalization MUST NOT invent new business categories or merge semantically distinct source values without an explicit modelling decision.

---

# 8. Free-Form Text

## STG-008 — Free-form content MUST be preserved conservatively

Free-form source content MUST NOT be aggressively standardized.

Examples include:

- review messages;
- review titles;
- descriptions;
- comments;
- user-generated text.

Mercury MUST NOT automatically lowercase, uppercase, tokenize, rewrite, or otherwise semantically alter free-form content in staging.

Where appropriate, source-specific missing-value normalization MAY be applied.

Boundary whitespace MAY be normalized only where doing so does not alter meaningful content.

The original Raw representation remains available for auditability and future processing.

This conservative approach preserves the usefulness of free-form content for later applications such as NLP, sentiment analysis, classification, or AI features.

---

# 9. Null and Missing-Value Standardization

## STG-009 — Semantic absence MUST be represented as SQL NULL

Sources may represent missing values using values such as:

```text
""
"NULL"
"null"
"N/A"
```

or other source-specific conventions.

Where a source contract establishes that such a value represents semantic absence, staging MUST normalize it to SQL `NULL`.

Mercury MUST NOT maintain one universal list of strings that are blindly converted to `NULL` for every source.

For example, the literal text `"N/A"` may be a legitimate value in one source and a missing-value marker in another.

Null normalization therefore combines:

```text
Mercury null-handling principle
              +
source-specific staging contract
              |
              v
normalized SQL NULL
```

Empty structured values SHOULD normally become `NULL` where an empty value has no valid domain meaning.

---

# 10. Naming Conventions

## STG-010 — Staging SHOULD conform source fields to Mercury naming conventions

Staging column names SHOULD be explicit, descriptive, and consistent across Mercury.

Default conventions include:

```text
identifier        -> *_id
timestamp         -> *_timestamp
calendar date     -> *_date
boolean           -> is_* / has_*
monetary amount   -> *_amount where this improves semantic clarity
count             -> *_count
code              -> *_code where appropriate
```

Mercury explicitly uses `*_timestamp` rather than abbreviated conventions such as `*_at`.

The term `timestamp` is preferred because it explicitly communicates the semantic and physical nature of the field and is broadly understandable across tools and engineering contexts.

Examples:

```text
order_purchase_timestamp
order_approved_timestamp
order_delivered_timestamp
```

rather than:

```text
order_purchased_at
order_approved_at
order_delivered_at
```

Existing source column names SHOULD be retained when they already conform to Mercury conventions and accurately communicate their meaning.

Staging MUST avoid gratuitous renaming.

A rename SHOULD provide one or more of:

- clearer semantics;
- consistency with Mercury conventions;
- consistency across equivalent concepts from multiple sources;
- removal of source-specific ambiguity.

---

# 11. Semantic Conversion Validity

## STG-011 — Invalid non-null source values MUST NOT silently disappear during casting

Semantic conversion failures are data-quality events.

For example:

```text
Raw:

price = "banana"
```

must not silently become:

```text
Staging:

price = NULL
```

without Mercury being able to distinguish the conversion failure from a legitimately missing source value.

Using:

```sql
SAFE_CAST(price AS NUMERIC)
```

without corresponding validation is therefore insufficient.

Mercury staging MUST distinguish between:

```text
source value legitimately absent
```

and:

```text
source value present but semantically invalid
```

The implementation MAY use:

- Dataform assertions;
- dedicated quality models;
- explicit validity flags;
- rejected-record models;
- another mechanism consistent with this ADR;
- or a combination of these approaches.

The exact implementation mechanism may vary by source and severity, but malformed non-null values MUST remain detectable.

Raw remains the authoritative source-faithful representation and MUST remain available for investigation.

---

# 12. Source-Level Structural Contracts

## STG-012 — Every staging model MUST define source-level expectations

Each staging model MUST establish the structural and semantic expectations required for downstream models to trust it.

Depending on the source entity, these expectations MAY include:

- required fields;
- source-key uniqueness;
- semantic type validity;
- accepted categorical values;
- numeric ranges;
- timestamp or date validity;
- code formats;
- required source grain.

For example:

```text
stg_orders.order_id is required
stg_orders.order_id is unique
stg_order_items.price must be a valid monetary value
stg_reviews.review_score must conform to its defined domain
```

These validations concern the integrity of the individual source entity.

Cross-entity referential integrity is outside the staging responsibility.

For example:

```text
Every order_id is unique within stg_orders
```

may be a staging assertion.

However:

```text
Every stg_orders.customer_id exists in stg_customers
```

requires a relationship between separate source entities and therefore belongs after the staging boundary.

---

# 13. No Cross-Entity Business Interpretation

## STG-013 — Staging MUST NOT introduce analytical business concepts

Staging exists to standardize source representation.

It MUST NOT introduce business concepts requiring relationships, aggregation, or analytical interpretation.

Examples of logic prohibited from staging include:

```text
is_repeat_customer
is_late_delivery
customer_lifetime_value
order_revenue
seller_performance
customer_segment
retention_status
lifetime_order_count
```

Such concepts belong in canonical, intermediate, feature, or mart layers according to their grain and purpose.

---

# 14. Source-Specific Mapping, Platform-Wide Standards

Mercury is designed to ingest heterogeneous sources with different:

- field names;
- schemas;
- data representations;
- source systems;
- delivery mechanisms;
- business terminology.

The staging implementation for a source therefore contains source-specific mappings.

For example:

```text
Source A
--------
transaction_number
transaction_time
gross_value

Source B
--------
order_id
created_timestamp
amount

        |
        v

source-specific staging mappings

        |
        v

Mercury conventions
--------
identifier -> STRING
timestamp  -> TIMESTAMP
money      -> NUMERIC
```

The mappings are source-specific.

The conventions are platform-wide.

This separation ensures that Mercury can support new sources without requiring the ingestion framework or downstream canonical models to adopt the source's physical representation.

---

# 15. Relationship to the Ingestion Layer

The staging architecture deliberately complements the ingestion architecture.

Ingestion answers:

> What exactly did the source provide, and can Mercury reliably preserve, replay, recover, and trace that delivery?

Staging answers:

> What do those source values mean, and how must they be represented for downstream analytical use?

Canonical modelling answers:

> How do those standardized source entities relate to Mercury's business concepts?

This separation prevents analytical assumptions from leaking into generic ingestion infrastructure.

A future source with completely different fields SHOULD require source-specific connector/schema configuration and source-specific staging mappings, but SHOULD NOT require changes to generic Mercury storage, replay, recovery, provenance, or reconciliation behavior solely because its business columns differ.

---

# 16. Relationship to Terraform and Dataform

Infrastructure and transformation responsibilities remain separate.

Terraform is responsible for infrastructure such as:

- BigQuery datasets;
- GCS buckets;
- IAM;
- service accounts;
- Dataform infrastructure and configuration where applicable;
- other required GCP resources.

Dataform is responsible for analytical transformations, including:

- staging models;
- semantic casting;
- normalization;
- assertions;
- canonical transformations;
- downstream analytical models.

Terraform MUST NOT be used to implement source-value standardization logic.

Dataform is the transformation boundary between BigQuery Raw and downstream analytical models.

---

# 17. Olist as the First Implementation

Olist is Mercury's first complete source implementation and will be used to validate this staging architecture.

However, Olist's current source characteristics MUST NOT define Mercury's general staging standards.

For example, if Olist currently provides city names in lowercase and state codes in uppercase, Mercury will still explicitly apply its geographic normalization rules.

The guarantee must come from the staging contract, not from accidental source conformity.

Olist-specific findings such as:

- source column names;
- observed nullability;
- observed category values;
- castability;
- source-key behavior;
- field-specific anomalies;
- source-specific missing-value conventions;

will be documented in the Olist staging contracts rather than in this ADR.

---

# 18. Staging Contract Development Process

A new source SHOULD pass through the following process before its staging models are considered complete:

```text
Define / apply Mercury Staging Standard
                 |
                 v
Classify source Raw columns
                 |
                 v
Propose semantic staging contracts
                 |
                 v
Profile Raw values against those contracts
                 |
                 v
Resolve anomalies and source-specific edge cases
                 |
                 v
Finalize source staging contracts
                 |
                 v
Implement Dataform staging models
                 |
                 v
Implement and execute staging assertions
                 |
                 v
STAGING GATE PASSES
                 |
                 v
Relationship exploration
                 |
                 v
Canonical modelling
```

Profiling MUST validate the proposed contract rather than allowing the current source representation to implicitly define Mercury's standards.

---

# 19. Staging Completion Gate

A source entity MUST NOT be treated as canonical-model-ready until its staging contract has been implemented and validated.

At minimum, the staging gate requires:

1. every Raw business column has been classified;
2. intended semantic types are documented;
3. required normalization rules are documented;
4. source-specific null behavior is understood;
5. semantic casts have been profiled;
6. malformed non-null values are detectable;
7. source grain is understood and preserved;
8. required source keys and structural expectations are validated;
9. the Dataform staging model implements the agreed contract;
10. staging assertions pass or known exceptions are explicitly documented.

Relationship exploration and canonical modelling SHOULD use staging models rather than Raw tables once the relevant staging contracts exist.

---

## Consequences

### Positive

- Raw remains immutable and source-faithful.
- Ingestion remains decoupled from analytical semantics.
- Downstream models receive predictable semantic data types.
- Equivalent concepts from heterogeneous sources can follow consistent conventions.
- Data-quality failures become explicit rather than silently hidden by casting.
- Canonical models do not need to repeatedly clean source representations.
- Source-specific mappings remain isolated from platform-wide conventions.
- New data sources can adopt Mercury standards without changing Raw source fidelity.
- Dataform becomes a clear semantic boundary in the architecture.
- The distinction between standardization and business modelling remains explicit.
- Source profiling becomes contract-driven rather than ad hoc.

### Negative / Trade-offs

- Staging models require explicit source-specific contracts.
- New sources require profiling before they can safely enter canonical modelling.
- Some transformations will appear redundant when a source already conforms to Mercury standards.
- Explicit semantic validation introduces additional Dataform models, assertions, or quality logic.
- Raw-to-staging development requires more upfront work than directly querying Raw.

These costs are accepted because Mercury prioritizes reliability, explainability, reusability, and explicit contracts over implicit assumptions.

---

## Alternatives Considered

### 1. Apply semantic typing during ingestion

Rejected.

This would couple generic ingestion behavior to source-specific analytical semantics and weaken the source-faithful Raw boundary.

It would also require ingestion components to decide what business fields mean before the data reaches the analytical transformation layer.

### 2. Use BigQuery schema autodetection

Rejected.

Schema autodetection can infer types from observed values and therefore makes the Raw ingestion contract dependent on the contents of a particular delivery.

Mercury deliberately uses explicit Raw schemas to keep ingestion deterministic.

### 3. Keep Raw strings throughout downstream modelling

Rejected.

This would duplicate casting and normalization logic throughout canonical models and marts and would provide no trusted semantic boundary.

### 4. Perform standardization directly in canonical models

Rejected.

This would mix source cleanup with entity integration and business modelling, making canonical transformations harder to understand, test, and reuse.

### 5. Standardize only fields that are currently inconsistent

Rejected.

A source's current cleanliness must not determine Mercury's guarantees.

For example, if a source currently provides all state codes in uppercase, downstream consumers should still be able to rely on staging enforcing uppercase rather than relying on the source continuing to behave that way.

---

## Implementation Notes

This ADR defines architectural requirements rather than the complete implementation of every staging-quality mechanism.

The following details will be determined during the Olist staging implementation:

- exact Dataform project structure;
- reusable helper patterns where appropriate;
- exact assertion strategy;
- whether invalid semantic values require dedicated quality models, explicit flags, failing assertions, or combinations of these mechanisms;
- source-specific missing-value mappings;
- source-specific accepted categorical domains;
- exact Olist staging column names;
- exact Olist semantic types;
- documented exceptions discovered during profiling.

These implementation decisions MUST remain consistent with the standards defined by this ADR.

---

## Initial Implementation Sequence

ADR-012 will first be applied to the eight Olist Raw source entities:

1. customers;
2. geolocations;
3. orders;
4. order_items;
5. payments;
6. products;
7. reviews;
8. sellers.

For each entity Mercury will:

1. classify every Raw column by semantic class;
2. propose its staging name and semantic type;
3. define applicable Mercury standardization rules;
4. profile existing Raw values;
5. identify source-specific edge cases;
6. finalize the source-to-staging contract;
7. implement the Dataform model;
8. implement the required assertions.

Only after the Olist staging gate passes will Mercury resume cross-entity relationship exploration and canonical modelling.

---

## Decision Summary

Mercury establishes Dataform staging as the explicit semantic standardization boundary between source-faithful BigQuery Raw data and canonical analytical modelling.

The governing architecture is:

```text
RAW
preserves what the source provided

        |
        v

STAGING
standardizes what those values mean

        |
        v

CANONICAL
integrates how those entities relate

        |
        v

MARTS / FEATURES
interpret those relationships for analytical use
```

This boundary is source-agnostic.

Olist is the first implementation of the contract, not the definition of the contract.