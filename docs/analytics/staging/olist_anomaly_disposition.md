# Olist Anomaly Disposition Register

## Status

Active

## Date

2026-09-01

## Purpose

This document records the operational and analytical dispositions for data-quality controls implemented for Mercury's Olist staging layer.

It applies the platform-wide policy defined by:

- [ADR-012: Staging Layer Standardization and Semantic Contracts](../../../architecture/decisions/ADR-012-Staging%20Layer%20Standardization%20and%20Semantic%20Contracts.md);
- [ADR-013: Data Quality Anomaly Disposition and Monitoring Contract](../../../architecture/decisions/ADR-013-Data%20Quality%20Anomaly%20Disposition%20and%20Monitoring%20Contract.md).

The schemas, grains, semantic types, normalization rules, and structural expectations remain defined in the [Olist staging contracts](olist_staging_contracts.md).

This register does not redefine those contracts. It documents what Mercury must do when a control fails or an Olist source anomaly is detected.

---

## 1. Scope

This register covers:

- all blocking Dataform assertions implemented for the eight Olist staging models;
- all non-blocking quality views implemented for the Olist staging layer;
- current validated anomaly baselines;
- downstream analytical dispositions;
- initial severity and notification requirements;
- engineer response expectations;
- controls that currently report zero anomalies;
- future relationship anomalies discovered during Phase 3.6.

This register does not define:

- the complete quality-history schema;
- deployed alerting infrastructure;
- notification channels;
- canonical model implementation;
- relationship findings that have not yet been profiled.

Those implementation details will be documented when they enter active implementation scope.

---

## 2. Current Implementation Position

The Olist quality implementation currently includes:

- 8 staging tables;
- 21 blocking Dataform assertions;
- 5 non-blocking quality views;
- successful compilation of the complete Dataform graph;
- successful BigQuery dry runs;
- successful execution under the dedicated Dataform transformation identity;
- zero failures across all blocking controls.

The non-blocking quality views are:

| Quality view | Purpose |
|---|---|
| `dq_orders_lifecycle_anomalies` | Surfaces invalid or incomplete order lifecycle chronology |
| `dq_products_anomalies` | Surfaces incomplete catalog and physical product data |
| `dq_payments_anomalies` | Surfaces unusual payment sequencing and values |
| `dq_reviews_chronology_anomalies` | Surfaces invalid review chronology |
| `dq_geolocations_duplicate_observations` | Surfaces repeated geolocation observations |

Detection is implemented.

Historical persistence, baseline evaluation, automated notification, and canonical disposition logic remain planned.

---

## 3. Control Types

### Blocking controls

Blocking controls enforce the minimum structural and semantic contract required to publish a staging relation.

A blocking failure requires:

1. failure of the affected Dataform workflow;
2. prevention of dependent publication;
3. engineer notification;
4. inspection of the source and transformation;
5. correction of the source, contract, or transformation where appropriate;
6. successful re-execution before publication resumes.

The approved baseline and threshold for every blocking control is:

```text
Expected failing rows: 0
Alert threshold: any failing row
Execution failure: critical unknown quality state
```

### Non-blocking monitors

Non-blocking monitors surface source conditions that do not invalidate the complete staging relation but may affect specific downstream uses.

A non-blocking finding requires:

1. preservation of the staged source record;
2. historical recording of the evaluation;
3. comparison with the approved baseline;
4. notification when its alert condition is met;
5. application of the documented downstream disposition;
6. retention of traceability to the staged and Raw source values.

---

## 4. Blocking Control Register

All blocking controls have an initial severity of `Critical`, an expected failing-row count of zero, and an alert threshold of any failing row or failure of the control itself.

### Customers

| Control ID | Dataform action | Contract protected |
|---|---|---|
| `OLIST-CUSTOMERS-KEY-001` | `staging_stg_customers_assertions_uniqueKey_0` | `customer_id` uniqueness |
| `OLIST-CUSTOMERS-STRUCTURE-001` | `staging_stg_customers_assertions_rowConditions` | Required values, ZIP-prefix format, and state-code format |

### Geolocations

| Control ID | Dataform action | Contract protected |
|---|---|---|
| `OLIST-GEOLOCATIONS-CAST-001` | `assert_stg_geolocations_cast_validity` | Latitude and longitude semantic cast validity |
| `OLIST-GEOLOCATIONS-STRUCTURE-001` | `staging_stg_geolocations_assertions_rowConditions` | Required values, formats, coordinate domains, and normalization |

Geolocations deliberately have no uniqueness assertion because the source grain permits repeated observations.

### Order items

