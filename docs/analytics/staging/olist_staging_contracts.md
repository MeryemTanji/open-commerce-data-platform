# Olist Staging Contract

**Project:** Mercury — Open Commerce Data Platform  
**Layer:** Analytics Engineering — Staging  
**Source:** Olist Brazilian E-Commerce Dataset  
**Status:** Implemented and validated
**Governing ADR:** ADR-012 — Staging Layer Standardization and Semantic Contracts

---

## 1. Purpose

This document defines the source-specific staging contract for the Olist implementation of Mercury.

ADR-012 defines the reusable Mercury staging standard. This document applies that standard to the Olist Raw datasets and records the decisions established through source profiling before Dataform implementation.

The purpose of this contract is to define, for every Olist staging model:

- source grain;
- source keys;
- target staging column names;
- semantic data types;
- normalization rules;
- nullability;
- domain constraints;
- blocking structural validation;
- known source-quality observations;
- non-blocking anomaly handling.

This document is the implementation specification for the Olist staging layer.

It does **not** redefine the general Mercury staging architecture. Reusable staging principles belong in ADR-012.

Future source systems should receive their own source-specific staging contracts while continuing to follow ADR-012.

---

# 2. Position of Staging in Mercury

Mercury deliberately preserves source data faithfully in the Raw layer.

Raw ingestion does not attempt to impose analytical semantics on source values.

The processing flow is:

```text
SOURCE SYSTEM
      │
      ▼
INGESTION CONNECTOR
      │
      ▼
IMMUTABLE RAW
source-faithful representation
all source fields preserved
      │
      ▼
STAGING STANDARDIZATION
names
types
null representation
casing
whitespace
semantic normalization
      │
      ▼
STRUCTURAL CONTRACT VALIDATION
keys
required fields
cast validity
safe semantic domains
      │
      ▼
NON-BLOCKING QUALITY SURFACING
source anomalies
lifecycle inconsistencies
unusual but interpretable values
      │
      ▼
CANONICAL MODELLING
relationships
shared business entities
business semantics
      │
      ▼
MARTS / FEATURES / DATA PRODUCTS
```

The Raw layer answers:

> What did the source deliver?

The staging layer answers:

> What does each source field structurally and semantically represent?

The canonical layer later answers:

> How do these standardized source entities relate to Mercury's business concepts?

---

# 3. Staging Responsibilities

The Olist staging layer has three distinct responsibilities.

## 3.1 Standardization

Standardization converts source representation into a stable analytical representation.

Examples include:

- trimming identifiers;
- converting empty strings to `NULL`;
- normalizing city casing;
- normalizing state-code casing;
- converting numeric strings into numeric types;
- converting timestamp strings into `TIMESTAMP`;
- correcting misleading or misspelled source column names.

Standardization may change representation.

It must not invent business meaning.

---

## 3.2 Blocking Structural Validation

Blocking structural validation determines whether Mercury can trust the staged structure.

Examples include:

- required identifiers becoming `NULL`;
- duplicate declared source keys;
- non-empty numeric values that cannot be parsed;
- non-empty timestamp values that cannot be parsed;
- values violating a safe semantic domain.

These conditions mean the staging contract itself cannot be guaranteed.

Such failures may block the affected staging build.

---

## 3.3 Non-Blocking Quality Surfacing

Some source records are structurally interpretable but contain suspicious or internally inconsistent information.

Examples include:

- a carrier timestamp occurring before an order purchase;
- a delivered order missing a delivery timestamp;
- a zero product weight;
- a zero-installment credit-card payment.

Mercury must not silently repair such records unless an explicit and justified source rule exists.

Instead:

```text
PRESERVE SOURCE VALUE
        │
        ▼
STANDARDIZE REPRESENTATION
        │
        ▼
FLAG QUALITY CONDITION
        │
        ▼
PIPELINE CONTINUES
```

The staging layer distinguishes between:

> Mercury cannot understand the value.

and:

> Mercury understands the value, but the value looks suspicious.

Only the former is inherently a structural staging failure.

---

# 4. Common Mercury Staging Transformations

The following patterns implement ADR-012 for Olist.

---

## 4.1 Identifiers

Identifiers remain `STRING`.

They are trimmed and empty strings become `NULL`.

```sql
NULLIF(TRIM(value), '')
```

Identifier casing is not modified unless a source-specific contract explicitly requires it.

---

## 4.2 Postal Codes

Postal codes remain `STRING`.

```sql
NULLIF(TRIM(value), '')
```

They must never be converted to integers merely because they contain digits.

Leading zeros are meaningful and must be preserved.

