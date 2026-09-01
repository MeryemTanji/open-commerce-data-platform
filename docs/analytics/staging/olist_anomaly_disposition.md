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
| Relationship-quality controls | Planned for Phase 3.6 |
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