| Control ID | Dataform action | Contract protected |
|---|---|---|
| `OLIST-ORDER-ITEMS-CAST-001` | `assert_stg_order_items_cast_validity` | Integer, timestamp, and monetary cast validity |
| `OLIST-ORDER-ITEMS-KEY-001` | `staging_stg_order_items_assertions_uniqueKey_0` | Compound-key uniqueness of `order_id` and `order_item_id` |
| `OLIST-ORDER-ITEMS-STRUCTURE-001` | `staging_stg_order_items_assertions_rowConditions` | Required values and numeric-domain rules |

### Orders

| Control ID | Dataform action | Contract protected |
|---|---|---|
| `OLIST-ORDERS-TEMPORAL-001` | `assert_stg_orders_temporal_parseability` | Timestamp and date parseability |
| `OLIST-ORDERS-KEY-001` | `staging_stg_orders_assertions_uniqueKey_0` | `order_id` uniqueness |
| `OLIST-ORDERS-STRUCTURE-001` | `staging_stg_orders_assertions_rowConditions` | Required values and normalized order status |

### Payments

| Control ID | Dataform action | Contract protected |
|---|---|---|
| `OLIST-PAYMENTS-CAST-001` | `assert_stg_payments_cast_validity` | Sequence, installment, and monetary cast validity |
| `OLIST-PAYMENTS-KEY-001` | `staging_stg_payments_assertions_uniqueKey_0` | Compound-key uniqueness of `order_id` and `payment_sequential` |
| `OLIST-PAYMENTS-STRUCTURE-001` | `staging_stg_payments_assertions_rowConditions` | Required values, normalized payment types, and numeric domains |

### Products

| Control ID | Dataform action | Contract protected |
|---|---|---|
| `OLIST-PRODUCTS-CAST-001` | `assert_stg_products_cast_validity` | Count and measurement cast validity |
| `OLIST-PRODUCTS-KEY-001` | `staging_stg_products_assertions_uniqueKey_0` | `product_id` uniqueness |
| `OLIST-PRODUCTS-STRUCTURE-001` | `staging_stg_products_assertions_rowConditions` | Required identifiers, normalized categories, and numeric domains |

### Reviews

| Control ID | Dataform action | Contract protected |
|---|---|---|
| `OLIST-REVIEWS-CAST-001` | `assert_stg_reviews_cast_validity` | Score, date, and timestamp cast validity |
| `OLIST-REVIEWS-KEY-001` | `staging_stg_reviews_assertions_uniqueKey_0` | Compound-key uniqueness of `review_id` and `order_id` |
| `OLIST-REVIEWS-STRUCTURE-001` | `staging_stg_reviews_assertions_rowConditions` | Required values and review-score domain |

### Sellers

| Control ID | Dataform action | Contract protected |
|---|---|---|
| `OLIST-SELLERS-KEY-001` | `staging_stg_sellers_assertions_uniqueKey_0` | `seller_id` uniqueness |
| `OLIST-SELLERS-STRUCTURE-001` | `staging_stg_sellers_assertions_rowConditions` | Required values, ZIP-prefix format, state-code format, and normalization |

---

## 5. Common Blocking-Control Playbook

When any blocking control reports a failing row or fails to execute, the responsible engineer must:

1. identify the affected control and Dataform execution;
2. inspect the failing staged records;
3. compare them with the source-faithful Raw values;
4. determine whether the cause is:
   - a new source condition;
   - an ingestion defect;
   - a staging transformation defect;
   - an incorrect or outdated contract;
   - failure of the quality control itself;
5. determine which downstream relations may be affected;
6. correct the source, transformation, or contract through an explicit reviewed change;
7. rerun the affected staging model and its assertions;
8. confirm that the blocking control passes before dependent publication resumes;
9. record any approved contract or baseline change.

Mercury must not interpret a control execution failure as a zero-anomaly result.

---

## 6. Non-Blocking Anomaly Register

The baselines below describe the validated Olist source snapshot. They are not automatically accepted as permanent future baselines.

An unchanged approved baseline does not require repeated actionable notification. A new anomaly type, increase beyond the approved baseline, increased anomaly rate, or failure of a monitor to execute requires evaluation.

### 6.1 Order lifecycle anomalies

Source relation:

```text
staging.stg_orders
```

Quality view:

```text
staging.dq_orders_lifecycle_anomalies
```