For the Olist ZIP-prefix fields, the expected representation is:

```text
^\d{5}$
```

---

## 4.3 Cities

Cities are standardized to lowercase.

```sql
NULLIF(
  LOWER(TRIM(value)),
  ''
)
```

This guarantee is applied even when the current source already conforms.

---

## 4.4 State Codes

State codes are standardized to uppercase.

```sql
NULLIF(
  UPPER(TRIM(value)),
  ''
)
```

For Olist, the expected representation is:

```text
^[A-Z]{2}$
```

---

## 4.5 Controlled Categories

Controlled categorical values are standardized to lowercase unless a source-specific semantic reason requires otherwise.

```sql
NULLIF(
  LOWER(TRIM(value)),
  ''
)
```

Examples include:

- `order_status`;
- `payment_type`;
- `product_category_name`.

Observed source values must not automatically become permanent Mercury-wide allowed-value lists.

Observed domains and contractual domains are different concepts.

---

## 4.6 Free-Form Text

User-authored free-form text is trimmed at its boundaries and whitespace-only strings become `NULL`.

```sql
NULLIF(TRIM(value), '')
```

Mercury must not lowercase or otherwise rewrite user-authored text during staging.

This applies to:

- `review_comment_title`;
- `review_comment_message`.

---

## 4.7 Integers

Integer-semantic source fields use safe conversion.

```sql
SAFE_CAST(
  NULLIF(TRIM(value), '')
  AS INT64
)
```

A non-empty Raw value that becomes `NULL` because conversion failed must be detectable as a structural contract violation.

---

## 4.8 Monetary and Decimal Measurements

Monetary values and decimal measurements use `NUMERIC`.

```sql
SAFE_CAST(
  NULLIF(TRIM(value), '')
  AS NUMERIC
)
```

Examples include:

- product dimensions;
- product weight;
- price;
- freight value;
- payment value.

---

## 4.9 Geographic Coordinates

Coordinates use `FLOAT64`.

```sql
SAFE_CAST(
  NULLIF(TRIM(value), '')
  AS FLOAT64
)
```

Latitude must fall within:

```text
-90 <= latitude <= 90
```

Longitude must fall within:

```text
-180 <= longitude <= 180
```

---

## 4.10 Timestamps

Timestamp-semantic source values use:

```sql
SAFE_CAST(
  NULLIF(TRIM(value), '')
  AS TIMESTAMP
)
```

Source column suffixes such as `_date` do not determine the target semantic type.

Profiling determines whether the source represents a calendar date or a moment in time.

---

## 4.11 Dates from Timestamp-Like Source Values

Some source fields contain timestamp-like representations but semantically represent calendar dates.

These are normalized using the parsed timestamp and then reduced to a `DATE`.

```sql
DATE(
  SAFE_CAST(
    NULLIF(TRIM(value), '')
    AS TIMESTAMP
  )
)
```

This pattern is used for:

- `order_estimated_delivery_date`;
- `review_creation_date`.

---

# 5. Olist Staging Model Inventory

The Olist implementation contains eight staging models.

```text
stg_customers
stg_sellers
stg_geolocations
stg_products
stg_orders
stg_order_items
stg_payments
stg_reviews
```

Each model preserves the source entity's grain unless explicitly documented otherwise.

---

# 6. `stg_customers`

## Grain

```text
one row per customer_id
```

## Source Key

```text
customer_id
```

`customer_id` is required and unique.

`customer_unique_id` is required but is **not** unique and must not be treated as the staging row key.

## Column Contract

| Raw column | Staging column | Type | Required | Transformation |
|---|---|---:|---:|---|
| `customer_id` | `customer_id` | STRING | Yes | trim, empty → NULL |
| `customer_unique_id` | `customer_unique_id` | STRING | Yes | trim, empty → NULL |
| `customer_zip_code_prefix` | `customer_zip_code_prefix` | STRING | Yes | trim, preserve leading zeros |
| `customer_city` | `customer_city` | STRING | Yes | trim, lowercase |
| `customer_state` | `customer_state` | STRING | Yes | trim, uppercase |

## Structural Contract

- `customer_id` must not be null.
- `customer_id` must be unique.
- `customer_unique_id` must not be null.
- `customer_zip_code_prefix` must not be null.
- `customer_city` must not be null.
- `customer_state` must not be null.
- ZIP prefix must match `^\d{5}$`.
- state code must match `^[A-Z]{2}$`.

## Important Source Observation

`customer_unique_id` represents a different identity concept from `customer_id`.

Its relationship to customer entities will be evaluated during canonical modelling rather than altered in staging.

