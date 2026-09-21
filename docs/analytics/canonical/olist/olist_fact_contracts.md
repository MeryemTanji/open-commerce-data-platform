# Olist Canonical Fact Contracts

## Status

Draft

## Date

2026-09-21

## Purpose

This document defines the source-specific canonical fact and bridge contracts for the Olist implementation.

It applies the platform-wide [Mercury Canonical Model Design](../../../../architecture/designs/canonical_model_design.md) and the inventory established in the [Olist Canonical Model Overview](olist_canonical_model_overview.md).

Dimension references follow the [Olist Dimension Contracts](olist_dimension_contracts.md). Profiling evidence is maintained in the [Olist Relationship Profile](../../relationships/olist_relationship_profile.md), while anomaly baselines and dispositions remain governed by the [Olist Anomaly Disposition Register](../../staging/olist_anomaly_disposition.md).

## Scope

This document defines the initial Olist contracts for:

- `fct_orders`;
- `fct_order_items`;
- `fct_payments`;
- `fct_reviews`;
- `bridge_order_reviews`.

It defines fact grains, keys, measures, dimension references, source lineage, anomaly treatment, reconciliation behavior, and publication controls.

It does not reproduce relationship-profiling evidence or anomaly baselines.

## 1. Order Fact and Lifecycle Semantics

### 1.1 Business responsibility and grain

`fct_orders` represents the order as a business process and preserves its lifecycle, customer context, temporal roles, and independently aggregated child-process summaries.

Its grain is:

```text
one row per source namespace and order_id
```

Its primary key is:

```text
order_key
```

The key is generated from:

```text
key_version
    +
order entity type
    +
source_namespace
    +
order_id
```

The initial source namespace is:

```text
olist
```

The same source namespace and `order_id` must always generate the same `order_key`.

The order fact must preserve every staged order, including orders without customer, item, payment, or review relationships.

### 1.2 Core order columns

The core identity and lifecycle columns are:

| Column | Responsibility |
| --- | --- |
| `order_key` | Canonical primary key |
| `source_namespace` | Namespace of the originating source instance |
| `source_order_id` | Preserved source `order_id` |
| `order_status` | Normalized source lifecycle status |
| `order_purchase_timestamp` | Preserved purchase timestamp |
| `order_approved_timestamp` | Preserved nullable approval timestamp |
| `order_delivered_carrier_timestamp` | Preserved nullable carrier-delivery timestamp |
| `order_delivered_customer_timestamp` | Preserved nullable customer-delivery timestamp |
| `order_estimated_delivery_date` | Preserved estimated-delivery date |
| `purchase_date_key` | Purchase-date key referencing `dim_date` |
| `approval_date_key` | Nullable approval-date key referencing `dim_date` |
| `carrier_delivery_date_key` | Nullable carrier-delivery-date key referencing `dim_date` |
| `customer_delivery_date_key` | Nullable customer-delivery-date key referencing `dim_date` |
| `estimated_delivery_date_key` | Estimated-delivery-date key referencing `dim_date` |

The customer and order-context columns are:

| Column | Responsibility |
| --- | --- |
| `customer_key` | Foreign key to the canonical customer |
| `source_customer_record_id` | Preserved order-specific source `customer_id` |
| `customer_location_key` | Foreign key to the order-context location |
| `customer_source_postal_code_prefix` | Postal-code prefix from the customer record |
| `customer_source_city` | Normalized city from the customer record |
| `customer_source_state` | Normalized state from the customer record |
| `customer_reference_status` | Result of customer identity resolution |

Customer identity and location resolution must follow the Olist dimension contracts.

### 1.3 Order-status semantics

The current source contains the following normalized status values:

```text
created
approved
invoiced
processing
shipped
delivered
unavailable
canceled
```

`order_status` preserves the source lifecycle classification.

Mercury must not:

- infer a different status from the presence or absence of lifecycle timestamps;
- promote an order to a later status;
- replace a status because related items or payments are absent;
- interpret `estimated_delivery_date` as evidence of actual delivery;
- collapse `canceled` and `unavailable` into one category.

A future new status requires contract review before it is accepted into the canonical domain.

### 1.4 Customer and location resolution

Customer resolution follows:

```text
stg_orders.customer_id
        ↓
stg_customers.customer_id
        ↓
dim_customer.customer_key
```

The join must preserve order grain.

When an order resolves to a staged customer:

- `customer_key` references the persistent customer;
- `source_customer_record_id` preserves the order-specific `customer_id`;
- `customer_location_key` represents the address context observed for that order;
- customer source geography remains available for lineage.

When no staged customer record exists:

- the order remains publishable;
- `source_customer_record_id` remains preserved;
- `customer_key` is `NULL`;
- customer-derived geographic attributes are unavailable;
- `customer_reference_status` is `missing_customer`;
- customer-dependent outputs must exclude or separately classify the order.

Mercury must not invent a persistent customer or associate the order with an unrelated customer.

### 1.5 Temporal roles

Date keys follow the Olist dimension contract:

| Date key                      | Source field                         | Nullability |
| ----------------------------- | ------------------------------------ | ----------- |
| `purchase_date_key`           | `order_purchase_timestamp`           | Required    |
| `approval_date_key`           | `order_approved_timestamp`           | Nullable    |
| `carrier_delivery_date_key`   | `order_delivered_carrier_timestamp`  | Nullable    |
| `customer_delivery_date_key`  | `order_delivered_customer_timestamp` | Nullable    |
| `estimated_delivery_date_key` | `order_estimated_delivery_date`      | Required    |

Timestamp-derived date keys use the documented UTC extraction convention.

A nullable lifecycle timestamp produces a nullable date key. Mercury must not generate a date key for an event that is absent from the source.

### 1.6 Lifecycle-quality indicators

`fct_orders` exposes the following indicators:

| Column | Meaning |
| --- | --- |
| `is_carrier_before_purchase` | Carrier delivery precedes purchase |
| `is_customer_before_carrier` | Customer delivery precedes carrier delivery |
| `is_delivered_missing_approval` | Delivered order has no approval timestamp |
| `is_delivered_missing_carrier_delivery` | Delivered order has no carrier-delivery timestamp |
| `is_delivered_missing_customer_delivery` | Delivered order has no customer-delivery timestamp |
| `has_lifecycle_anomaly` | At least one governed lifecycle anomaly is present |

These indicators expose source conditions without modifying the underlying timestamps.

`has_lifecycle_anomaly` is derived as the logical union of the individual lifecycle indicators.

### 1.7 Lifecycle durations

Reusable lifecycle durations are calculated from preserved timestamps.

The initial duration columns are:

| Column | Calculation |
| --- | --- |
| `purchase_to_approval_seconds` | Approval minus purchase timestamp |
| `purchase_to_carrier_delivery_seconds` | Carrier delivery minus purchase timestamp |
| `carrier_to_customer_delivery_seconds` | Customer delivery minus carrier delivery |
| `purchase_to_customer_delivery_seconds` | Customer delivery minus purchase timestamp |
| `delivery_date_variance_days` | Actual delivery date minus estimated delivery date |

A positive `delivery_date_variance_days` value indicates delivery after the estimated date. A negative value indicates delivery before the estimated date.