| Control ID | Anomaly type | Baseline | Severity | Disposition |
|---|---|---:|---|---|
| `OLIST-ORDERS-LIFECYCLE-001` | `carrier_before_purchase` | 166 | Warning | Retain and flag; exclude from chronology calculations requiring carrier time to follow purchase |
| `OLIST-ORDERS-LIFECYCLE-002` | `customer_before_carrier` | 23 | Warning | Retain and flag; exclude from carrier-to-customer delivery-duration calculations |
| `OLIST-ORDERS-LIFECYCLE-003` | `delivered_missing_approval` | 14 | Warning | Retain and flag; do not infer an approval timestamp |
| `OLIST-ORDERS-LIFECYCLE-004` | `delivered_missing_carrier_delivery` | 2 | Warning | Retain and flag; exclude from calculations requiring carrier-delivery time |
| `OLIST-ORDERS-LIFECYCLE-005` | `delivered_missing_customer_delivery` | 8 | Warning | Retain and flag; do not infer customer-delivery time from order status |

#### Analytical impact

These records remain valid for uses that do not require complete and ordered lifecycle timestamps, including:

- order counts;
- customer-order relationships;
- order-item relationships;
- payment reconciliation;
- product and seller analysis.

They are not automatically valid for:

- approval-duration calculations;
- dispatch-duration calculations;
- carrier-delivery duration;
- total delivery duration;
- late-delivery analysis requiring actual delivery timestamps.

#### Alert condition

Notify when:

- a new lifecycle anomaly type appears;
- the count or rate of an existing type exceeds its approved baseline;
- a previously zero-result lifecycle condition becomes positive;
- the quality view fails to execute.

#### Response

The engineer must determine whether the change originates in source lifecycle data or Mercury timestamp logic and identify affected duration-based models.

No lifecycle timestamp may be invented or reordered.

---

### 6.2 Product anomalies

Source relation:

```text
staging.stg_products
```

Quality view:

```text
staging.dq_products_anomalies
```

| Control ID | Anomaly type | Baseline | Severity | Disposition |
|---|---|---:|---|---|
| `OLIST-PRODUCTS-METADATA-001` | `missing_catalog_metadata` | 610 | Informational | Retain; preserve nullable attributes; use an explicit unknown category only in a downstream consumption contract |
| `OLIST-PRODUCTS-MEASUREMENT-001` | `missing_physical_measurement` | 2 | Warning | Retain and flag; exclude from calculations requiring complete physical measurements |
| `OLIST-PRODUCTS-WEIGHT-001` | `zero_product_weight` | 4 | Warning | Retain and flag; exclude from calculations requiring positive product weight |

#### Analytical impact

Products with incomplete metadata remain valid for:

- order-item counts;
- revenue and price analysis;
- seller-product relationships;
- product-identifier-level analysis.

They may be unsuitable for:

- category segmentation;
- catalog completeness metrics;
- weight-based logistics analysis;
- volume or dimensional analysis.

#### Alert condition

Notify when:

- a new product anomaly type appears;
- an existing count or rate exceeds its approved baseline;
- the quality view fails to execute.

Missing catalog metadata may remain informational while unchanged. Missing or zero physical measurements require warning-level evaluation when they increase.

#### Response

The engineer must determine whether missing attributes reflect legitimate source incompleteness, a changed source schema, or a transformation regression.

Mercury must not invent product attributes or replace zero measurements with plausible values.

---

### 6.3 Payment anomalies

Source relation:

```text
staging.stg_payments
```

Quality view:

```text
staging.dq_payments_anomalies
```

| Control ID | Anomaly type | Baseline | Severity | Disposition |
|---|---|---:|---|---|
| `OLIST-PAYMENTS-SEQUENCE-001` | `order_missing_sequence_one` | 80 orders | Warning | Retain; do not renumber payment sequences; flag the affected order |
| `OLIST-PAYMENTS-INSTALLMENTS-001` | `zero_installment_credit_card` | 2 payments | Warning | Retain and flag; do not infer an installment count |
| `OLIST-PAYMENTS-ZERO-VALUE-001` | `zero_value_payment` | 9 payments | Warning | Retain and flag; evaluate separately from positive-value payment totals |

The zero-value payment baseline consists of:

| Payment type | Baseline |
|---|---:|
| `not_defined` | 3 |
| `voucher` | 6 |

#### Analytical impact

Affected payment records remain valid source observations.

They require care in:

- payment-method analysis;
- payment-sequence interpretation;
- installment analysis;
- order-value reconciliation;
- revenue or collected-value calculations.

#### Alert condition

Notify when:

- a new payment anomaly type or payment-type combination appears;
- an existing anomaly count or rate exceeds its approved baseline;
- an order previously expected to contain sequence one does not;
- the quality view fails to execute.

#### Response

The engineer must compare affected payments with their related orders and order items during relationship exploration.

Mercury must not:

- renumber payment sequences;
- replace zero installments with one;
- replace zero payment values;
- infer missing payment records.

Canonical payment and order models must expose the relevant flags and avoid join amplification before monetary reconciliation is considered valid.

---

### 6.4 Review chronology anomalies

Source relation:

```text
staging.stg_reviews
```

Quality view:

```text
staging.dq_reviews_chronology_anomalies
```

| Control ID | Anomaly type | Baseline | Severity | Disposition |
|---|---|---:|---|---|
| `OLIST-REVIEWS-CHRONOLOGY-001` | Answer timestamp before creation date | 0 | Warning | Retain and flag; exclude from response-time calculations |

#### Analytical impact

A future affected review may remain valid for:

- review counts;
- score analysis;
- order-review relationships;
- textual analysis.

It would not be valid for response-time calculations requiring chronological consistency.

#### Alert condition

Any detected occurrence must trigger notification because the approved baseline is zero.

Failure of the quality view to execute must produce an unknown quality state rather than a zero result.

#### Response

The engineer must inspect the Raw date and timestamp values and confirm whether the issue originated in the source or transformation logic.

Mercury must not alter either timestamp to create plausible chronology.

---

### 6.5 Geolocation duplicate observations

Source relation:

```text
staging.stg_geolocations
```

Quality view:

```text
staging.dq_geolocations_duplicate_observations
```

| Control ID | Anomaly type | Baseline | Severity | Disposition |
|---|---|---:|---|---|
| `OLIST-GEOLOCATIONS-DUPLICATES-001` | Repeated normalized geolocation observations | 261,831 duplicate observations | Informational | Preserve staging grain; aggregate or resolve to a documented geographic grain before enrichment |

Supporting baseline:

| Metric | Baseline |
|---|---:|
| Total staging observations | 1,000,163 |
| Distinct normalized observations | 738,332 |
| Duplicated combinations | 128,174 |
| Observations in duplicated combinations | 390,005 |
| Duplicate observations beyond the first | 261,831 |

#### Analytical impact

The staging table must not be joined directly into customer, seller, order, or canonical facts through ZIP prefix because:

- ZIP prefix is not unique;
- repeated observations are source-valid at staging grain;
- direct joins would multiply business records;
- coordinates may vary within a ZIP prefix.

A downstream geographic preparation model must define:

- its target grain;
- coordinate-resolution or aggregation logic;
- treatment of multiple cities or states associated with a ZIP prefix;
- traceability to the source observations.

#### Alert condition

An unchanged approved duplicate profile does not require repeated notification.

Notify when:

- the duplicate-observation rate increases beyond its approved baseline;
- a new duplicate pattern affects the future resolution rule;
- the quality view fails to execute.

#### Response

The engineer must confirm that duplicate changes reflect source observations rather than an ingestion replay or transformation defect.

Mercury must not apply `SELECT DISTINCT` to staging merely to remove the duplicates.

---

### 6.6 Customer–order relationship anomalies

Source relations:

```text
staging.stg_customers
staging.stg_orders
```

Quality view:

   staging.dq_customer_order_relationship_anomalies

| Control ID | Anomaly type | Baseline | Severity | Disposition |
|---|---|---:|---|---|
| `OLIST-CUSTOMER-ORDER-COVERAGE-001` | `orders_without_customer` | 0 | Warning | Preserve and flag the staged order; prevent unreviewed use in customer-dependent canonical outputs. |
| `OLIST-CUSTOMER-ORDER-COVERAGE-002` | `customers_without_order` | 0 | Warning | Preserve and flag the customer record; exclude it only from analyses requiring an associated order. |
| `OLIST-CUSTOMER-ORDER-CARDINALITY-001` | `customer_ids_with_multiple_orders` | 0 | Warning | Preserve and flag affected records; investigate whether source identity semantics have changed. |

#### Analytics Impact

The current zero baselines confirm that:

- every staged order matches one staged customer record;
- every staged customer record matches one staged order;
- each customer_id is associated with exactly one order;
- joining customers and orders through customer_id preserves order grain.

The separate customer_unique_id represents persistent customer identity and may legitimately relate to multiple orders.

#### Alert Condition

Any positive result must trigger notification because all three approved baselines are zero.

Failure of the quality view to execute must produce an unknown quality state rather than a zero-anomaly result.

Response

The engineer must:

- 1. inspect the affected customer and order records;
- 2. compare the relationship keys with their Raw representations;
- 3. determine whether the condition results from source behavior, incomplete ingestion, or transformation logic;
- 4. identify customer-dependent canonical outputs that may be affected;
- 5. apply the documented disposition without deleting or silently rewriting staging records;
- 6. review the Olist identity contract if customer_id semantics have changed.