---

# 7. `stg_sellers`

## Grain

```text
one row per seller_id
```

## Source Key

```text
seller_id
```

## Column Contract

| Raw column | Staging column | Type | Required | Transformation |
|---|---|---:|---:|---|
| `seller_id` | `seller_id` | STRING | Yes | trim, empty → NULL |
| `seller_zip_code_prefix` | `seller_zip_code_prefix` | STRING | Yes | trim, preserve leading zeros |
| `seller_city` | `seller_city` | STRING | Yes | trim, lowercase |
| `seller_state` | `seller_state` | STRING | Yes | trim, uppercase |

## Structural Contract

- `seller_id` must not be null.
- `seller_id` must be unique.
- ZIP prefix must not be null and must match `^\d{5}$`.
- city must not be null.
- state must not be null and must match `^[A-Z]{2}$`.

---

# 8. `stg_geolocations`

## Grain

```text
one row per source geolocation observation
```

No unique source key has been established.

`geolocation_zip_code_prefix` is **not** unique.

## Column Contract

| Raw column | Staging column | Type | Required | Transformation |
|---|---|---:|---:|---|
| `geolocation_zip_code_prefix` | `geolocation_zip_code_prefix` | STRING | Yes | trim, preserve leading zeros |
| `geolocation_lat` | `geolocation_lat` | FLOAT64 | Yes | safe semantic cast |
| `geolocation_lng` | `geolocation_lng` | FLOAT64 | Yes | safe semantic cast |
| `geolocation_city` | `geolocation_city` | STRING | Yes | trim, lowercase |
| `geolocation_state` | `geolocation_state` | STRING | Yes | trim, uppercase |

## Structural Contract

- all fields are required;
- ZIP prefix must match `^\d{5}$`;
- state code must match `^[A-Z]{2}$`;
- non-empty latitude values must convert successfully to `FLOAT64`;
- non-empty longitude values must convert successfully to `FLOAT64`;
- latitude must fall within `[-90, 90]`;
- longitude must fall within `[-180, 180]`.

## Known Source Characteristic

The Raw Olist geolocation dataset contains:

```text
1,000,163 total source observations
738,332 distinct normalized full rows
261,831 exact duplicate observations
```

These duplicates must **not** be removed in staging.

Staging preserves source grain.

Any future decision to create a canonical geography representation, representative coordinate, ZIP-level aggregation, or deduplicated geography entity belongs downstream.

---

# 9. `stg_products`

## Grain

```text
one row per product_id
```

## Source Key

```text
product_id
```

## Column Contract

| Raw column | Staging column | Type | Required | Transformation |
|---|---|---:|---:|---|
| `product_id` | `product_id` | STRING | Yes | trim, empty → NULL |
| `product_category_name` | `product_category_name` | STRING | No | trim, lowercase |
| `product_name_lenght` | `product_name_length` | INT64 | No | safe semantic cast |
| `product_description_lenght` | `product_description_length` | INT64 | No | safe semantic cast |
| `product_photos_qty` | `product_photos_count` | INT64 | No | safe semantic cast |
| `product_weight_g` | `product_weight_g` | NUMERIC | No | safe semantic cast |
| `product_length_cm` | `product_length_cm` | NUMERIC | No | safe semantic cast |
| `product_height_cm` | `product_height_cm` | NUMERIC | No | safe semantic cast |
| `product_width_cm` | `product_width_cm` | NUMERIC | No | safe semantic cast |

## Renames

```text
product_name_lenght
    → product_name_length

product_description_lenght
    → product_description_length

product_photos_qty
    → product_photos_count
```

Raw preserves the original source spelling and naming.

Staging exposes the corrected Mercury contract.

## Structural Contract

- `product_id` must not be null.
- `product_id` must be unique.
- non-empty count fields must convert successfully to `INT64`.
- non-empty measurement fields must convert successfully to `NUMERIC`.
- count fields must be non-negative when present.
- physical measurements must be non-negative when present.

## Nullability

The following fields are legitimately nullable:

- `product_category_name`;
- `product_name_length`;
- `product_description_length`;
- `product_photos_count`;
- `product_weight_g`;
- `product_length_cm`;
- `product_height_cm`;
- `product_width_cm`.

Mercury must not manufacture replacement values for missing product metadata.

The source contains:

- 610 products missing catalog-description attributes;
- 2 products missing physical measurements;
- 4 products with `product_weight_g = 0`.

Missing product metadata remains `NULL`.

Zero weight is preserved as a valid source value. It must not be silently converted to `NULL` or repaired, and is surfaced as a non-blocking quality observation.