A duration must be `NULL` when:

- either required endpoint is unavailable;
- the endpoint ordering is invalid for that calculation;
- the applicable anomaly disposition excludes the record from that chronology calculation.

Every suppressed duration must be accompanied by the applicable lifecycle-anomaly indicator.

A newly observed invalid temporal ordering that is not covered by an existing indicator must be surfaced as a new quality condition and receive an approved disposition before the affected derived duration is published.

Mercury must not apply an absolute value, reorder endpoints, or infer a missing timestamp to manufacture a usable duration.

### 1.8 Child-process summaries

Items, payments, and reviews are independent child relationships from orders. Each must be aggregated independently to order grain before joining to `fct_orders`.

The order fact includes:

| Column | Responsibility |
| --- | --- |
| `item_count` | Number of staged order-item observations |
| `distinct_product_count` | Number of distinct source product identifiers |
| `distinct_seller_count` | Number of distinct source seller identifiers |
| `item_price_total` | Sum of item-level unit prices |
| `freight_total` | Sum of item-level freight values |
| `item_based_order_total` | Sum of item prices and freight values |
| `payment_count` | Number of staged payment observations |
| `payment_total` | Sum of payment values |
| `review_association_count` | Number of distinct staged `(order_id, review_id)` associations |
| `has_items` | Indicates whether the order has items |
| `has_payments` | Indicates whether the order has payments |
| `has_reviews` | Indicates whether the order has review associations |
| `item_coverage_status` | Classification of item coverage |
| `payment_coverage_status` | Classification of payment coverage |
| `review_coverage_status` | Classification of review coverage |

When no child rows exist:

- the corresponding row count is `0`;
- the corresponding presence indicator is `FALSE`;
- monetary totals remain `NULL` rather than being represented as observed zero value;
- the applicable coverage status explains the missing relationship.

A missing relationship must not be replaced with inferred child records or inferred monetary values.

### 1.9 Item-coverage status

The initial `item_coverage_status` domain is:

| Value | Meaning |
| --- | --- |
| `present` | One or more order-item observations exist |
| `absent_status_consistent` | No items exist, and the order status permits their absence |
| `absent_requires_review` | No items exist, but the order status normally requires item evidence |

The statuses treated as status-consistent for item absence are:

```text
created
canceled
unavailable
```

Absence for the following statuses requires review:

```text
approved
invoiced
processing
shipped
delivered
```

An itemless order remains valid for order-level analyses that do not require item, product, seller, freight, or item-based value evidence.

### 1.10 Payment-coverage status

The initial `payment_coverage_status` domain is:

| Value | Meaning |
| --- | --- |
| `present` | One or more payment observations exist |
| `absent_status_consistent` | No payments exist, and the order status permits their absence |
| `absent_requires_review` | No payments exist, but the order status normally requires payment evidence |

The statuses treated as status-consistent for payment absence are:

```text
created
canceled
unavailable
```

Absence for the following statuses requires review:

```text
approved
invoiced
processing
shipped
delivered
```

A paymentless order remains valid for non-payment analysis.

Mercury must not infer that `payment_total` equals `item_based_order_total`.

### 1.11 Review-coverage status

The initial `review_coverage_status` domain is:

| Value     | Meaning                               |
| --------- | ------------------------------------- |
| `present` | One or more review associations exist |
| `absent`  | No review association exists          |

A missing review does not invalidate an order.

Reviewless orders remain available for analyses that do not require customer feedback. Delivered orders without reviews remain explicitly observable through the applicable quality control.

### 1.12 Order-value reconciliation

Item and payment measures are compared only after both child relations have been aggregated independently to order grain.

The reconciliation difference is:

```text
payment_total - item_based_order_total
```

The accepted absolute tolerance is:

```text
0.01
```

The initial `order_value_reconciliation_status` domain is:

| Value | Meaning |
| --- | --- |
| `reconciled` | Absolute difference between both totals is at most `0.01` |
| `payment_above_item_total` | Payment total exceeds the item-based total by more than `0.01` |
| `payment_below_item_total` | Payment total is below the item-based total by more than `0.01` |
| `not_comparable_missing_items` | Payment evidence exists, but item evidence is absent |
| `not_comparable_missing_payments` | Item evidence exists, but payment evidence is absent |
| `not_comparable_missing_both` | Neither item nor payment evidence exists |

The order fact exposes:

| Column                              | Responsibility                                    |
| ----------------------------------- | ------------------------------------------------- |
| `order_value_difference`            | Signed payment total minus item-based order total |
| `order_value_absolute_difference`   | Absolute value of the reconciliation difference   |
| `order_value_reconciliation_status` | Governed reconciliation classification            |

When either total is unavailable:

- difference values remain `NULL`;
- the reconciliation status identifies the missing relationship;
- no missing total is replaced with zero;
- reconciliation-dependent outputs must exclude or separately classify the order.

Mercury must preserve both monetary concepts. Neither value may be overwritten to force agreement.

### 1.13 Join-amplification safeguards

The order fact must be assembled from one-row-per-order inputs:

```text
stg_orders
        +
int_order_item_summary
        +
int_order_payment_summary
        +
int_order_review_summary
        +
customer identity resolution
```

The child summaries must be independently aggregated before they are joined.

`fct_orders` must not join detailed order-item, payment, or review rows simultaneously.

Product, seller, payment-method, and individual-review attributes do not belong directly on `fct_orders`.

### 1.14 Order anomaly dispositions

The principal order-level conditions are treated as follows:

| Condition | Canonical treatment |
| --- | --- |
| `orders_without_customer` | Retain the order and source customer reference; set `customer_key` to `NULL` |
| Item absence for `created`, `canceled`, or `unavailable` orders | Retain and classify as `absent_status_consistent` |
| Item absence for later lifecycle statuses | Retain and classify as `absent_requires_review`; prevent item-dependent reconciliation |
| Payment absence for `created`, `canceled`, or `unavailable` orders | Retain and classify as `absent_status_consistent` |
| Payment absence for later lifecycle statuses | Retain and classify as `absent_requires_review`; prevent payment-dependent reconciliation |
| Delivered order without review | Retain and classify review coverage as `absent` |
| `carrier_before_purchase` | Preserve timestamps, flag the anomaly, and suppress the affected duration |
| `customer_before_carrier` | Preserve timestamps, flag the anomaly, and suppress the affected duration |
| Delivered order missing a lifecycle timestamp | Preserve the `NULL`, expose the applicable flag, and do not infer the event |
| `payment_above_item_total` | Preserve both totals and flag the reconciliation direction |
| `payment_below_item_total` | Preserve both totals and flag the reconciliation direction |

The Olist anomaly disposition register remains authoritative for control IDs, baselines, severity, notification requirements, and response playbooks.

### 1.15 Order publication controls

`fct_orders` must enforce:

- one row per `order_key`;
- one row per source namespace and `source_order_id`;
- non-null canonical and source identity columns;
- deterministic consistency between `order_key` and its key inputs;
- preservation of the staged order count;
- no row amplification during customer, location, or child-summary resolution;
- accepted `order_status` values;
- a non-null `purchase_date_key`;
- a non-null `estimated_delivery_date_key`;
- valid `dim_date` references for every non-null role-specific date key;
- preservation of every source lifecycle timestamp;
- non-null Boolean values for every lifecycle-quality indicator;
- `has_lifecycle_anomaly = TRUE` if and only if at least one governed lifecycle-quality indicator is `TRUE`;
- every suppressed chronology-dependent duration to be explained by its corresponding lifecycle-quality indicator;
- non-negative lifecycle durations whenever a duration is published;
- valid `customer_reference_status` values;
- a non-null, valid `dim_customer` reference whenever `customer_reference_status` is `matched` or `reused_customer_record`;
- a `NULL` `customer_key` whenever `customer_reference_status` is `missing_customer`;
- a non-null `customer_location_key` whenever `customer_reference_status` is `matched` or `reused_customer_record`;
- a `NULL` `customer_location_key` whenever `customer_reference_status` is `missing_customer`;
- a valid `dim_location` reference whenever `customer_location_key` is non-null;
- preservation of the source customer-record identifier;
- valid item-, payment-, and review-coverage status values;
- non-negative child-observation counts;
- consistency between each child-observation count and its corresponding coverage status;
- independently aggregated item, payment, and review summaries before they are joined to the order grain;
- preservation of both item-derived and payment-derived order totals;
- no multiplication of item, payment, or review measures through cross-process joins;
- explicit reconciliation status for every order;
- reconciliation differences calculated only when both governed totals are available;
- use of the approved monetary tolerance when assigning reconciliation status;
- no forced agreement between independently derived monetary totals.

A blocking canonical control must fail if:

- customer resolution unexpectedly changes the number of order rows;
- any one-row-per-order intermediate contains duplicate `source_order_id` values;
- joining an intermediate summary changes the order grain;
- a required canonical or source identifier is unavailable;
- a canonical foreign key is populated but does not resolve to its declared parent;
- a lifecycle-quality indicator or derived duration contradicts its governing rule;
- a child-coverage status contradicts the corresponding child-observation count;
- monetary reconciliation logic produces an unsupported or internally inconsistent state.

Known source anomalies governed by an approved non-blocking disposition must remain publishable when the required lineage, status, and anomaly indicators are present.

The existing staging and relationship-quality controls remain responsible for monitoring changes in source coverage, cardinality, chronology, and reconciliation baselines. Canonical controls validate that those findings have been implemented without changing the declared order grain or silently altering source evidence.

## 2. Order-Item Fact and Commercial Grain

### 2.1 Business responsibility and grain

`fct_order_items` represents the individual commercial line observations associated with Olist orders.

Its grain is:

```text
one row per source namespace, order_id, and order_item_id
```

Its canonical primary key is:

```text
order_item_key
```

The key is generated deterministically from:

```text
key_version
    +
order-item entity type
    +
source_namespace
    +
source_order_id
    +
source_order_item_id
```

The relation preserves every validated staged order-item observation.

The source `order_item_id` is unique only within an order. It must not be treated as a globally unique identifier, renumbered, or interpreted independently of `order_id`.

### 2.2 Core order-item columns

The initial `fct_order_items` columns include:

| Column                     | Responsibility                                |
| -------------------------- | --------------------------------------------- |
| `order_item_key`           | Canonical primary key for the order item      |
| `source_namespace`         | Namespace of the originating source instance  |
| `source_order_id`          | Preserved source `order_id`                   |
| `source_order_item_id`     | Preserved source `order_item_id`              |
| `order_key`                | Foreign key to `fct_orders`                   |
| `order_reference_status`   | Result of order-reference resolution          |
| `source_product_id`        | Preserved source `product_id`                 |
| `product_key`              | Nullable foreign key to `dim_product`         |
| `product_reference_status` | Result of product-reference resolution        |
| `source_seller_id`         | Preserved source `seller_id`                  |
| `seller_key`               | Nullable foreign key to `dim_seller`          |
| `seller_reference_status`  | Result of seller-reference resolution         |
| `shipping_limit_timestamp` | Preserved shipping-limit timestamp            |
| `shipping_limit_date_key`  | Foreign key to `dim_date`                     |
| `unit_price`               | Preserved item price                          |
| `freight_value`            | Preserved item-level freight value            |
| `item_total_value`         | Sum of unit price and freight value           |
| `unit_quantity`            | Quantity represented by the physical fact row |

The initial value of `unit_quantity` is:

```text
1
```

This value records that each source order-item row represents one observed unit. It does not consolidate repeated product rows or replace the physical row grain.

### 2.3 Order relationship

Every order item is expected to resolve to one canonical order:

```text
stg_order_items.order_id
        ↓
fct_orders.source_order_id
        ↓
fct_orders.order_key
```

The initial `order_reference_status` domain is:

| Value           | Meaning                                        |
| --------------- | ---------------------------------------------- |
| `matched`       | The order item resolved to one canonical order |
| `missing_order` | The order item references no canonical order   |

An unmatched order item remains publishable only when its source order identifier is preserved and its missing-parent condition is exposed explicitly.

Mercury must not:

- fabricate an order for an unmatched order item;
- associate an unmatched item with a different order;
- discard an otherwise valid item solely because its order reference is missing;
- allow unmatched items into calculations requiring a valid canonical order.

### 2.4 Product relationship

Product identity is resolved through:

```text
stg_order_items.product_id
        ↓
dim_product.source_product_id
        ↓
dim_product.product_key
```

The initial `product_reference_status` domain is:

| Value             | Meaning                                                       |
| ----------------- | ------------------------------------------------------------- |
| `matched`         | The order item resolved to one canonical product              |
| `missing_product` | The source product identifier references no canonical product |

When product resolution succeeds, `product_key` must reference exactly one `dim_product` row.

When product resolution fails:

- the order item remains available;
- `source_product_id` is preserved;
- `product_key` is `NULL`;
- `product_reference_status` is `missing_product`;
- the item is excluded only from outputs requiring a resolved product.

Mercury must not invent, substitute, or silently correct a missing product reference.

### 2.5 Seller relationship

Seller identity is resolved through:

```text
stg_order_items.seller_id
        ↓
dim_seller.source_seller_id
        ↓
dim_seller.seller_key
```

The initial `seller_reference_status` domain is:

| Value            | Meaning                                                     |
| ---------------- | ----------------------------------------------------------- |
| `matched`        | The order item resolved to one canonical seller             |
| `missing_seller` | The source seller identifier references no canonical seller |

When seller resolution succeeds, `seller_key` must reference exactly one `dim_seller` row.

When seller resolution fails:

- the order item remains available;
- `source_seller_id` is preserved;
- `seller_key` is `NULL`;
- `seller_reference_status` is `missing_seller`;
- the item is excluded only from outputs requiring a resolved seller.

Mercury must not treat seller as a permanent product attribute. Seller identity belongs to the commercial order-item event.

### 2.6 Shipping-limit semantics

`shipping_limit_timestamp` represents the source-provided fulfilment deadline associated with the order item.

It is preserved as a timestamp and also produces:

```text
shipping_limit_date_key
```

The date key references `dim_date` using the calendar date derived under Mercury’s documented Olist timezone convention.

The canonical model must not:

- interpret the shipping limit as an observed shipment event;
- replace it with an order-level delivery timestamp;
- infer that shipment occurred before the limit;
- collapse different item-level shipping limits to one arbitrary order-level value.

If an order-level shipping-limit summary is required downstream, it must use an explicitly documented aggregation such as the earliest or latest item shipping limit.

### 2.7 Monetary measures

The order-item fact preserves the following monetary measures:

| Column             | Meaning                                    |
| ------------------ | ------------------------------------------ |
| `unit_price`       | Source item price for the represented unit |
| `freight_value`    | Source freight value assigned to the item  |
| `item_total_value` | `unit_price + freight_value`               |

All monetary columns use an exact numeric type appropriate for currency values.

The following calculation applies:

```text
item_total_value = unit_price + freight_value
```

A zero freight value is valid and must not be treated as missing.

The item fact must not allocate payment values to individual order items unless a separate governed allocation contract is introduced.

Payment totals remain part of the payment business process and are reconciled with independently aggregated item totals at the order grain.

### 2.8 Repeated products and quantity semantics

Repeated `(order_id, product_id)` combinations are valid source observations and represent item quantity only through explicit aggregation.

The physical fact remains:

```text
one row per source namespace, order_id, and order_item_id
```

Each physical row retains:

- its source order-item identifier;
- product identity;
- seller identity;
- unit price;
- freight value;
- shipping-limit timestamp;
- unit quantity of `1`.

A downstream quantity summary may calculate:

```text
quantity = COUNT(-)
```

but only after selecting a grouping grain that preserves every commercially meaningful distinction.

The minimum grouping context includes:

```text
order_key
product_key or source_product_id
seller_key or source_seller_id
unit_price
freight_value
shipping_limit_timestamp
```

If any of those values differ, the rows must remain separate unless another explicitly governed aggregation is introduced.

The current validated source contains repeated order-product combinations, but no repeated combination with conflicting sellers, prices, freight values, or shipping limits. Controls must still preserve those distinctions if such cases appear in future deliveries.

### 2.9 Multi-seller and product relationships

An order may contain items from multiple sellers, and a product may be sold by multiple sellers.

These relationships are represented through `fct_order_items`.

Mercury must not:

- assign one seller to an entire order when multiple sellers are present;
- store seller as a fixed attribute of `dim_product`;
- aggregate an order-product combination without retaining seller context;
- join seller-level and product-level summaries in a way that multiplies item measures.

An optional order–seller summary may be derived downstream at:

```text
one row per order_key and seller_key
```

Such a summary must aggregate directly from `fct_order_items` and declare its measures and grain explicitly.

### 2.10 Join-amplification safeguards

`fct_order_items` is the canonical detailed relation for analysing products and sellers within orders.

Payment and review relations must not be joined directly to item rows when their independent one-to-many grains would multiply observations.

Unsafe detailed join:

```text
order items
    ×
payments
    ×
reviews
```

Required pattern:

```text
order items
    ↓
aggregate independently to the required grain
    ↓
combine with independently aggregated payment or review measures
```

Order-level item measures must be aggregated from `fct_order_items` before they are joined to `fct_orders` or another order-grain relation.

A controlled join from `fct_order_items` to one-row-per-key dimensions or to `fct_orders` must preserve the order-item row count.

### 2.11 Order-item anomaly dispositions

The applicable source and relationship conditions receive the following canonical treatments:

| Condition | Canonical treatment |
| --- | --- |
| `order_items_without_order` | Retain the item and source order reference; set `order_key` to `NULL` and classify it as `missing_order` |
| `order_items_without_product` | Retain the item and source product reference; set `product_key` to `NULL` and classify it as `missing_product` |
| `order_items_without_seller` | Retain the item and source seller reference; set `seller_key` to `NULL` and classify it as `missing_seller` |
| `repeated_order_product_combinations` | Preserve every item row; derive quantity only through explicit aggregation |
| `repeated_order_products_with_multiple_sellers` | Preserve seller-level item separation |
| `repeated_order_products_with_multiple_prices` | Preserve price-level item separation |
| `repeated_order_products_with_multiple_freight_values` | Preserve freight-level item separation |
| `repeated_order_products_with_multiple_shipping_limits` | Preserve shipping-limit-level item separation |
| `orders_with_multiple_sellers` | Preserve every seller association; require seller-aware aggregation |
| `products_with_multiple_sellers` | Preserve seller on the item event; do not assign a fixed seller to the product |
| Missing or invalid monetary value | Preserve source evidence; withhold affected measures until an approved disposition exists |
| Invalid shipping-limit timestamp | Preserve source evidence; withhold the affected date key until the condition is resolved |

Existing staging and relationship-quality controls remain responsible for monitoring changes to these anomaly baselines.

### 2.12 Order-item publication controls

`fct_order_items` must enforce:

- one row per `order_item_key`;
- one row per source namespace, `source_order_id`, and `source_order_item_id`;
- non-null canonical and source identity columns;
- deterministic consistency between `order_item_key` and its key inputs;
- preservation of the staged order-item count;
- no row amplification during order, product, seller, or date resolution;
- a non-null, valid `fct_orders` reference whenever `order_reference_status` is `matched`;
- a `NULL` `order_key` whenever `order_reference_status` is `missing_order`;
- a non-null, valid `dim_product` reference whenever `product_reference_status` is `matched`;
- a `NULL` `product_key` whenever `product_reference_status` is `missing_product`;
- a non-null, valid `dim_seller` reference whenever `seller_reference_status` is `matched`;
- a `NULL` `seller_key` whenever `seller_reference_status` is `missing_seller`;
- valid order-, product-, and seller-reference status values;
- preservation of all source relationship identifiers;
- a valid `dim_date` reference whenever `shipping_limit_date_key` is populated;
- deterministic consistency between `shipping_limit_timestamp` and `shipping_limit_date_key`;
- non-null exact numeric values for `unit_price` and `freight_value`;
- non-negative `unit_price` and `freight_value`;
- exact consistency between `item_total_value` and `unit_price + freight_value`;
- `unit_quantity = 1` for every physical fact row;
- preservation of repeated order-product observations;
- no unintended consolidation of rows with different sellers, prices, freight values, or shipping limits.

A blocking canonical control must fail if:

- canonical processing changes the staged order-item count unexpectedly;
- a canonical key maps to more than one source key combination;
- a matched canonical foreign key does not resolve to its declared parent;
- a missing-reference status is paired with a populated canonical foreign key;
- a source relationship identifier is lost;
- monetary derivation is inconsistent;
- dimensional resolution multiplies or removes order-item rows;
- the implemented relation no longer conforms to its declared grain.

Known source anomalies governed by an approved non-blocking disposition remain publishable when their source lineage, reference statuses, and affected-measure safeguards are present.

## 3. Payment Fact and Payment Semantics

### 3.1 Business responsibility and grain

`fct_payments` represents individual payment observations associated with canonical orders.

Its grain is:

```text
one row per source namespace, order_id, and payment_sequential
```

Its canonical primary key is:

```text
payment_key
```

The key is generated deterministically from:

```text
key_version
    +
payment entity type
    +
source_namespace
    +
source_order_id
    +
source_payment_sequence
```