Mercury must not silently create customer relationships, replace identifiers, or discard unmatched records.

---

### 6.7 Order–order-item relationship anomalies

Source relations:

```text
staging.stg_orders
staging.stg_order_items
```

Quality view:

```text
staging.dq_order_order_item_relationship_anomalies
```

| Control ID | Anomaly type | Baseline | Severity | Disposition |
|---|---|---:|---|---|
| `OLIST-ORDER-ITEM-COVERAGE-001` | `items_without_order` | 0 | Warning | Preserve and flag the item; prevent unreviewed use in order-dependent canonical outputs. |
| `OLIST-ORDER-ITEM-COVERAGE-002` | `approved_orders_without_items` | 0 | Warning | Preserve and flag the order; exclude it from item-dependent outputs until investigated. |
| `OLIST-ORDER-ITEM-COVERAGE-003` | `invoiced_orders_without_items` | 2 | Warning | Preserve and flag the order; retain order-level evidence but prevent item-dependent reconciliation. |
| `OLIST-ORDER-ITEM-COVERAGE-004` | `processing_orders_without_items` | 0 | Warning | Preserve and flag the order; exclude it from item-dependent outputs until investigated. |
| `OLIST-ORDER-ITEM-COVERAGE-005` | `shipped_orders_without_items` | 1 | Warning | Preserve and flag the order; retain fulfilment evidence but prevent item-dependent reconciliation. |
| `OLIST-ORDER-ITEM-COVERAGE-006` | `delivered_orders_without_items` | 0 | Warning | Preserve and flag the order; exclude it from item-dependent outputs until investigated. |
| `OLIST-ORDER-ITEM-SEQUENCE-001` | `orders_missing_item_id_one` | 0 | Warning | Preserve and flag affected items; do not renumber the source sequence. |
| `OLIST-ORDER-ITEM-SEQUENCE-002` | `orders_with_non_contiguous_item_ids` | 0 | Warning | Preserve and flag affected items; do not invent missing sequence values. |

#### Analytical impact

The current relationship profile confirms that:

- every staged order item matches a staged order;
- order-item identifiers begin at one and remain contiguous within each order;
- orders may legitimately contain multiple items;
- joining orders to order items changes the result from order grain to order-item grain;
- `created`, `canceled`, and `unavailable` orders may legitimately have no item records;
- two invoiced orders and one shipped order have no Raw or staged item records despite having approved positive payments and reviews;
- the shipped itemless order also contains a carrier-delivery timestamp.

Orders without expected item records cannot support:

- product attribution;
- seller attribution;
- item-price calculation;
- freight calculation;
- item-count calculation;
- reconciliation between payment value and item-level order value.

They may remain usable for order-level lifecycle, payment, customer, and review analysis when the missing item relationship is explicitly flagged.

#### Alert condition

Notify when:

- `items_without_order` becomes positive;
- any currently zero active-status control becomes positive;
- the invoiced or shipped baseline increases;
- a new active order status appears without items;
- an item sequence no longer begins at one;
- an item sequence becomes non-contiguous;
- the quality view fails to execute.

Unchanged itemless `created`, `canceled`, and `unavailable` orders do not require an actionable alert solely because they lack items.

#### Response

The engineer must:

1. inspect the affected orders and items in staging and Raw;
2. determine whether the cause is missing source data, incomplete ingestion, or transformation behavior;
3. inspect related payments, lifecycle timestamps, and reviews;
4. identify item-, product-, seller-, price-, and freight-dependent outputs;
5. preserve the order and all available related evidence;
6. prevent unreviewed item-dependent use until the condition is understood;
7. avoid fabricating products, sellers, prices, freight values, or item sequences.

Mercury must not delete itemless orders or infer missing line items from payment totals.

---

### 6.8 Order–payment relationship anomalies

Source relations:

```text
staging.stg_orders
staging.stg_payments
```

Quality view:

```text
staging.dq_order_payment_relationship_anomalies
```

