# Olist Canonical Model Overview

## Status

Draft

## Date

2026-09-19

## Purpose

This document defines the source-specific structure of Mercury's initial Olist canonical model.

It applies the platform-wide requirements established in the [Mercury Canonical Model Design](../../../../architecture/designs/canonical_model_design.md) to the validated Olist staging relations.

Detailed profiling evidence is maintained in the [Olist Relationship Profile](../../relationships/olist_relationship_profile.md). Anomaly baselines, severities, dispositions, and response requirements are maintained in the [Olist Anomaly Disposition Register](../../staging/olist_anomaly_disposition.md).

## Scope

This document defines:

- the initial Olist canonical relation inventory;
- relation grains and responsibilities;
- canonical relationships;
- relations intentionally excluded from the initial implementation;
- the Olist source namespace;
- the Olist canonical key registry;
- links to detailed dimension, fact, and publication contracts.

It does not reproduce staging contracts, relationship-profiling evidence, or anomaly-monitoring baselines.

## 1. Initial Canonical Model Inventory

The first canonical implementation uses the validated Olist staging relations while expressing source-independent business concepts.

### 1.1 Dimensions

| Relation | Grain | Business responsibility | Primary staging input |
| --- | --- | --- | --- |
| `dim_customer` | One row per `customer_unique_id` | Represents persistent customer identity independently of order-specific customer records | `stg_customers` |
| `dim_product` | One row per `product_id` | Represents reusable product and catalogue attributes | `stg_products` |
| `dim_seller` | One row per `seller_id` | Represents sellers and their governed geographic attributes | `stg_sellers` |
| `dim_date` | One row per calendar date | Provides reusable calendar attributes and role-playing date relationships | Generated from canonical date boundaries |
| `dim_location` | One row per ZIP-code prefix | Provides deterministically resolved geographic attributes | `stg_geolocations` |

### 1.2 Facts

| Relation | Grain | Business responsibility | Primary staging input |
| --- | --- | --- | --- |
| `fct_orders` | One row per `order_id` | Represents the order lifecycle and independently aggregated order-level measures | `stg_orders` |
| `fct_order_items` | One row per `(order_id, order_item_id)` | Represents individual product–seller line items and their commercial values | `stg_order_items` |
| `fct_payments` | One row per `(order_id, payment_sequential)` | Represents individual payment events associated with an order | `stg_payments` |
| `fct_reviews` | One row per `review_id` | Represents distinct review payloads and feedback chronology | `stg_reviews` |

### 1.3 Bridges

| Relation | Grain | Business responsibility | Primary staging input |
| --- | --- | --- | --- |
| `bridge_order_reviews` | One row per `(order_id, review_id)` | Preserves every validated association between orders and reviews | `stg_reviews` |

### 1.4 Intermediate Relations

The initial implementation is expected to require the following internal relations:

| Relation | Grain | Responsibility |
| --- | --- | --- |
| `int_geolocation_resolution` | One row per ZIP-code prefix | Resolves repeated geolocation observations into governed location attributes |
| `int_order_item_summary` | One row per `order_id` | Aggregates item counts and monetary measures before joining to order grain |
| `int_order_payment_summary` | One row per `order_id` | Aggregates payment counts and values before joining to order grain |
| `int_order_review_summary` | One row per `order_id` | Aggregates review-association counts without selecting an arbitrary review |

Intermediate relation names may be refined during their individual implementation contracts, but their declared grains and responsibilities must remain explicit.

## 2. Initial Relationship Structure

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

## 3. Excluded Initial Relations

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

## 4. Olist Key Exceptions

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

## 5. Canonical Key Registry

### 5.1 Primary keys

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

### 5.2 Preserved source identifiers

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

### 5.3 Foreign-key propagation

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

## 6. Source Namespace

The first implementation uses:

```text
source_namespace = "olist"
```

The source namespace identifies the Olist source instance represented by the current development data.

## 7. Detailed Contracts

The detailed Olist canonical contracts are maintained in:

- [Olist Dimension Contracts](olist_dimension_contracts.md);
- [Olist Fact Contracts](olist_fact_contracts.md);
- [Olist Publication Contract](olist_publication_contract.md).

These contracts implement the model inventory defined in this document.