The relation preserves every validated staged payment observation.

Multiple payments associated with one order may represent split payments, multiple vouchers, or another valid source payment arrangement. They must not be consolidated into one physical payment row.

### 3.2 Core payment columns

The initial `fct_payments` columns include:

| Column | Responsibility |
| --- | --- |
| `payment_key` | Canonical primary key |
| `source_namespace` | Namespace of the originating source instance |
| `source_order_id` | Preserved source `order_id` |
| `source_payment_sequence` | Preserved source `payment_sequential` |
| `order_key` | Nullable foreign key to `fct_orders` |
| `order_reference_status` | Result of order-reference resolution |
| `payment_type` | Normalized source payment type |
| `payment_installments` | Preserved source installment count |
| `payment_value` | Preserved source payment value |
| `is_order_missing_sequence_one` | Order has no observed payment sequence one |
| `is_zero_installment_credit_card` | Credit-card payment has zero installments |
| `is_zero_value_payment` | Payment value is zero |
| `has_payment_anomaly` | At least one governed payment anomaly applies |

The payment fact does not infer payment timestamps because the source provides no payment-event timestamp.

### 3.3 Order relationship

Every payment is expected to resolve to one canonical order:

```text
stg_payments.order_id
        ↓
fct_orders.source_order_id
        ↓
fct_orders.order_key
```

The initial `order_reference_status` domain is:

| Value           | Meaning                                     |
| --------------- | ------------------------------------------- |
| `matched`       | The payment resolved to one canonical order |
| `missing_order` | The payment references no canonical order   |

When order resolution succeeds, `order_key` must reference exactly one row in `fct_orders`.

When order resolution fails:

- the payment remains available;
- `source_order_id` is preserved;
- `order_key` is `NULL`;
- `order_reference_status` is `missing_order`;
- the payment is excluded only from outputs requiring a resolved canonical order.

Mercury must not fabricate an order, substitute another order, or discard an otherwise valid payment because its parent reference is missing.

### 3.4 Payment-sequence semantics

`source_payment_sequence` preserves the source `payment_sequential` value.

The sequence identifies payment observations within an order. It is part of the source-derived payment identity but does not establish a globally meaningful chronology.

The current validated source includes orders whose observed sequences begin at two:

- 78 orders contain only sequence two;
- 2 orders contain sequences two and three;
- 80 orders therefore contain no observed sequence one.

Mercury cannot determine whether the sequence-one payment is missing or whether the source assigned its sequence according to another process.

The canonical model must therefore:

- preserve every source sequence value unchanged;
- retain the affected payments;
- expose `is_order_missing_sequence_one`;
- avoid interpreting sequence values as proof of payment-event chronology;
- avoid inferring missing sequence rows.

Mercury must not:

- renumber payment sequences;
- generate a synthetic sequence-one payment;
- shift later sequences to close a gap;
- consolidate payments solely because their sequences appear irregular.

### 3.5 Payment-type semantics

The current Olist source contains the following observed payment types:

```text
credit_card
boleto
voucher
debit_card
not_defined
```

These values describe source payment classifications. They are not a platform-wide Mercury payment-type domain.

`payment_type` must preserve the normalized staged value.

The value `not_defined` is a source classification and must not be converted to `NULL`, replaced with another payment type, or treated as evidence that the payment row is invalid.

A future source may introduce different payment types through its own source-specific contract.

### 3.6 Installment semantics

`payment_installments` preserves the source-reported installment count.

The value describes how the source represented the payment arrangement. It does not represent:

- the number of payment rows;
- the payment sequence;
- the number of installments already settled;
- an independently observed repayment schedule.

The current validated source contains two credit-card payments with:

```text
payment_installments = 0
```

These observations remain structurally valid but require explicit quality visibility.

For affected payments:

- the source value remains zero;
- `is_zero_installment_credit_card` is `TRUE`;
- no installment count is inferred;
- analyses requiring a positive installment count must exclude or separately classify the affected payment.

Mercury must not replace a zero installment count with one.

### 3.7 Payment-value semantics

`payment_value` preserves the source payment value using an exact numeric type appropriate for currency.

The value must be non-negative.

The current validated source contains nine zero-value payments:

| Payment type  | Payment rows |
| ------------- | -----------: |
| `voucher`     |            6 |
| `not_defined` |            3 |

A zero payment value is preserved as source evidence and is not converted to `NULL`.

For affected payments:

- `payment_value` remains zero;
- `is_zero_value_payment` is `TRUE`;
- the payment remains part of payment-event counts;
- the payment contributes zero to additive monetary totals;
- analyses requiring positive-value payments must exclude or separately classify it explicitly.

Mercury must not replace a zero payment value or infer a positive amount from order-item evidence.

### 3.8 Multi-payment orders

An order may contain zero, one, or multiple payment observations.

The current validated relationship includes:

- 99,440 orders with at least one payment;
- 2,961 orders with multiple payments;
- a maximum of 29 payments for one order;
- one delivered order without a payment observation.

Multiple payment observations are valid and must remain separate at the physical payment grain.

Order-level payment summaries must be derived through explicit aggregation:

```text
one row per order_key
```

The initial order-level measures include:

```text
payment_count = COUNT(-)

payment_total = SUM(payment_value)
```

Payment counts and totals must be aggregated before they are joined to order-grain models.

An order without payment evidence must remain publishable when its payment-coverage status and related anomaly disposition are exposed by `fct_orders`.

### 3.9 Payment-quality indicators

The governed payment-quality indicators are:

| Column | Meaning |
| --- | --- |
| `is_order_missing_sequence_one` | Order has no observed payment sequence one |
| `is_zero_installment_credit_card` | Credit-card payment has zero installments |
| `is_zero_value_payment` | Preserved payment value is zero |
| `has_payment_anomaly` | At least one governed payment anomaly applies |
The aggregate indicator follows:

```text
has_payment_anomaly =
    is_order_missing_sequence_one
    OR is_zero_installment_credit_card
    OR is_zero_value_payment
```

These indicators expose source-quality conditions. They do not authorize deletion, renumbering, or correction of payment observations.

A newly discovered payment condition must be classified and assigned a disposition before affected derived measures are published without qualification.

### 3.10 Monetary reconciliation boundary

`fct_payments` preserves payment-side monetary evidence. It does not determine whether an order is financially reconciled.

Payment-to-item reconciliation occurs at the order grain after:

- payment values have been aggregated independently from `fct_payments`;
- item prices and freight values have been aggregated independently from `fct_order_items`;
- both summaries have been joined safely to `fct_orders`.

The payment fact must not:

- join directly to order-item rows for monetary aggregation;
- allocate payments across individual order items;
- overwrite payment values with item-derived values;
- infer missing payments from item totals;
- force payment and item totals to agree.

A zero-value payment contributes zero to `payment_total` but remains included in `payment_count`.

### 3.11 Join-amplification safeguards

Directly joining payment rows to order-item or review rows can multiply independent business events.

Unsafe detailed join:

```text
payments
    ×
order items
    ×
reviews
```

Required pattern:

```text
payments
    ↓
aggregate independently to the required grain
    ↓
combine with independently aggregated item or review measures
```