| Control ID | Anomaly type | Baseline | Severity | Disposition |
|---|---|---:|---|---|
| `OLIST-ORDER-PAYMENT-COVERAGE-001` | `payments_without_order` | 0 | Warning | Preserve and flag the payment; prevent unreviewed use in order-dependent canonical outputs. |
| `OLIST-ORDER-PAYMENT-COVERAGE-002` | `approved_orders_without_payments` | 0 | Warning | Preserve and flag the order; exclude it from payment-dependent outputs until investigated. |
| `OLIST-ORDER-PAYMENT-COVERAGE-003` | `invoiced_orders_without_payments` | 0 | Warning | Preserve and flag the order; prevent unreviewed payment and collected-value interpretation. |
| `OLIST-ORDER-PAYMENT-COVERAGE-004` | `processing_orders_without_payments` | 0 | Warning | Preserve and flag the order; exclude it from payment-dependent outputs until investigated. |
| `OLIST-ORDER-PAYMENT-COVERAGE-005` | `shipped_orders_without_payments` | 0 | Warning | Preserve and flag the order; retain fulfilment evidence but prevent payment reconciliation. |
| `OLIST-ORDER-PAYMENT-COVERAGE-006` | `delivered_orders_without_payments` | 1 | Warning | Preserve and flag the order; retain order and fulfilment evidence but prevent payment-dependent reconciliation. |

#### Analytical impact

The current relationship profile confirms that:

- every staged payment matches a staged order;
- one delivered order has no Raw or staged payment record;
- the paymentless order contains three items;
- its item price totals 134.97;
- its freight value totals 8.49;
- it has complete carrier and customer delivery timestamps;
- it has one review with score one;
- some orders legitimately contain multiple payment records.

The paymentless delivered order may remain usable for:

- order counts;
- customer-order relationships;
- order-item analysis;
- product and seller analysis;
- fulfilment analysis;
- review analysis.

It cannot support:

- collected-payment analysis;
- payment-method analysis;
- payment reconciliation;
- comparisons between payment value and item-based order value.

Payment-sequence anomalies remain governed by `dq_payments_anomalies` and are not duplicated in this relationship view.

#### Alert condition

Notify when:

- `payments_without_order` becomes positive;
- any currently zero active-status control becomes positive;
- the delivered-order-without-payment baseline increases;
- a new active order status appears without payment;
- the quality view fails to execute.

Paymentless `created`, `canceled`, and `unavailable` orders are not automatically actionable solely because they lack payment records.

#### Response

The engineer must:

1. inspect the affected order and payment relations in staging and Raw;
2. determine whether the condition reflects missing source data, incomplete ingestion, or transformation behavior;
3. inspect related items, lifecycle timestamps, and reviews;
4. identify payment-, revenue-, and reconciliation-dependent outputs;
5. preserve the order and all available related evidence;
6. prevent unreviewed payment-dependent use;
7. avoid fabricating payment records, payment methods, sequences, or values.

Mercury must not infer a payment value from item and freight totals.

---

### 6.9 Order-value reconciliation anomalies

Source relations:

```text
staging.stg_order_items
staging.stg_payments
```

Quality view:

```text
staging.dq_order_value_reconciliation_anomalies
```

The control compares independently aggregated item-based and payment totals at `order_id` grain.

The item-based order total is:

```text
SUM(price + freight_value)
```

The payment total is:

```text
SUM(payment_value)
```

A tolerance of 0.01 is applied before a difference is classified as an anomaly.

| Control ID | Anomaly type | Baseline | Severity | Disposition |
|---|---|---:|---|---|
| `OLIST-ORDER-VALUE-RECONCILIATION-001` | `payment_above_item_total` | 264 | Warning | Preserve both totals and flag the order; exclude it from analyses requiring exact item-to-payment reconciliation. |
| `OLIST-ORDER-VALUE-RECONCILIATION-002` | `payment_below_item_total` | 39 | Warning | Preserve both totals and flag the order; exclude it from analyses requiring exact item-to-payment reconciliation. |

#### Validated monetary impact

| Anomaly type | Evaluated orders | Anomaly rate | Total absolute difference | Maximum absolute difference |
|---|---:|---:|---:|---:|
| `payment_above_item_total` | 98,665 | 0.2676% | 3,070.14 | 182.81 |
| `payment_below_item_total` | 98,665 | 0.0395% | 199.08 | 51.62 |
| Combined | 98,665 | 0.3071% | 3,269.22 | 182.81 |

The cumulative absolute difference across all comparable orders is 3,271.95 when differences within the accepted 0.01 tolerance are included. The monitored anomaly impact of 3,269.22 includes only orders outside that tolerance.

#### Analytical impact

Reconciliation anomalies affect:

- comparisons between collected payment and item-based order value;
- payment completeness analysis;
- order-value validation;
- revenue definitions requiring exact agreement between the two concepts.

Affected orders may remain valid for analyses that use one clearly identified measure independently.

Mercury must preserve the distinction between:

```text
item-based order value
```

and:

```text
collected payment value
```

Neither value may be overwritten to force agreement.

#### Alert condition

Notify when:

- either anomaly count or anomaly rate exceeds its approved baseline;
- the total or maximum absolute difference increases materially;
- a new reconciliation direction or category appears;
- the quality view fails to execute.

An unchanged approved baseline does not require repeated actionable notification.

#### Response

The engineer must:

1. inspect the independently aggregated item and payment records;
2. identify the payment method and payment structure;
3. determine whether the difference reflects source behavior, missing data, or transformation logic;
4. identify reconciliation-dependent downstream outputs;
5. preserve both original measures;
6. apply the documented reconciliation status;
7. avoid altering source values to manufacture agreement.

Mercury must aggregate order items and payments independently to `order_id` grain before comparing or combining them.

---

### 6.10 Order–review relationship anomalies

#### Scope

The order–review relationship is monitored by:

```text
staging.dq_order_review_relationship_anomalies
```

The view detects relationship-coverage, review-cardinality, identity-consistency, and cross-purchase-date conditions without modifying the staged source observations.

Detailed exploration evidence and canonical modelling implications are maintained in the Olist relationship profile.

### Registered Controls

| Control ID | Anomaly or observation type | Baseline | Severity | Disposition |
| --- | --- | ---: | --- | --- |
| `OLIST-ORDER-REVIEW-COVERAGE-001` | `reviews_without_order` | 0 | Warning | Preserve the staged review; exclude it from order-dependent canonical outputs and investigate the missing parent |
| `OLIST-ORDER-REVIEW-COVERAGE-002` | `delivered_orders_without_review` | 646 | Informational | Retain the order and flag missing feedback; exclude it only from measures requiring an observed review |
| `OLIST-ORDER-REVIEW-CARDINALITY-001` | `orders_with_multiple_distinct_review_scores` | 202 | Informational | Retain every distinct review event and its chronology; require downstream models to declare their review-selection semantics |
| `OLIST-ORDER-REVIEW-IDENTITY-001` | `reused_review_ids_with_inconsistent_payloads` | 0 | Warning | Preserve and flag affected observations; prevent unreviewed consolidation to one review entity |
| `OLIST-ORDER-REVIEW-IDENTITY-002` | `reused_review_ids_across_customers` | 0 | Warning | Preserve and flag affected observations; prevent unreviewed use in customer-level feedback outputs |
| `OLIST-ORDER-REVIEW-IDENTITY-003` | `reused_review_ids_across_purchase_dates` | 41 | Warning | Preserve all associations and flag cross-occasion review reuse for controlled downstream treatment |

### Baseline Interpretation

The zero-anomaly controls establish structural expectations:

- every review should reference a known order;
- one reused review_id should continue to represent one consistent review payload;
- a reused review_id should not cross persistent-customer boundaries.

Any non-zero result for these controls represents a change from the validated source baseline and requires investigation.

The non-zero baselines describe known source behavior:

- 646 delivered orders currently have no associated review;
- 202 orders currently contain multiple distinct review scores;
- 41 reused review IDs currently span different purchase dates.

These conditions do not invalidate the staged orders or reviews.

Multiple review scores may represent customer feedback changing over time. They MUST NOT be automatically averaged, overwritten, or treated as contradictory without a downstream semantic rule.

### Initial Notification Behavior

| Control ID | Initial notification condition | Initial response |
| --- | --- | --- |
| `OLIST-ORDER-REVIEW-COVERAGE-001` | Anomaly count becomes greater than zero | Investigate missing order coverage before publishing affected order-dependent review outputs |
| `OLIST-ORDER-REVIEW-COVERAGE-002` | Count or rate materially exceeds the validated baseline | Confirm whether review coverage or source-delivery behavior has changed |
| `OLIST-ORDER-REVIEW-CARDINALITY-001` | Count or rate materially deviates from the validated baseline | Review whether feedback-event behavior or source semantics have changed |
| `OLIST-ORDER-REVIEW-IDENTITY-001` | Anomaly count becomes greater than zero | Investigate payload conflicts and prevent automatic consolidation of affected review IDs |
| `OLIST-ORDER-REVIEW-IDENTITY-002` | Anomaly count becomes greater than zero | Investigate the identity boundary before using affected reviews in customer-level outputs |
| `OLIST-ORDER-REVIEW-IDENTITY-003` | Count or rate materially exceeds the validated baseline | Investigate increased review reuse across separate purchase occasions |

Exact automated thresholds and notification routing remain part of the future quality-observability implementation boundary defined by ADR-013.

### Canonical publication requirements

Before canonical review outputs are published:

- reviews MUST be represented independently from their order associations;
- the review entity SHOULD use one row per review_id;
- an order–review bridge SHOULD preserve one row per (order_id, review_id);
- review IDs with inconsistent payloads MUST NOT be consolidated without review;
- cross-customer review reuse MUST NOT enter customer-level outputs without investigation;
- order-level review measures MUST aggregate or resolve reviews before joining to the order grain;
- first-review, latest-review, all-review, and sentiment-evolution measures MUST use explicitly documented semantics;
- reviewless orders MUST remain available to analyses that do not require customer feedback.

---

## 7. Accepted Profiled Characteristics

Some observed values satisfy the staging contract and are not currently classified as anomalies.

### Zero-freight order items

The validated Olist staging data contains:

```text
383 order-item rows with freight_value = 0
```

Zero freight is permitted by the documented numeric domain and is therefore retained as a valid source value.

Mercury must not replace zero freight with `NULL` or infer a positive shipping charge.

A future business model may expose a zero-freight indicator where analytically useful, but the current observation does not require a quality alert.

---

## 8. Initial Alert Policy

Until sufficient historical evaluations exist to establish more mature statistical thresholds, Mercury will use the following initial policy:

| Condition | Initial behavior |
|---|---|
| Blocking control reports any failing row | Fail dependent publication and issue a critical notification |
| Blocking control fails to execute | Fail dependent publication and issue a critical unknown-state notification |
| Zero-baseline non-blocking control becomes positive | Issue a warning notification |
| Known warning-level anomaly exceeds its approved count or rate | Issue a warning notification |
| Known informational anomaly remains unchanged | Record without repeated actionable notification |
| Known informational anomaly rate increases | Notify for engineering evaluation |
| New anomaly type appears | Notify for classification and disposition |
| Non-blocking monitor fails to execute | Record an unknown quality state and notify |
| Anomaly returns to its expected state | Record the recovery; resolution notification may be emitted |

Unexpected results must not automatically become new approved baselines.

Baseline or threshold changes require documented review.

---

## 9. Ownership

Until a more granular ownership model is introduced, the responsible role for all Olist controls is:

```text
Mercury Data Engineering
```

The owner is responsible for:

- reviewing quality notifications;
- inspecting affected records;
- identifying source or transformation causes;
- assessing downstream impact;
- applying or verifying the documented disposition;
- escalating source issues where necessary;
- approving changes to controls, thresholds, severities, or baselines;
- recording investigation outcomes.

Ownership refers to an operational role rather than an individual person.

---

## 10. Implementation Status

| Capability | Status |
|---|---|
| Blocking Dataform assertions | Implemented and validated |
| Non-blocking quality views | Implemented and validated |
| Initial anomaly baselines | Recorded in this document |
| Initial analytical dispositions | Defined in this document |
| Stable control identifiers | Defined in this document |
| Canonical quality flags | Planned |
| Geographic resolution model | Planned |
| Relationship-quality controls | In progress — customer–order, order–order-item, order–payment, and order-value reconciliation controls implemented and validated |
| Persistent quality-result history | Planned |
| Baseline evaluation mechanism | Planned |
| Automated engineer notification | Planned |
| Operational response-history storage | Planned |
| Quality-observability implementation design | Planned |

A disposition marked as defined is not considered technically implemented until the relevant canonical, preparation, monitoring, or operational component exists and has been validated.

---

## 11. Relationship Exploration Extension

Phase 3.6 will add cross-entity controls covering areas such as:

- customer-to-order coverage;
- order-to-order-item coverage;
- order-to-payment coverage;
- order-to-review coverage;
- product-to-order-item coverage;
- seller-to-order-item coverage;
- orphaned child records;
- parents without children;
- unexpected cardinalities;
- join amplification;
- monetary reconciliation;
- geographic enrichment compatibility.

Every new relationship anomaly must be:

1. assigned a stable control identifier;
2. classified as blocking or non-blocking;
3. assigned a severity;
4. given an initial baseline or threshold;
5. assigned an owner;
6. given a response playbook;
7. given an explicit downstream disposition;
8. added to this register before the affected canonical model is published.

---

## 12. Completion Criteria

The initial Olist anomaly-disposition phase is complete when:

- [x] ADR-013 is accepted
- [x] every existing blocking control is registered
- [x] every existing non-blocking anomaly type is registered
- [x] validated baselines are recorded
- [x] zero-anomaly controls have future response behavior
- [x] severities are assigned
- [x] initial notification conditions are defined
- [x] downstream dispositions are defined
- [x] ownership and response expectations are defined
- [x] future implementation boundaries are explicit
- [x] the ROADMAP reflects the resulting implementation position

Operational monitoring is not considered implemented until quality history, evaluation, and notification mechanisms have been deployed and validated.