## Known Quality Observations

The source contains:

- 610 products missing catalog-description attributes;
- small numbers of products missing physical measurements;
- four products with `product_weight_g = 0`.

Zero weight is preserved.

It may be surfaced as a non-blocking quality observation but must not be silently converted to `NULL` or repaired.

---

# 10. `stg_orders`

## Grain

```text
one row per order_id
```

## Source Key

```text
order_id
```

## Column Contract

| Raw column | Staging column | Type | Required | Transformation |
|---|---|---:|---:|---|
| `order_id` | `order_id` | STRING | Yes | trim, empty → NULL |
| `customer_id` | `customer_id` | STRING | Yes | trim, empty → NULL |
| `order_status` | `order_status` | STRING | Yes | trim, lowercase |
| `order_purchase_timestamp` | `order_purchase_timestamp` | TIMESTAMP | Yes | safe semantic cast |
| `order_approved_at` | `order_approved_timestamp` | TIMESTAMP | No | safe semantic cast |
| `order_delivered_carrier_date` | `order_delivered_carrier_timestamp` | TIMESTAMP | No | safe semantic cast |
| `order_delivered_customer_date` | `order_delivered_customer_timestamp` | TIMESTAMP | No | safe semantic cast |
| `order_estimated_delivery_date` | `order_estimated_delivery_date` | DATE | Yes | parse timestamp-like source → DATE |

## Renames

```text
order_approved_at
    → order_approved_timestamp

order_delivered_carrier_date
    → order_delivered_carrier_timestamp

order_delivered_customer_date
    → order_delivered_customer_timestamp
```

The carrier and customer delivery fields contain meaningful time-of-day information and therefore represent timestamps despite their Raw `_date` suffix.

`order_estimated_delivery_date` behaves as a calendar date and retains the `_date` suffix.

## Structural Contract

- `order_id` must not be null.
- `order_id` must be unique.
- `customer_id` must not be null.
- `order_status` must not be null.
- `order_purchase_timestamp` must not be null.
- `order_estimated_delivery_date` must not be null.
- all non-empty temporal values must successfully parse into their target semantic types.

Lifecycle timestamps such as approval and delivery are nullable because their presence depends on the order lifecycle.

## Known Quality Observations

The source currently contains:

```text
166 orders where carrier delivery occurs before purchase

23 orders where customer delivery occurs before
carrier delivery
```
Orders with `delivered` status also include:

```text
14 orders missing approval timestamps

2 orders missing carrier-delivery timestamps

8 orders missing customer-delivery timestamps
```

These records remain structurally interpretable.

Mercury must:

```text
preserve the row
preserve the timestamp / NULL
flag the anomaly
continue processing
```

They are not silently corrected.

---

# 11. `stg_order_items`

## Grain

```text
one row per (order_id, order_item_id)
```

## Source Key

```text
(order_id, order_item_id)
```

The compound key must be unique.

## Column Contract

| Raw column | Staging column | Type | Required | Transformation |
|---|---|---:|---:|---|
| `order_id` | `order_id` | STRING | Yes | trim, empty → NULL |
| `order_item_id` | `order_item_id` | INT64 | Yes | safe semantic cast |
| `product_id` | `product_id` | STRING | Yes | trim, empty → NULL |
| `seller_id` | `seller_id` | STRING | Yes | trim, empty → NULL |
| `shipping_limit_date` | `shipping_limit_timestamp` | TIMESTAMP | Yes | safe semantic cast |
| `price` | `price` | NUMERIC | Yes | safe semantic cast |
| `freight_value` | `freight_value` | NUMERIC | Yes | safe semantic cast |

## Rename

```text
shipping_limit_date
    → shipping_limit_timestamp
```

The source field contains meaningful time-of-day information and is therefore timestamp-semantic.

## Structural Contract

- all fields are required;
- `(order_id, order_item_id)` must be unique;
- `order_item_id` must successfully convert to `INT64`;
- `order_item_id >= 1`;
- shipping limit must successfully convert to `TIMESTAMP`;
- price must successfully convert to `NUMERIC`;
- freight value must successfully convert to `NUMERIC`;
- `price >= 0`;
- `freight_value >= 0`.

The current source contains:

```text
383 order items with freight_value = 0
```

Zero freight values remain valid source values and must not be converted to `NULL`.

No non-blocking quality view is needed for this condition because the contract explicitly classifies zero freight as valid—not suspicious.

---

# 12. `stg_payments`

## Grain

```text
one row per (order_id, payment_sequential)
```

## Source Key

```text
(order_id, payment_sequential)
```

## Column Contract