A controlled join from `fct_payments` to `fct_orders` must preserve the payment row count.

Any payment-type, installment, or order-level summary must declare its grain before being combined with another business process.

### 3.12 Payment anomaly dispositions

The applicable payment conditions receive the following canonical treatments:

| Condition | Canonical treatment |
| --- | --- |
| `payments_without_order` | Retain the payment and source order reference; set `order_key` to `NULL` and classify it as `missing_order` |
| `order_missing_sequence_one` | Preserve observed sequences; flag affected payments without renumbering or inferring rows |
| `zero_installment_credit_card` | Preserve the zero value, flag the payment, and do not infer an installment count |
| `zero_value_payment` | Preserve and flag the payment; include it in event counts and classify it separately from positive-value payments |
| Multiple payments for one order | Preserve every payment observation; aggregate explicitly for order-level analysis |
| Delivered order without payment | Preserve the order, classify its payment coverage as requiring review, and do not infer a payment |
| Payment total above item-based total | Preserve both totals; expose the reconciliation direction on `fct_orders` |
| Payment total below item-based total | Preserve both totals; expose the reconciliation direction on `fct_orders` |

Existing staging and relationship-quality controls remain responsible for monitoring changes to the validated payment-anomaly and relationship baselines.

### 3.13 Payment publication controls

`fct_payments` must enforce:

- one row per `payment_key`;
- one row per source namespace, `source_order_id`, and `source_payment_sequence`;
- non-null canonical and source identity columns;
- deterministic consistency between `payment_key` and its key inputs;
- preservation of the staged payment count;
- no row amplification during order resolution;
- valid `order_reference_status` values;
- a non-null, valid `fct_orders` reference whenever `order_reference_status` is `matched`;
- a `NULL` `order_key` whenever `order_reference_status` is `missing_order`;
- preservation of the source order identifier and payment sequence;
- `source_payment_sequence >= 1`;
- non-null normalized `payment_type`;
- `payment_installments >= 0`;
- a non-null exact numeric `payment_value`;
- `payment_value >= 0`;
- non-null Boolean values for every governed payment-quality indicator;
- exact consistency between each indicator and its underlying source condition;
- `has_payment_anomaly = TRUE` if and only if at least one governed payment-quality indicator is `TRUE`;
- preservation of multi-payment orders at the physical payment grain;
- no unintended consolidation or renumbering of payment observations.

A blocking canonical control must fail if:

- canonical processing changes the staged payment count unexpectedly;
- the implemented relation no longer conforms to its declared grain;
- a canonical key maps to more than one source key combination;
- a matched `order_key` does not resolve to `fct_orders`;
- a missing-order status is paired with a populated `order_key`;
- a source payment sequence is changed or lost;
- a required payment value is unavailable or negative;
- an anomaly indicator contradicts its underlying payment attributes;
- order resolution multiplies or removes payment rows.

Known payment anomalies governed by an approved non-blocking disposition remain publishable when their source values, lineage, and applicable quality indicators are preserved.

## 4. Review Fact and Feedback Semantics

### 4.1 Business responsibility and grain

`fct_reviews` represents distinct customer-feedback events supplied by the Olist source.

Its grain is:

```text
one row per source namespace and review_id
```

Its canonical primary key is:

```text
review_key
```

The key is generated deterministically from:

```text
key_version
    +
review entity type
    +
source_namespace
    +
source_review_id
```

The source relationship between reviews and orders is not part of the physical `fct_reviews` grain.

That relationship is represented separately through:

```text
bridge_order_reviews
```

This separation allows Mercury to:

- preserve one canonical review payload per source review identifier;
- retain every valid order–review association;
- avoid duplicating review measures when one review identifier is associated with multiple orders;
- preserve multiple distinct reviews associated with one order.

### 4.2 Core review columns

The initial `fct_reviews` columns include:

| Column | Responsibility |
| --- | --- |
| `review_key` | Canonical primary key |
| `source_namespace` | Namespace of the originating source instance |
| `source_review_id` | Preserved source `review_id` |
| `review_score` | Preserved source review score |
| `review_comment_title` | Preserved nullable review title |
| `review_comment_message` | Preserved nullable review message |
| `review_creation_timestamp` | Preserved review-creation timestamp |
| `review_answer_timestamp` | Preserved review-answer timestamp |
| `review_creation_date_key` | Review-creation date key referencing `dim_date` |
| `review_answer_date_key` | Review-answer date key referencing `dim_date` |
| `order_association_count` | Number of distinct order associations |
| `is_reused_review_id` | Review is associated with multiple orders |
| `is_reused_across_purchase_dates` | Associated orders have different purchase dates |
| `is_answer_before_creation` | Review answer precedes review creation |
| `has_review_anomaly` | At least one governed review anomaly applies |

`review_comment_title` and `review_comment_message` remain nullable because written feedback is optional.

### 4.3 Review identity and payload consolidation

The Olist staging relation has the grain:

```text
one row per review_id and order_id
```

A source `review_id` may therefore appear in more than one staged row because the same review payload may be associated with multiple orders.

`fct_reviews` consolidates those repeated associations to one review entity only when the governed review payload is consistent.

The governed payload includes:

```text
review_score
review_comment_title
review_comment_message
review_creation_timestamp
review_answer_timestamp
```

Before consolidation, Mercury must verify that one `source_review_id` does not map to multiple distinct governed payloads.

If repeated rows contain the same governed payload:

- one canonical review row is published;
- all distinct order associations are preserved in `bridge_order_reviews`;
- `order_association_count` records the number of associations;
- `is_reused_review_id` indicates whether the count exceeds one.

If one source review identifier maps to conflicting payloads, Mercury must not select one payload arbitrarily.

The affected identifier must be flagged and prevented from unreviewed consolidation until an explicit disposition is approved.

### 4.4 Review-score semantics

`review_score` preserves the source-provided feedback score.

The accepted Olist domain is:

```text
1
2
3
4
5
```

A higher score represents more positive feedback.

Mercury must not:

- average multiple review scores into one physical review row;
- overwrite an earlier review with a later review;
- select only the highest, lowest, earliest, or latest score without an explicit downstream contract;
- interpret the score as a product-only measure when the review is associated with an order containing multiple products or sellers.

When an order is associated with multiple distinct review scores, every review event and association must remain available.

Downstream order-level feedback models must declare their selection or aggregation semantics explicitly.

### 4.5 Review-text semantics

`review_comment_title` and `review_comment_message` preserve the normalized nullable text supplied through staging.

An absent title or message does not make the review invalid.

Mercury must not:

- generate text for a review with no written comment;
- interpret missing text as negative or positive feedback;
- replace one review’s text with text from another associated review;
- combine different review messages into one canonical payload without an explicit downstream contract.

Text-derived sentiment, topic, language, or classification outputs belong in governed downstream data products or feature models. They are not part of the initial canonical review fact.

### 4.6 Review temporal roles

`fct_reviews` preserves:

```text
review_creation_timestamp
review_answer_timestamp
```

The corresponding role-specific date keys are:

| Date key                   | Derived from                |
| -------------------------- | --------------------------- |
| `review_creation_date_key` | `review_creation_timestamp` |
| `review_answer_date_key`   | `review_answer_timestamp`   |