| Raw column | Staging column | Type | Required | Transformation |
|---|---|---:|---:|---|
| `order_id` | `order_id` | STRING | Yes | trim, empty → NULL |
| `payment_sequential` | `payment_sequential` | INT64 | Yes | safe semantic cast |
| `payment_type` | `payment_type` | STRING | Yes | trim, lowercase |
| `payment_installments` | `payment_installments` | INT64 | Yes | safe semantic cast |
| `payment_value` | `payment_value` | NUMERIC | Yes | safe semantic cast |

## Structural Contract

- all fields are required;
- `(order_id, payment_sequential)` must be unique;
- `payment_sequential` must successfully convert to `INT64`;
- `payment_sequential >= 1`;
- `payment_installments` must successfully convert to `INT64`;
- `payment_installments >= 0`;
- `payment_value` must successfully convert to `NUMERIC`;
- `payment_value >= 0`.

## Observed Payment Types

The current Olist source contains:

```text
credit_card
boleto
voucher
debit_card
not_defined
```

These are observed Olist values.

They are not a reusable Mercury-wide allowed-value list.

## Known Quality Observations

The source currently contains:

```text
80 orders without payment_sequential = 1

2 credit-card payment rows with
payment_installments = 0

9 zero-value payment rows
    6 voucher
    3 not_defined
```

These values are structurally valid and are preserved.

They may be surfaced through non-blocking quality models.

---

# 13. `stg_reviews`

## Grain

```text
one row per (review_id, order_id)
```

Neither `review_id` nor `order_id` is individually unique.

The combination is unique.

## Source Key

```text
(review_id, order_id)
```

## Column Contract

| Raw column | Staging column | Type | Required | Transformation |
|---|---|---:|---:|---|
| `review_id` | `review_id` | STRING | Yes | trim, empty → NULL |
| `order_id` | `order_id` | STRING | Yes | trim, empty → NULL |
| `review_score` | `review_score` | INT64 | Yes | safe semantic cast |
| `review_comment_title` | `review_comment_title` | STRING | No | trim boundaries, empty → NULL |
| `review_comment_message` | `review_comment_message` | STRING | No | trim boundaries, empty → NULL |
| `review_creation_date` | `review_creation_date` | DATE | Yes | parse timestamp-like source → DATE |
| `review_answer_timestamp` | `review_answer_timestamp` | TIMESTAMP | Yes | safe semantic cast |

## Structural Contract

- `(review_id, order_id)` must be unique;
- `review_id` must not be null;
- `order_id` must not be null;
- `review_score` must not be null;
- `review_creation_date` must not be null;
- `review_answer_timestamp` must not be null;
- review score must successfully convert to `INT64`;
- `1 <= review_score <= 5`;
- creation date source values must be parseable;
- answer timestamps must be parseable.

## Free-Form Text Policy

Review title and message are user-authored content.

Staging may:

- trim boundary whitespace;
- convert empty/whitespace-only values to `NULL`.

Staging must not:

- lowercase the content;
- rewrite spelling;
- translate text;
- censor values;
- infer sentiment;
- derive business classifications.

Those operations, if ever required, belong downstream.

## Review Creation Date Semantics

Raw `review_creation_date` is timestamp-like but overwhelmingly behaves as a calendar date.

Observed time-of-day representation:

```text
00:00:00    99,139 rows
01:00:00        85 rows
```

Only these two times are observed.

This pattern supports calendar-date semantics rather than meaningful timestamp precision.

The staging field therefore remains:

```text
review_creation_date DATE
```

and is derived from the parsed timestamp representation.

## Review Chronology

No current Olist record has:

```text
review_answer_timestamp < review_creation_date
```

Mercury may still define this as a non-blocking quality rule for future source deliveries.

---

# 14. Consolidated Raw → Staging Mapping

```text
CUSTOMERS
────────────────────────────────────────────────────────────
customer_id
    → customer_id STRING

customer_unique_id
    → customer_unique_id STRING

customer_zip_code_prefix
    → customer_zip_code_prefix STRING

customer_city
    → customer_city STRING

customer_state
    → customer_state STRING


SELLERS
────────────────────────────────────────────────────────────
seller_id
    → seller_id STRING

seller_zip_code_prefix
    → seller_zip_code_prefix STRING

seller_city
    → seller_city STRING

seller_state
    → seller_state STRING


GEOLOCATIONS
────────────────────────────────────────────────────────────
geolocation_zip_code_prefix
    → geolocation_zip_code_prefix STRING

geolocation_lat
    → geolocation_lat FLOAT64

geolocation_lng
    → geolocation_lng FLOAT64

geolocation_city
    → geolocation_city STRING

geolocation_state
    → geolocation_state STRING


PRODUCTS
────────────────────────────────────────────────────────────
product_id
    → product_id STRING

product_category_name
    → product_category_name STRING

product_name_lenght
    → product_name_length INT64

product_description_lenght
    → product_description_length INT64

product_photos_qty
    → product_photos_count INT64

product_weight_g
    → product_weight_g NUMERIC

product_length_cm
    → product_length_cm NUMERIC

product_height_cm
    → product_height_cm NUMERIC

product_width_cm
    → product_width_cm NUMERIC


ORDERS
────────────────────────────────────────────────────────────
order_id
    → order_id STRING

customer_id
    → customer_id STRING

order_status
    → order_status STRING

order_purchase_timestamp
    → order_purchase_timestamp TIMESTAMP

order_approved_at
    → order_approved_timestamp TIMESTAMP

order_delivered_carrier_date
    → order_delivered_carrier_timestamp TIMESTAMP

order_delivered_customer_date
    → order_delivered_customer_timestamp TIMESTAMP

order_estimated_delivery_date
    → order_estimated_delivery_date DATE


ORDER ITEMS
────────────────────────────────────────────────────────────
order_id
    → order_id STRING

order_item_id
    → order_item_id INT64

product_id
    → product_id STRING

seller_id
    → seller_id STRING

shipping_limit_date
    → shipping_limit_timestamp TIMESTAMP

price
    → price NUMERIC

freight_value
    → freight_value NUMERIC


PAYMENTS
────────────────────────────────────────────────────────────
order_id
    → order_id STRING

payment_sequential
    → payment_sequential INT64

payment_type
    → payment_type STRING

payment_installments
    → payment_installments INT64

payment_value
    → payment_value NUMERIC


REVIEWS
────────────────────────────────────────────────────────────
review_id
    → review_id STRING

order_id
    → order_id STRING

review_score
    → review_score INT64

review_comment_title
    → review_comment_title STRING

review_comment_message
    → review_comment_message STRING

review_creation_date
    → review_creation_date DATE

review_answer_timestamp
    → review_answer_timestamp TIMESTAMP
```

---

# 15. Consolidated Grain and Key Matrix

| Model | Grain | Source key |
|---|---|---|
| `stg_customers` | one row per customer | `customer_id` |
| `stg_sellers` | one row per seller | `seller_id` |
| `stg_geolocations` | one row per source geolocation observation | none established |
| `stg_products` | one row per product | `product_id` |
| `stg_orders` | one row per order | `order_id` |
| `stg_order_items` | one row per order item | `(order_id, order_item_id)` |
| `stg_payments` | one row per payment observation | `(order_id, payment_sequential)` |
| `stg_reviews` | one row per review/order observation | `(review_id, order_id)` |

---

# 16. Blocking Structural Contracts

Blocking validation protects the semantic guarantees made by staging.

Examples include:

```text
REQUIRED KEYS
────────────────────────────────────────
customer_id
seller_id
product_id
order_id
compound source keys


UNIQUENESS
────────────────────────────────────────
customer_id
seller_id
product_id
order_id
(order_id, order_item_id)
(order_id, payment_sequential)
(review_id, order_id)


CAST VALIDITY
────────────────────────────────────────
non-empty integer source
    → valid INT64

non-empty monetary source
    → valid NUMERIC

non-empty coordinate source
    → valid FLOAT64

non-empty timestamp source
    → valid TIMESTAMP


SAFE SEMANTIC DOMAINS
────────────────────────────────────────
latitude
    -90 to 90

longitude
    -180 to 180

order_item_id
    >= 1

payment_sequential
    >= 1

payment_installments
    >= 0

review_score
    1 to 5

non-negative measurements
non-negative monetary values
```

Blocking contracts should represent conditions where the promised staging structure cannot safely be delivered.

---

# 17. Non-Blocking Quality Observations

Quality observations represent values Mercury can interpret but which may warrant investigation.

Known Olist examples include:

## Geolocations

```text
261,831 exact duplicate source observations
```

These are preserved because staging does not redefine source grain.

---

## Products

```text
nullable catalog metadata
small number of missing physical measurements
4 zero-weight products
```

---

## Orders

```text
166 carrier timestamps before purchase

23 customer-delivery timestamps before
carrier-delivery timestamps

some delivered orders missing expected
lifecycle timestamps
```

---

## Payments

```text
80 orders without payment sequence 1

2 zero-installment credit-card payments

9 zero-value payment records
```

---

## Reviews

Current review chronology is clean.