Both date keys reference `dim_date`.

The timestamps remain the authoritative temporal values. Date keys support calendar-based analysis and do not replace timestamp precision.

Review chronology is valid when:

```text
review_answer_timestamp >= review_creation_timestamp
```

The response duration may be derived as:

```text
review_response_seconds =
    review_answer_timestamp - review_creation_timestamp
```

It may be published only when both timestamps are available and their chronology is valid.

When the answer timestamp precedes the creation timestamp:

- both source-derived timestamps remain unchanged;
- `is_answer_before_creation` is `TRUE`;
- `review_response_seconds` is `NULL`;
- the review and its order associations remain available;
- analyses requiring valid response chronology must exclude or separately classify the review.

Mercury must not alter either timestamp to create plausible chronology.

### 4.7 Order-association behavior

One review may be associated with multiple orders, and one order may be associated with multiple reviews.

These relationships are preserved through:

```text
bridge_order_reviews
```

`order_association_count` is derived from the number of distinct staged `(order_id, review_id)` associations for the review.

The current validated source contains review identifiers associated with:

- two orders;
- three orders;
- orders purchased within a short time window;
- orders purchased on different calendar dates.

A reused review identifier does not, by itself, prove that duplicate review rows exist or that one association is invalid.

Mercury must preserve all validated associations until source evidence supports a different disposition.

### 4.8 Reuse across purchase occasions

`is_reused_across_purchase_dates` indicates that one source review identifier is associated with orders having more than one distinct purchase date.

This condition provides visibility into review reuse across potentially separate purchase occasions.

It does not authorize Mercury to:

- duplicate the canonical review payload;
- delete an order association;
- select one order as the definitive parent;
- infer which association was intended by the source;
- assign the review to one product or seller arbitrarily.

Customer-level or purchase-occasion feedback outputs must explicitly account for this condition before using an affected review.

### 4.9 Multiple reviews per order

An order may have more than one distinct review association.

Different reviews associated with the same order may contain:

- different scores;
- different creation dates;
- different answer timestamps;
- different titles;
- different messages.

These differences may represent distinct feedback events, including feedback supplied after additional product use.

Mercury must preserve each review entity and every order–review association.

The initial canonical layer does not designate one review as:

- the current review;
- the final review;
- the primary review;
- the authoritative review.

A downstream model requiring one review per order must define an explicit selection rule and expose the effect of that rule.

### 4.10 Review-quality indicators

The governed review-quality indicators are:

| Column | Meaning |
| --- | --- |
| `is_reused_review_id` | Review identifier has multiple order associations |
| `is_reused_across_purchase_dates` | Associated orders have different purchase dates |
| `is_answer_before_creation` | Review answer precedes review creation |
| `has_review_anomaly` | At least one governed warning-level anomaly applies |

The aggregate anomaly indicator follows:

```text
has_review_anomaly =
    is_reused_across_purchase_dates
    OR is_answer_before_creation
```

`is_reused_review_id` remains an informational relationship indicator. Reuse alone does not necessarily represent a quality anomaly.

A source review identifier associated with inconsistent payloads cannot be represented safely at the declared `fct_reviews` grain. That condition is enforced through a blocking consolidation control rather than encoded as a published review-row flag.

### 4.11 Join-amplification safeguards

`fct_reviews` must not be joined directly to order-item or payment rows when the resulting relation would multiply independent observations.

Unsafe detailed join:

```text
reviews
    ×
order items
    ×
payments
```

Required pattern:

```text
reviews
    ↓
bridge_order_reviews
    ↓
aggregate to the required order or review grain
    ↓
combine with independently aggregated measures
```

Review counts must distinguish between:

```text
distinct review entities
```

and:

```text
distinct order–review associations
```

`COUNT(review_key)` after an uncontrolled join must not be treated as a review-event measure.

### 4.12 Review anomaly dispositions

The applicable review conditions receive the following canonical treatments:

| Condition | Canonical treatment |
| --- | --- |
| `reviews_without_order` | Retain the review; exclude it only from outputs requiring a resolved order |
| `delivered_orders_without_review` | Retain the order and classify its review coverage as absent |
| `orders_with_multiple_distinct_review_scores` | Retain every review event; require explicit downstream selection or aggregation |
| `reused_review_ids_with_inconsistent_payloads` | Preserve source observations; prevent unreviewed consolidation |
| `reused_review_ids_across_customers` | Preserve associations; prevent unreviewed customer-level use |
| `reused_review_ids_across_purchase_dates` | Preserve all associations and expose cross-occasion reuse |
| Review answer before review creation | Preserve both timestamps, flag the anomaly, and suppress the response duration |
| Missing review title or message | Retain the review; treat optional text absence as valid |

Existing staging and relationship-quality controls remain responsible for monitoring changes to review chronology, identity, coverage, and reuse baselines.

### 4.13 Review publication controls

`fct_reviews` must enforce:

- one row per `review_key`;
- one row per source namespace and `source_review_id`;
- non-null canonical and source identity columns;
- deterministic consistency between `review_key` and its key inputs;
- one governed payload per source review identifier;
- no arbitrary selection among conflicting payloads;
- an accepted `review_score`;
- preservation of nullable review title and message values;
- preservation of review creation and answer timestamps;
- valid `dim_date` references for every populated review date key;
- deterministic consistency between each timestamp and its date key;
- non-negative `review_response_seconds` whenever the duration is published;
- a `NULL` response duration whenever review chronology is invalid;
- non-null Boolean values for every governed review-quality indicator;
- consistency between `order_association_count` and `is_reused_review_id`;
- consistency between each anomaly indicator and its underlying evidence;
- `has_review_anomaly = TRUE` if and only if at least one governed warning-level review anomaly applies;
- no duplication of review entities caused by order associations;
- no loss of valid order–review associations during review consolidation.

A blocking canonical control must fail if:

- one source review identifier maps to multiple governed payloads without an approved disposition;
- a canonical review key maps to more than one source review identifier;
- the implemented relation no longer conforms to its declared grain;
- a required review identity or score is unavailable;
- a populated date key does not resolve to `dim_date`;
- a published response duration contradicts the source chronology;
- review consolidation selects an arbitrary payload;
- order-association processing multiplies or removes canonical review rows.

Known review conditions governed by an approved non-blocking disposition remain publishable when their source evidence, lineage, and applicable indicators are preserved.

## 5. Order–Review Bridge Contract

### 5.1 Business responsibility and grain

`bridge_order_reviews` preserves the many-to-many-capable relationship between canonical orders and canonical reviews.

Its grain is:

```text
one row per order_key and review_key
```

The bridge uses the compound canonical relationship key directly:

```text
(order_key, review_key)
```

It does not require an additional generated surrogate key.

The corresponding source relationship is:

```text
one row per source namespace, order_id, and review_id
```

The bridge exists because:

- one order may be associated with multiple distinct reviews;
- one review identifier may be associated with multiple orders;
- neither relationship can be represented safely by storing a single foreign key on `fct_orders` or `fct_reviews`;
- review payloads and order attributes must remain at their own declared grains.

### 5.2 Core bridge columns

The initial `bridge_order_reviews` columns include:

| Column             | Responsibility                               |
| ------------------ | -------------------------------------------- |
| `order_key`        | Foreign key to `fct_orders`                  |
| `review_key`       | Foreign key to `fct_reviews`                 |
| `source_namespace` | Namespace of the originating source instance |
| `source_order_id`  | Preserved source `order_id`                  |
| `source_review_id` | Preserved source `review_id`                 |

The bridge contains relationship lineage only.

Review scores, text, and timestamps remain in `fct_reviews`. Order lifecycle, customer, coverage, and reconciliation attributes remain in `fct_orders`.

### 5.3 Source-to-canonical resolution

Each staged order–review association is resolved through both sides of the relationship.

Order resolution follows:

```text
stg_reviews.order_id
        ↓
fct_orders.source_order_id
        ↓
fct_orders.order_key
```

Review resolution follows:

```text
stg_reviews.review_id
        ↓
fct_reviews.source_review_id
        ↓
fct_reviews.review_key
```

A bridge row is publishable only when both canonical parent keys resolve.

The source identifiers remain on the bridge so each canonical association can be traced back to its staged representation.

### 5.4 Relationship preservation

Every distinct staged `(order_id, review_id)` association must remain represented when both canonical parents are publishable.

Mercury must not:

- select only one review for an order with multiple reviews;
- select only one order for a review associated with multiple orders;
- duplicate a review payload for every order association;
- merge multiple review identifiers into one review entity;
- infer an order–review relationship that does not exist in staging;
- delete an association merely because the review identifier is reused;
- treat a repeated review identifier as proof that an association is invalid.

The bridge records associations. It does not determine which review should be considered current, primary, final, or authoritative.

### 5.5 Multiple reviews per order

An order may be associated with more than one canonical review.

These reviews may contain different:

- scores;
- creation timestamps;
- answer timestamps;
- titles;
- messages.

Every distinct review and relationship remains available.

Joining `fct_orders` to `bridge_order_reviews` changes the result from order grain to order–review-association grain when an order has multiple reviews.

A downstream model requiring one row per order must aggregate or select review associations explicitly before joining them to an order-grain output.

Mercury must not select one review arbitrarily.

### 5.6 Reviews associated with multiple orders

A canonical review may be associated with more than one canonical order.

All validated associations remain in `bridge_order_reviews`.

Joining `fct_reviews` to the bridge changes the result from review grain to order–review-association grain when a review has multiple order associations.

A downstream model requiring one row per review must aggregate its order relationships or preserve the review grain separately.

Review reuse across different purchase dates remains visible through the governed indicator on `fct_reviews` and the preserved bridge associations.

### 5.7 Missing-reference behavior

A canonical bridge row requires both:

```text
order_key
review_key
```

If a staged review does not resolve to a canonical order:

- the canonical review remains available in `fct_reviews`;
- its source review payload remains preserved;
- no canonical order–review bridge row is fabricated;
- the unresolved source association remains visible through the applicable relationship-quality control;
- the review is excluded only from outputs requiring a resolved order.

If a staged association cannot resolve to a canonical review because review consolidation is blocked:

- the source association remains preserved in staging;
- no bridge row is published for the unresolved review;
- publication of the affected relationship remains blocked until the review-identity condition receives an approved disposition.

Mercury must not publish a bridge row containing a `NULL` parent key.

### 5.8 Relationship-count semantics

The bridge supports two different counts:

```text
reviews per order =
    COUNT(DISTINCT review_key)
    grouped by order_key
```

and:

```text
orders per review =
    COUNT(DISTINCT order_key)
    grouped by review_key
```

These counts describe different relationship directions and must not be used interchangeably.

The following measures also remain distinct:

```text
canonical review entities
```

and:

```text
canonical order–review associations
```

A review associated with multiple orders contributes:

- one row to `fct_reviews`;
- one bridge row for each distinct resolved order association.

An order associated with multiple reviews contributes:

- one row to `fct_orders`;
- one bridge row for each distinct resolved review association.

### 5.9 Join-amplification safeguards

The bridge intentionally expands parent entities to relationship grain.

Safe order-to-review traversal is:

```text
fct_orders
    ↓
bridge_order_reviews
    ↓
fct_reviews
```

The resulting grain is:

```text
one row per order_key and review_key
```

This join must not be combined directly with detailed order-item or payment rows when measures from those business processes are being aggregated.

Unsafe detailed join:

```text
order items
    ×
payments
    ×
bridge_order_reviews
    ×
reviews
```

Required pattern:

```text
each business process
    ↓
aggregate independently to the required grain
    ↓
combine the resulting summaries
```

A downstream order-grain model must aggregate review measures to one row per `order_key` before joining them to order-level item or payment summaries.

A downstream review-grain model must aggregate order relationships to one row per `review_key`.

### 5.10 Relationship anomaly dispositions

The applicable relationship conditions receive the following canonical treatments:

| Condition | Canonical treatment |
| --- | --- |
| `reviews_without_order` | Preserve the review in `fct_reviews`; do not fabricate a bridge association |
| `delivered_orders_without_review` | Preserve the order; do not create a synthetic review or bridge row |
| `orders_with_multiple_distinct_review_scores` | Preserve every distinct review and order–review association |
| `reused_review_ids_with_inconsistent_payloads` | Preserve source observations; block unreviewed review consolidation |
| `reused_review_ids_across_customers` | Preserve associations; prevent unreviewed customer-level attribution |
| `reused_review_ids_across_purchase_dates` | Preserve every association and expose cross-occasion reuse |
| Duplicate source order–review association | Preserve source evidence; prevent duplicate canonical bridge rows |
| Missing canonical review parent | Withhold the bridge row until review identity is resolved safely |

Existing staging and relationship-quality controls remain responsible for monitoring changes to review coverage, identity, cardinality, and reuse baselines.

### 5.11 Bridge publication controls

`bridge_order_reviews` must enforce:

- one row per compound `(order_key, review_key)` relationship;
- one row per source namespace, `source_order_id`, and `source_review_id`;
- non-null `order_key` and `review_key`;
- non-null source namespace and relationship identifiers;
- a valid `fct_orders` reference for every `order_key`;
- a valid `fct_reviews` reference for every `review_key`;
- deterministic consistency between each canonical key and its preserved source identifier;
- preservation of every distinct staged association whose canonical parents are publishable;
- no inferred canonical association without staged relationship evidence;
- no duplication caused by parent joins;
- no arbitrary removal of associations involving reused review identifiers;
- no review-payload columns copied into the bridge;
- no order-level measures copied into the bridge.

A blocking canonical control must fail if:

- a bridge row contains a `NULL` parent key;
- a parent key does not resolve to its declared canonical relation;
- the same canonical order–review relationship appears more than once;
- the same source association maps to multiple canonical relationships;
- a canonical relationship maps to multiple source-identifier combinations;
- a publishable staged association is lost;
- an association is created without source relationship evidence;
- joining the bridge to either parent unexpectedly duplicates the bridge relationship;
- the implemented relation no longer conforms to its declared grain.

Known relationship conditions governed by an approved non-blocking disposition remain publishable when their source lineage, parent references, and full set of valid associations are preserved.