A future condition such as:

```text
review_answer_timestamp < review_creation_date
```

would be surfaced as a quality anomaly rather than silently repaired.

---

# 18. Quality Severity Principle

Mercury staging distinguishes structural failures from source-quality anomalies.

```text
LEVEL 1 — STRUCTURAL FAILURE
────────────────────────────────────────

Example:
price = "banana"

Mercury cannot establish the promised
NUMERIC semantic representation.

Result:
blocking structural failure


LEVEL 2 — QUALITY ANOMALY
────────────────────────────────────────

Example:
carrier_timestamp < purchase_timestamp

Mercury understands both values,
but their relationship is suspicious.

Result:
preserve + flag + continue


LEVEL 3 — BUSINESS INTERPRETATION
────────────────────────────────────────

Example:
actual delivery > estimated delivery

This represents a late delivery,
not invalid source structure.

Result:
derive downstream in canonical/marts
```

This distinction must be preserved during Dataform implementation.

---

# 19. Explicit Staging Non-Goals

The Olist staging layer must not perform the following responsibilities.

## 19.1 No Cross-Entity Relationship Modelling

Staging does not yet determine whether:

```text
orders.customer_id
    → customers.customer_id

order_items.product_id
    → products.product_id

order_items.seller_id
    → sellers.seller_id

payments.order_id
    → orders.order_id

reviews.order_id
    → orders.order_id
```

Those relationships will be explored after staging is complete.

---

## 19.2 No Canonical Entity Construction

Staging does not decide:

- what constitutes a canonical customer;
- how multiple customer IDs should be unified;
- how geography should be deduplicated;
- how products should be categorized across future sources;
- how payments should be consolidated;
- how reviews should relate to canonical orders.

Those decisions belong to canonical modelling.

---

## 19.3 No Business Metrics

Staging must not derive metrics such as:

- order revenue;
- total order freight;
- customer lifetime value;
- repeat-customer flags;
- late-delivery flags;
- seller performance;
- average review score;
- payment totals;
- product popularity.

These belong downstream.

---

## 19.4 No Unjustified Deduplication

Staging must not use `DISTINCT` simply because duplicate rows exist.

Source grain is preserved unless an explicit source contract proves that duplicates are erroneous and defines deterministic remediation.

---

## 19.5 No Silent Error Repair

Staging must not silently:

- replace suspicious timestamps;
- convert zero values to `NULL`;
- manufacture missing values;
- rewrite identifiers;
- infer missing categories;
- alter lifecycle states;
- remove structurally interpretable anomalous rows.

Suspicious values should be surfaced through quality mechanisms.

---

# 20. Dataform Implementation Structure

The intended implementation structure is conceptually:

```text
definitions/
└── staging/
    └── olist/
        ├── stg_customers.sqlx
        ├── stg_sellers.sqlx
        ├── stg_geolocations.sqlx
        ├── stg_products.sqlx
        ├── stg_orders.sqlx
        ├── stg_order_items.sqlx
        ├── stg_payments.sqlx
        └── stg_reviews.sqlx
```

Non-blocking quality models may be organized separately, for example:

```text
definitions/
└── quality/
    └── olist/
        ├── dq_orders_lifecycle_anomalies.sqlx
        ├── dq_products_anomalies.sqlx
        └── dq_payments_anomalies.sqlx
```

The exact Dataform organization may evolve during implementation.

The architectural separation must remain:

```text
STANDARDIZATION
      ↓
STRUCTURAL VALIDATION
      ↓
QUALITY SURFACING
      ↓
CANONICAL MODELLING
```

---

# 21. Implementation Principles

The following principles apply while writing the Olist `.sqlx` models.

### Principle 1 — Explicit over implicit

Semantic transformations should be visible in SQL.

For example:

```sql
NULLIF(LOWER(TRIM(customer_city)), '')
```

is preferred over relying on the current source already being lowercase.

---

### Principle 2 — Safe casts over uncontrolled casts

Raw values come from external source systems.

Use safe semantic conversion and validate failures explicitly.

```sql
SAFE_CAST(...)
```

A failed safe cast must not silently disappear from observability.

---

### Principle 3 — Source conformity does not equal source guarantee

If current Olist data already follows a Mercury convention, Mercury still applies the convention explicitly.

The staging contract defines what downstream consumers can rely on regardless of future source variation.

---

### Principle 4 — Preserve source grain

Standardization changes representation.

It does not arbitrarily change the number or meaning of source observations.

---

### Principle 5 — Null is not automatically an error

Nullability must reflect source semantics.

Examples include:

- optional product metadata;
- optional review comments;
- lifecycle timestamps that do not exist because an order never reached that lifecycle stage.

---

### Principle 6 — Observed ranges are not automatically contracts

For example, if current product weight has a particular observed maximum, that maximum must not become a validation rule without semantic justification.

Contracts should represent genuine semantic constraints rather than accidental characteristics of the current dataset.

---

### Principle 7 — Quality anomalies remain observable

Suspicious but structurally valid source records must not disappear during transformation.

---

### Principle 8 — Source-specific staging, reusable standard

The Olist SQLX models are source-specific.

ADR-012 is reusable.

Future source systems may use different Raw column names and different source schemas while implementing the same Mercury staging principles.

Conceptually:

```text
OLIST RAW
     │
     ▼
OLIST STAGING MAPPING
     │
     ├──────────────┐
     │              │
     ▼              │
MERCURY             │
STAGING STANDARD ◄──┘
ADR-012


FUTURE SOURCE RAW
     │
     ▼
FUTURE SOURCE STAGING MAPPING
     │
     ├──────────────┐
     │              │
     ▼              │
SAME MERCURY        │
STAGING STANDARD ◄──┘
ADR-012
```

---

# 22. Staging Completion Criteria

The Olist staging phase is complete only when all of the following are true.

## Standardization

- [x] all eight staging models exist;
- [x] every Raw source field covered by this contract is mapped intentionally;
- [x] semantic types match this document;
- [x] required renames are implemented;
- [x] identifier normalization is implemented;
- [x] categorical normalization is implemented;
- [x] geographic normalization is implemented;
- [x] free-form text handling is implemented;
- [x] empty-string handling is implemented.

## Structural Validation

- [x] required-field contracts are tested;
- [x] declared source keys are tested;
- [x] compound-key uniqueness is tested;
- [x] invalid non-empty casts are detectable;
- [x] safe semantic domains are validated;
- [x] failures are observable and actionable.

## Quality Surfacing

- [x] known Olist source anomalies remain present after standardization;
- [x] known non-blocking anomalies do not unnecessarily stop the entire pipeline;
- [x] anomaly reporting is separated from structural staging guarantees;
- [x] no suspicious source values are silently repaired.

## Grain Preservation

- [x] staging row counts are reconciled with expected Raw source grain;
- [x] geolocation duplicates remain preserved;
- [x] no accidental `DISTINCT` or aggregation changes source grain.

## Scope Control

- [x] no canonical joins have been introduced;
- [x] no foreign-key assumptions have been introduced prematurely;
- [x] no business metrics have been introduced;
- [x] no canonical customer/product/order concepts have been inferred;
- [x] no business-level deduplication has been introduced.

---

# 23. Next Phase After Staging

Once this contract has been implemented and validated, Mercury may proceed to relationship exploration.

The intended sequence remains:

```text
DEFINE MERCURY STAGING STANDARD
ADR-012
             │
             ▼
CLASSIFY OLIST RAW COLUMNS
             │
             ▼
PROFILE SOURCE CONFORMITY
             │
             ▼
FINALIZE OLIST STAGING CONTRACT
             │
             ▼
IMPLEMENT DATAFORM
             │
             ▼
TEST STAGING
             │
             ▼
RELATIONSHIP EXPLORATION
             │
             ▼
CANONICAL MODELLING
             │
             ▼
MARTS / FEATURES / DATA PRODUCTS
```

Relationship exploration will investigate questions such as:

- customer identity relationships;
- order-to-customer relationships;
- order-to-item cardinality;
- product relationships;
- seller relationships;
- payment relationships;
- review relationships;
- geography relationships;
- orphaned identifiers;
- one-to-many and many-to-many behavior;
- appropriate canonical grains.

Those questions intentionally remain outside this staging contract.

---

# 24. Final Contract Summary

The Olist staging implementation establishes the following boundary:

```text
RAW
────────────────────────────────────────
source-faithful
immutable
all source values preserved
source naming preserved
source representation preserved


STAGING
────────────────────────────────────────
source-specific
semantically typed
consistently named
normalized
structurally validated
source grain preserved
quality anomalies surfaced


CANONICAL
────────────────────────────────────────
cross-entity
relationship-aware
business-semantic
source-independent where appropriate
```

The fundamental staging rule is:

> **Standardize what a source value is without inventing what it means to the business.**

And the fundamental quality rule is:

> **Fail when Mercury cannot safely establish the promised structure; flag and preserve when Mercury understands the record but the source itself appears suspicious.**

This contract is the implementation baseline for the Olist Dataform staging models and the source-specific application of ADR-012.