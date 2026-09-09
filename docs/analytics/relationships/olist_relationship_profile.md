# Olist Relationship Profile

## Status

Work in progress

## Date

2026-09-08

## Purpose

This document records cross-entity relationship findings for Mercury's staged Olist data.

The exploration validates:

- expected parent-child relationships;
- referential coverage;
- observed cardinalities;
- join amplification;
- identity behavior;
- reconciliation constraints;
- implications for canonical modelling.

This document records profiling evidence and modelling inputs. It does not redefine staging contracts or anomaly-disposition policy.

Related documentation:

- [Olist staging contracts](../staging/olist_staging_contracts.md)
- [Olist anomaly disposition register](../staging/olist_anomaly_disposition.md)
- [ADR-012: Staging Layer Standardization and Semantic Contracts](../../../architecture/decisions/ADR-012-Staging%20Layer%20Standardization%20and%20Semantic%20Contracts.md)
- [ADR-013: Data Quality Anomaly Disposition and Monitoring Contract](../../../architecture/decisions/ADR-013-Data%20Quality%20Anomaly%20Disposition%20and%20Monitoring%20Contract.md)

---

## 1. Scope

Relationship exploration uses validated staging relations rather than Raw source tables.

The current scope includes:

| Parent entity | Related entity | Join key | Expected relationship | Status |
|---|---|---|---|---|
| Customers | Orders | `customer_id` | One customer record to one order | Profiled |
| Orders | Order items | `order_id` | One order to zero or more order items | Planned |
| Orders | Payments | `order_id` | One order to zero or more payments | Planned |
| Orders | Reviews | `order_id` | One order to zero or more reviews | Planned |
| Products | Order items | `product_id` | One product to zero or more order items | Planned |
| Sellers | Order items | `seller_id` | One seller to zero or more order items | Planned |
| Geolocations | Customers | ZIP-code prefix | Many observations to many customer records | Planned |
| Geolocations | Sellers | ZIP-code prefix | Many observations to many seller records | Planned |

Expected relationships are hypotheses until validated against the staged source data.

---

## 2. Method

Each relationship is evaluated for:

1. parent and child row counts;
2. distinct relationship keys;
3. child records without a matching parent;
4. parent records without matching children;
5. observed minimum and maximum cardinality;
6. cardinality distribution;
7. join-result row count;
8. join-amplification risk;
9. known source anomalies affecting interpretation;
10. implications for canonical grain and identity.

Relationship anomalies are added to the Olist anomaly disposition register in accordance with ADR-013.

Exploratory findings do not automatically become blocking controls. Blocking behavior requires an explicit contract decision.

---

## 3. Customer–Order Relationship

### 3.1 Relationship definition

The relationship between staged customers and orders uses:

```text
stg_customers.customer_id
        =
stg_orders.customer_id
```

Olist exposes two customer identifiers with different semantics:

| Identifier | Observed role |
|---|---|
| `customer_id` | Source identifier connecting a customer record to a particular order |
| `customer_unique_id` | Persistent source identity that may appear across multiple customer records and orders |

The distinction is important because `customer_id` and `customer_unique_id` must not be treated as interchangeable canonical customer keys.

---

### 3.2 Coverage and cardinality results

| Metric | Result |
|---|---:|
| Customer rows | 99,441 |
| Distinct `customer_id` values in customers | 99,441 |
| Distinct `customer_unique_id` values | 96,096 |
| Order rows | 99,441 |
| Distinct `customer_id` values in orders | 99,441 |
| Orders without a matching customer | 0 |
| Customer records without a matching order | 0 |
| `customer_id` values associated with multiple orders | 0 |
| Persistent customers with multiple observed orders | 2,997 |
| Maximum observed orders for one persistent customer | 17 |
| Joined customer–order rows | 99,441 |
| Join-amplification factor | 1.0 |

The join-amplification factor is calculated as:

```text
joined customer–order rows
──────────────────────────
order rows

99,441
─────── = 1.0
99,441
```

The customer–order join therefore preserves order grain.

---

### 3.3 Persistent-customer order distribution

| Observed order count | Persistent customer count | Orders represented | Percentage of persistent customers |
|---:|---:|---:|---:|
| 1 | 93,099 | 93,099 | 96.8812% |
| 2 | 2,745 | 5,490 | 2.8565% |
| 3 | 203 | 609 | 0.2112% |
| 4 | 30 | 120 | 0.0312% |
| 5 | 8 | 40 | 0.0083% |
| 6 | 6 | 36 | 0.0062% |
| 7 | 3 | 21 | 0.0031% |
| 9 | 1 | 9 | 0.0010% |
| 17 | 1 | 17 | 0.0010% |

Summary:

| Customer group | Persistent customers | Percentage of persistent customers | Orders represented |
|---|---:|---:|---:|
| One observed order | 93,099 | 96.8812% | 93,099 |
| More than one observed order | 2,997 | 3.1188% | 6,342 |

Customers with multiple observed orders represent approximately 3.12% of persistent customers and account for approximately 6.38% of observed orders.

The average number of orders among these repeat observed customers is approximately 2.12.

These findings describe behavior within the available Olist dataset. They do not prove that a customer made only one lifetime purchase outside the observed source scope.

---

### 3.4 Relationship-quality controls

The following non-blocking controls are implemented in:

```text
staging.dq_customer_order_relationship_anomalies
```

| Control ID | Anomaly type | Validated baseline |
|---|---|---:|
| `OLIST-CUSTOMER-ORDER-COVERAGE-001` | `orders_without_customer` | 0 |
| `OLIST-CUSTOMER-ORDER-COVERAGE-002` | `customers_without_order` | 0 |
| `OLIST-CUSTOMER-ORDER-CARDINALITY-001` | `customer_ids_with_multiple_orders` | 0 |

The view:

- compiles successfully through Dataform;
- passes its BigQuery dry run;
- is deployed in the staging dataset;
- reproduces the zero-anomaly exploratory results.

The severities, alert conditions, response requirements, and downstream dispositions are maintained in the Olist anomaly disposition register.

---

### 3.5 Persistent-customer location stability

Customer location was profiled at `customer_unique_id` grain to determine whether order-specific customer records consistently contain the same location.

| Metric | Result |
|---|---:|
| Persistent customers | 96,096 |
| Persistent customers with multiple observed orders | 2,997 |
| Customers with multiple ZIP prefixes | 250 |
| Customers with multiple cities | 122 |
| Customers with multiple states | 39 |
| Customers with multiple location combinations | 252 |
| Maximum ZIP prefixes per customer | 3 |
| Maximum cities per customer | 3 |
| Maximum states per customer | 3 |
| Maximum location combinations per customer | 3 |

Customers with multiple locations represent:

- approximately 8.41% of customers with multiple observed orders;
- approximately 0.26% of all persistent customers.

Multiple locations are not classified as anomalies solely because they differ. They may represent legitimate changes of residence, delivery-location choices, or other order-specific source behavior.

The result establishes that customer location is not universally stable at persistent-customer grain.

Mercury must therefore preserve the order-contextual location associated with each `customer_id`. A canonical customer model must not select an arbitrary location for `customer_unique_id`.

Potential canonical treatments include:

- retaining location at order grain;
- deriving a documented latest-observed location;
- maintaining customer-location history;
- separating persistent customer identity from location observations.

The appropriate treatment will be decided during canonical modelling.

---

### 3.6 Findings

The current source snapshot supports the following conclusions:

1. Every staged order has exactly one matching staged customer record.
2. Every staged customer record has exactly one matching staged order.
3. `customer_id` behaves as an order-specific relationship identifier.
4. `customer_unique_id` behaves as the persistent source customer identity.
5. Joining customers to orders through `customer_id` does not multiply or remove order rows.
6. Multiple orders associated with one `customer_unique_id` are expected business behavior rather than duplicate-customer anomalies.
7. Repeat-customer logic must not be implemented in staging because it requires cross-record aggregation and business interpretation.

---

### 3.7 Canonical modelling implications

The findings provide the following inputs for later canonical design:

- `customer_id` should remain available for source traceability and order-to-customer relationship validation.
- `customer_unique_id` is the current candidate source key for persistent canonical customer identity.
- A canonical order relation can use the staged `customer_id` join without current row amplification.
- Repeat-customer indicators require aggregation by `customer_unique_id` and therefore belong after staging.
- Customer-level metrics must distinguish customer records from persistent customer identities.
- A final canonical customer-key strategy remains subject to an explicit canonical modelling decision.
- Geographic attributes must not yet be resolved through direct joins to staged geolocation observations.

These are modelling inputs, not yet an approved canonical schema.

---

### 3.8 Remaining customer exploration

Before finalizing the canonical customer design, Mercury must investigate whether multiple customer records associated with the same `customer_unique_id` contain different:

- ZIP-code prefixes;
- cities;
- states;
- observed order timestamps.

This will determine whether customer location can be treated as a single stable attribute or requires order-contextual or historically varying treatment.

---

## 4. Order–Order Item Relationship

### 4.1 Relationship definition

The relationship between staged orders and order items uses:

```text
stg_orders.order_id
        =
stg_order_items.order_id
```

The declared grains are:

```text
stg_orders
one row per order

stg_order_items
one row per order and order-item sequence
```

The expected relationship is one order to zero or more order items.

---

### 4.2 Coverage and cardinality results

| Metric | Result |
|---|---:|
| Order rows | 99,441 |
| Order-item rows | 112,650 |
| Orders with items | 98,666 |
| Orders without items | 775 |
| Order items without an order | 0 |
| Orders with exactly one item | 88,863 |
| Orders with multiple items | 9,803 |
| Minimum items per item-bearing order | 1 |
| Maximum items per order | 21 |
| Average items per item-bearing order | 1.1417 |
| Orders missing item ID one | 0 |
| Orders with non-contiguous item IDs | 0 |
| Inner-join rows | 112,650 |
| Left-join rows | 113,425 |
| Left-join amplification factor | 1.1406 |

Approximately 9.94% of item-bearing orders contain multiple items.

A direct left join from orders to order items increases the result from 99,441 order rows to 113,425 rows. Measures held at order grain would therefore be duplicated if joined directly without aggregation or grain-aware modelling.

---

### 4.3 Itemless orders by status

| Order status | Total orders in status | Orders without items | Percentage of status without items |
|---|---:|---:|---:|
| `unavailable` | 609 | 603 | 99.0148% |
| `canceled` | 625 | 164 | 26.2400% |
| `created` | 5 | 5 | 100.0000% |
| `invoiced` | 314 | 2 | 0.6369% |
| `shipped` | 1,107 | 1 | 0.0903% |

Itemless orders with the following statuses are treated as status-consistent source characteristics:

- `created`;
- `canceled`;
- `unavailable`.

These statuses represent 772 of the 775 itemless orders.

The remaining three itemless orders require explicit quality treatment:

- 2 invoiced orders;
- 1 shipped order.

No approved, processing, or delivered orders are currently missing items.

---

### 4.4 Unexpected itemless-order evidence

The two invoiced orders and one shipped order:

- were purchased on 5 October 2016;
- have no corresponding rows in Raw order items;
- have no corresponding rows in staged order items;
- each have one approved positive payment;
- each have one review with score one.

Their payment values are:

| Order status | Payment value |
|---|---:|
| `invoiced` | 73.04 |
| `invoiced` | 76.19 |
| `shipped` | 77.73 |

The shipped order also has an order-delivered-carrier timestamp.

Other orders from the same source period contain valid item records, including delivered, invoiced, processing, and shipped orders. The finding therefore does not represent a complete order-item source outage for that date.

The evidence supports classification as a localized source-level relationship anomaly. It does not establish why the line items are absent.

Mercury must not infer missing products, sellers, prices, freight values, or item sequences from the payment records.

---

### 4.5 Relationship-quality controls

The following non-blocking controls are implemented in:

```text
staging.dq_order_order_item_relationship_anomalies
```

| Control ID | Anomaly type | Validated baseline |
|---|---|---:|
| `OLIST-ORDER-ITEM-COVERAGE-001` | `items_without_order` | 0 |
| `OLIST-ORDER-ITEM-COVERAGE-002` | `approved_orders_without_items` | 0 |
| `OLIST-ORDER-ITEM-COVERAGE-003` | `invoiced_orders_without_items` | 2 |
| `OLIST-ORDER-ITEM-COVERAGE-004` | `processing_orders_without_items` | 0 |
| `OLIST-ORDER-ITEM-COVERAGE-005` | `shipped_orders_without_items` | 1 |
| `OLIST-ORDER-ITEM-COVERAGE-006` | `delivered_orders_without_items` | 0 |
| `OLIST-ORDER-ITEM-SEQUENCE-001` | `orders_missing_item_id_one` | 0 |
| `OLIST-ORDER-ITEM-SEQUENCE-002` | `orders_with_non_contiguous_item_ids` | 0 |

The view:

- compiles successfully through Dataform;
- passes its BigQuery dry run;
- is deployed in the staging dataset;
- reproduces the validated exploratory baselines.

Severities, alert conditions, response requirements, and dispositions are maintained in the Olist anomaly disposition register.

---

### 4.6 Canonical modelling implications

The relationship establishes that:

1. order items form a child entity at order-item grain;
2. order-item measures must not be joined directly into an order-grain model without aggregation;
3. a canonical order fact and canonical order-item fact may require separate grains;
4. product and seller attribution is unavailable for the three unexpected itemless orders;
5. item-price and freight totals cannot be calculated for those orders;
6. payment-to-item-value reconciliation cannot succeed for those orders;
7. order-level lifecycle, customer, payment, and review evidence may still be retained with an explicit missing-items flag;
8. `order_item_id` behaves as a contiguous sequence within each order and must not be treated as globally unique;
9. itemless `created`, `canceled`, and `unavailable` orders must not be removed merely because they lack item records.

---

## 5. Order–Payment Relationship

### 5.1 Relationship definition

The relationship between staged orders and payments uses:

```text
stg_orders.order_id
        =
stg_payments.order_id
```

The declared grains are:

```text
stg_orders
one row per order

stg_payments
one row per order and payment sequence
```

The expected relationship is one order to zero or more payment records.

Multiple payment records may represent split payments, multiple vouchers, or other source payment behavior. They are not inherently anomalous.

---

### 5.2 Coverage and cardinality results

| Metric | Result |
|---|---:|
| Order rows | 99,441 |
| Payment rows | 103,886 |
| Orders with payments | 99,440 |
| Orders without payments | 1 |
| Payments without an order | 0 |
| Orders with exactly one payment | 96,479 |
| Orders with multiple payments | 2,961 |
| Minimum payments per payment-bearing order | 1 |
| Maximum payments per order | 29 |
| Average payments per payment-bearing order | 1.0447 |
| Orders missing payment sequence one | 80 |
| Orders with non-contiguous payment sequences | 80 |
| Inner-join rows | 103,886 |
| Left-join rows | 103,887 |
| Left-join amplification factor | 1.0447 |

Approximately 2.98% of payment-bearing orders contain multiple payment records.

A direct order-to-payment join therefore changes the relation from order grain to payment grain and duplicates order-level attributes for multi-payment orders.

---

### 5.3 Payment sequence behavior

The 80 orders without payment sequence one have the following observed patterns:

| Sequence pattern | Affected orders |
|---|---:|
| `2` | 78 |
| `2,3` | 2 |

All affected orders begin at sequence two:

- 78 orders contain only payment sequence two;
- 2 orders contain sequences two and three;
- no affected order contains sequence one.

Mercury cannot determine from the available data whether sequence-one payments are missing or whether the source assigned sequences according to another process.

The sequence values must therefore remain unchanged. Mercury must not renumber them.

This condition is already monitored through:

```text
staging.dq_payments_anomalies
```

with the anomaly type:

```text
order_missing_sequence_one
```

It is not duplicated in the order–payment relationship-quality view.

---

### 5.4 Paymentless delivered order

One delivered order has no corresponding payment record in either Raw or staging.

The available evidence is:

| Attribute | Result |
|---|---:|
| Order status | `delivered` |
| Raw payment rows | 0 |
| Staged payment rows | 0 |
| Order-item rows | 3 |
| Total item price | 134.97 |
| Total freight value | 8.49 |
| Item-based order total | 143.46 |
| Review rows | 1 |
| Review score | 1 |
| Carrier-delivery timestamp | Present |
| Customer-delivery timestamp | Present |

The order is valid evidence for order, item, product, seller, fulfilment, customer, and review analysis.

It is not valid evidence for collected-payment value or payment-method analysis.

Mercury must not infer that payment value equals 143.46. Item-based order value and collected payment value are separate source concepts and may differ for legitimate reasons.

---

### 5.5 Relationship-quality controls

The following controls are implemented in:

```text
staging.dq_order_payment_relationship_anomalies
```

| Control ID | Anomaly type | Validated baseline |
|---|---|---:|
| `OLIST-ORDER-PAYMENT-COVERAGE-001` | `payments_without_order` | 0 |
| `OLIST-ORDER-PAYMENT-COVERAGE-002` | `approved_orders_without_payments` | 0 |
| `OLIST-ORDER-PAYMENT-COVERAGE-003` | `invoiced_orders_without_payments` | 0 |
| `OLIST-ORDER-PAYMENT-COVERAGE-004` | `processing_orders_without_payments` | 0 |
| `OLIST-ORDER-PAYMENT-COVERAGE-005` | `shipped_orders_without_payments` | 0 |
| `OLIST-ORDER-PAYMENT-COVERAGE-006` | `delivered_orders_without_payments` | 1 |

The view:

- compiles successfully through Dataform;
- passes its BigQuery dry run;
- is deployed in the staging dataset;
- reproduces the validated relationship baselines.

The severities, alert conditions, response requirements, and dispositions are maintained in the Olist anomaly disposition register.

---

### 5.6 Order-value reconciliation and join amplification

Order-item values and payment values were aggregated independently to order grain before comparison. This avoids multiplying measures when an order contains both multiple items and multiple payment records.

#### Coverage and reconciliation results

| Metric | Result |
| --- | ---: |
| Orders | 99,441 |
| Orders with both items and payments | 98,665 |
| Orders with items but no payments | 1 |
| Orders with payments but no items | 775 |
| Orders with neither items nor payments | 0 |
| Orders with multiple items and multiple payments | 275 |
| Orders reconciled within the `0.01` tolerance | 98,362 |
| Orders with payments above item totals | 264 |
| Orders with payments below item totals | 39 |
| Orders outside the reconciliation tolerance | 303 |
| Reconciliation anomaly rate | 0.3071% |

The implemented reconciliation controls evaluate only orders containing both item and payment records. Missing relationship coverage remains governed by the separate order–item and order–payment controls.

#### Reconciliation differences outside tolerance

| Direction | Evaluated orders | Anomaly count | Anomaly rate | Total absolute difference | Maximum absolute difference |
| --- | ---: | ---: | ---: | ---: | ---: |
| Payment above item total | 98,665 | 264 | 0.2676% | 3,070.14 | 182.81 |
| Payment below item total | 98,665 | 39 | 0.0395% | 199.08 | 51.62 |
| Combined | 98,665 | 303 | 0.3071% | 3,269.22 | 182.81 |

The exploratory total absolute difference across all comparable orders was `3,271.95`. That value includes small differences within the accepted `0.01` tolerance. The monitored anomaly total of `3,269.22` includes only orders outside that tolerance.

#### Difference magnitude

| Absolute-difference band | Payment above | Payment below | Total orders | Total absolute difference |
| --- | ---: | ---: | ---: | ---: |
| `0.02–0.10` | 23 | 21 | 44 | 1.00 |
| `0.11–1.00` | 9 | 1 | 10 | 5.89 |
| `1.01–10.00` | 141 | 10 | 151 | 755.17 |
| `10.01–50.00` | 84 | 6 | 90 | 1,788.80 |
| `50.01–100.00` | 4 | 1 | 5 | 304.65 |
| Above `100.00` | 3 | 0 | 3 | 413.71 |

Most reconciliation anomalies are greater than `1.00`, so the findings cannot be explained solely by ordinary decimal-rounding differences.

#### Payment-structure findings

| Payment structure | Comparable orders | Mismatched orders | Mismatch rate | Total absolute difference |
| --- | ---: | ---: | ---: | ---: |
| Multiple payments, missing sequence one | 2 | 0 | 0.0000% | 0.00 |
| Multiple payments, sequence one present | 2,934 | 17 | 0.5794% | 47.61 |
| Single payment, missing sequence one | 77 | 0 | 0.0000% | 0.00 |
| Single payment, sequence one present | 95,652 | 286 | 0.2990% | 3,221.61 |

The missing-sequence-one condition does not explain the reconciliation anomalies. Most mismatches occur among orders with a conventional single payment at sequence one.

#### Join-amplification findings

| Metric | Correctly aggregated result | Naive three-table join result | Overstatement |
| --- | ---: | ---: | ---: |
| Joined rows | 99,441 order-grain rows | 118,434 rows | 18,993 additional rows |
| Item value | 15,843,553.24 | 16,566,687.31 | 723,134.07 |
| Payment value | 16,008,872.12 | 20,470,726.66 | 4,461,854.54 |

The naive join produces a row-amplification factor of approximately `1.191`. It overstates item value by approximately `4.564%` and payment value by approximately `27.871%`.

Canonical models therefore MUST aggregate order items and payments independently to order grain before joining them. Order-grain outputs should expose the item-based total, payment total, difference, and reconciliation status without silently correcting either source-derived measure.

---

### 5.7 Findings

The current source snapshot supports the following conclusions:

1. Every staged payment has a matching staged order.
2. Nearly every staged order has at least one payment.
3. One delivered order has no Raw or staged payment evidence.
4. Multiple payment records are legitimate and occur for approximately 2.98% of payment-bearing orders.
5. Payment data must be aggregated to order grain before joining it to an order-grain canonical model.
6. Payment sequence values cannot be assumed to begin at one.
7. Payment sequence values must not be renumbered.
8. Payment value must not be inferred from item price and freight.
9. Directly joining payments and order items through orders may multiply both item and payment measures.
10. Item-to-payment reconciliation must be profiled before canonical monetary measures are defined.

---

## 6. Order–Review Relationship

### 6.1 Relationship definition

The order–review relationship connects:

- `stg_orders.order_id`
- `stg_reviews.order_id`

The staged data does not represent a strictly one-to-one relationship.

The validated relationship supports:

- orders without reviews;
- orders with one review;
- orders with multiple distinct reviews;
- review identifiers associated with multiple orders.

The effective source relationship is therefore many-to-many:

```text
Order
  ↓
Order–Review Association
  ↓
Review Event
```
The staging layer preserves each source observation at the compound grain:

        (order_id, review_id)

No review observation is removed, merged, or reassigned during staging.

---

### 6.2 Coverage and cardinality results

| Metric                                              | Result |
| --------------------------------------------------- | -----: |
| Order rows                                          | 99,441 |
| Distinct order IDs                                  | 99,441 |
| Review rows                                         | 99,224 |
| Reviewed orders                                     | 98,673 |
| Distinct review IDs                                 | 98,410 |
| Orders without reviews                              |    768 |
| Reviews without orders                              |      0 |
| Orders with exactly one review                      | 98,126 |
| Orders with multiple reviews                        |    547 |
| Minimum reviews per reviewed order                  |      1 |
| Maximum reviews per reviewed order                  |      3 |
| Average reviews per reviewed order                  | 1.0056 |
| Orders repeating the same review ID internally      |      0 |
| Rows produced by a direct order-to-review left join | 99,992 |
| Left-join amplification factor                      | 1.0055 |

All review rows reference valid staged orders.

The direct order-to-review join produces 551 more rows than the order table. Order-grain models therefore MUST resolve or aggregate review relationships before joining them to orders.

Of the 547 orders with multiple reviews:

- 543 have two review rows;
- 4 have three review rows.

---

### 6.3 Review coverage by order status

| Order status | Orders | Orders without reviews | Orders with multiple reviews | Missing-review rate |
| --- | ---: | ---: | ---: | ---: |
| `delivered` | 96,478 | 646 | 525 | 0.6696% |
| `shipped` | 1,107 | 75 | 11 | 6.7751% |
| `canceled` | 625 | 20 | 4 | 3.2000% |
| `unavailable` | 609 | 14 | 2 | 2.2989% |
| `processing` | 301 | 6 | 1 | 1.9934% |
| `invoiced` | 314 | 5 | 4 | 1.5924% |
| `created` | 5 | 2 | 0 | 40.0000% |
| `approved` | 2 | 0 | 0 | 0.0000% |

The 646 delivered orders without reviews represent incomplete feedback coverage rather than invalid orders.

These orders remain valid for order, fulfilment, and revenue analysis. They MUST be excluded only from calculations that require an observed review score or review event.

Review-based reporting MUST distinguish between:

- order population;
- review-eligible population where explicitly defined;
- reviewed-order population;
- unique feedback-event population.

---

### 6.4 Multiple-review behavior

Multiple reviews associated with one order are not assumed to be duplicate or contradictory records.

| Reviews per order | Affected orders | Different scores | Different creation dates | Different answer timestamps | Different titles | Different messages |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 2 | 543 | 200 | 388 | 543 | 9 | 124 |
| 3 | 4 | 2 | 4 | 4 | 0 | 2 |
| **Total** | **547** | **202** | **392** | **547** | **9** | **126** |

All orders with multiple reviews contain different answer timestamps. Some customers may provide feedback more than once, including changing their score after using a product or experiencing the order over time.

Consequently:

- multiple scores MUST NOT be treated automatically as contradictory data;
- earlier reviews MUST NOT be silently overwritten;
- later reviews MUST NOT automatically replace earlier reviews in staging;
- review chronology MUST remain available for downstream analysis;
- downstream models MUST define whether they use the first review, - latest review, every feedback event, or another documented aggregation.

A simple average of multiple scores MUST NOT be applied as an undocumented default because it removes the direction and chronology of changing feedback.

---

### 6.5 Reused review identities

The review identifier is not unique to one order.

| Metric                                       | Result |
| -------------------------------------------- | -----: |
| Review IDs associated with multiple orders   |    789 |
| Affected review rows                         |  1,603 |
| Maximum orders per reused review ID          |      3 |
| Reused IDs with inconsistent payloads        |      0 |
| Reused IDs spanning different customers      |      0 |
| Reused IDs spanning different purchase dates |     41 |

Every reused review ID currently:

- has an identical score, title, message, creation date, and answer timestamp;
- remains within one customer_unique_id;
- is associated with no more than three orders.

The purchase-timing profile is:

| Orders per reused review ID | Reused review IDs | Purchased within one hour | Purchased on different dates | Maximum purchase span |
| ---: | ---: | ---: | ---: | ---: |
| 2 | 764 | 729 | 35 | 3,051 hours |
| 3 | 25 | 19 | 6 | 1,304 hours |
| **Total** | **789** | **748** | **41** | — |

Approximately 94.80% of reused review IDs relate to orders purchased within one hour. This strongly suggests that one customer-feedback event can be associated with multiple order IDs from the same purchase occasion.

The remaining 41 review IDs span different purchase dates. These records may represent source-side review reuse or propagation across separate purchase occasions. Mercury preserves and flags them rather than silently assigning the review to only one order.

---

### 6.6 Relationship-quality controls

The permanent Dataform view:

        staging.dq_order_review_relationship_anomalies

reports the following controls:

| Anomaly or observation type | Validated baseline | Severity | Disposition |
| --- | ---: | --- | --- |
| `reviews_without_order` | 0 | Warning | Preserve the staged observation; exclude it from order-dependent canonical outputs and investigate the missing parent |
| `delivered_orders_without_review` | 646 | Informational | Retain the order and flag missing feedback; exclude it only from measures requiring an observed review |
| `orders_with_multiple_distinct_review_scores` | 202 | Informational | Retain every distinct review event and its chronology; require downstream models to declare their review-selection semantics |
| `reused_review_ids_with_inconsistent_payloads` | 0 | Warning | Preserve and flag affected observations; prevent unreviewed consolidation to one review entity |
| `reused_review_ids_across_customers` | 0 | Warning | Preserve and flag affected observations; prevent unreviewed use in customer-level feedback outputs |
| `reused_review_ids_across_purchase_dates` | 41 | Warning | Preserve all order associations and flag cross-occasion review reuse for controlled downstream treatment |

The controls remain non-blocking at staging grain. They provide baselines and future-change detection under ADR-013.

---

### 6.7 Canonical modelling implications

The canonical model SHOULD separate review events from their order associations.

| Canonical relation | Grain | Purpose |
| --- | --- | --- |
| Review fact or entity | One row per `review_id` | Stores the unique review payload and feedback chronology |
| Order–review bridge | One row per `(order_id, review_id)` | Preserves the association between reviews and orders |
| Order fact | One row per `order_id` | Preserves the order grain without review-driven row amplification |

The one-row-per-review representation is currently supported because reused review IDs have consistent payloads. The zero-baseline payload-consistency control protects this assumption against future source changes.

Canonical calculations MUST define their intended grain:

- feedback-event metrics count each review_id once;
- order review coverage uses the order–review bridge;
- order-level review counts count distinct review IDs;
- customer-level feedback metrics avoid counting a shared review - repeatedly merely because it relates to multiple orders;
- initial-sentiment metrics select the earliest qualifying review deterministically;
- latest-sentiment metrics select the latest qualifying review deterministically;
- sentiment-evolution analysis retains and orders all distinct review events.

Order-grain models MUST aggregate or resolve review associations before joining them to orders.

The staging source observations remain immutable with respect to review identity and assignment. Any consolidation, selection, or temporal interpretation belongs in an explicitly documented downstream model.

---

### 6.8 Findings

The relationship exploration establishes that:

- 1. Every staged review references a valid order.
- 2. Review coverage is optional rather than universal.
- 3. Delivered orders without reviews remain analytically valid outside review-dependent measures.
- 4. An order may receive multiple distinct review events.
- 5. Multiple review scores may represent changing customer feedback over time.
- 6. A review event may relate to multiple orders belonging to the same persistent customer.
- 7. Most shared reviews relate to orders purchased within one hour.
- 8. A smaller set of shared reviews spans separate purchase dates and requires continued visibility.
- 9. Direct order-to-review joins can amplify the order grain.
- 10. The canonical model requires a review entity and an order–review bridge to preserve the observed relationship losslessly.

---

## 7. Product–Order Item Relationship

### 7.1 Relationship definition

The product–order-item relationship connects:

- `stg_products.product_id`
- `stg_order_items.product_id`

Each staged product has one unique `product_id`, while a product may occur in multiple order-item rows.

The relationship is:

```text
Product 1 ────< Order Item
```

Orders and products form a many-to-many relationship through order items:

```text
Order 1 ────< Order Item >──── 1 Product
```

The validated order-item grain remains:

```text
(order_id, order_item_id)
```

---

### 7.2 Coverage and Cardinality Results

| Metric                                |  Result |
| ------------------------------------- | ------: |
| Product rows                          |  32,951 |
| Distinct product IDs                  |  32,951 |
| Order-item rows                       | 112,650 |
| Referenced product IDs                |  32,951 |
| Orders with items                     |  98,666 |
| Order items without a product         |       0 |
| Products without order items          |       0 |
| Products with one item row            |  18,117 |
| Products with multiple item rows      |  14,834 |
| Products occurring in one order       |  19,564 |
| Products occurring in multiple orders |  13,387 |
| Minimum item rows per used product    |       1 |
| Maximum item rows per used product    |     527 |
| Average item rows per used product    |  3.4187 |
| Minimum orders per used product       |       1 |
| Maximum orders per used product       |     467 |
| Average orders per used product       |  3.1084 |
| Item-to-product joined rows           | 112,650 |
| Item-to-product join factor           |  1.0000 |

Every staged order item references a valid product, and every staged product appears in at least one order item.

Joining product attributes to the order-item grain by product_id does not amplify the item row count.

The absence of unused products describes the current Olist dataset. It MUST NOT become a universal platform assumption because a complete product catalogue may legitimately include products that have never been ordered.

---

### 7.3 Repeated Products within Orders

The staged order items contain:

| Metric                                              |  Result |
| --------------------------------------------------- | ------: |
| Distinct `(order_id, product_id)` combinations      | 102,425 |
| Combinations with multiple item rows                |   7,088 |
| Item rows represented by repeated combinations      |  17,313 |
| Additional quantity rows beyond one per combination |  10,225 |
| Maximum item rows per order-product combination     |      20 |

Repeated order-product combinations retain consistent commercial and fulfilment attributes:

| Consistency observation                             | Count |
| --------------------------------------------------- | ----: |
| Repeated combinations with multiple sellers         |     0 |
| Repeated combinations with multiple prices          |     0 |
| Repeated combinations with multiple freight values  |     0 |
| Repeated combinations with multiple shipping limits |     0 |

This supports interpreting each repeated order-item row as an individual product unit in the current dataset.

---

### 7.4 Inferred Quantity Distribution

| Inferred quantity | Order-product combinations | Represented item rows |
| ----------------: | -------------------------: | --------------------: |
|                 1 |                     95,337 |                95,337 |
|                 2 |                      5,382 |                10,764 |
|                 3 |                        953 |                 2,859 |
|                 4 |                        390 |                 1,560 |
|                 5 |                        168 |                   840 |
|                 6 |                        172 |                 1,032 |
|                 7 |                          4 |                    28 |
|                 8 |                          2 |                    16 |
|                 9 |                          2 |                    18 |
|                10 |                          5 |                    50 |
|                11 |                          1 |                    11 |
|                12 |                          2 |                    24 |
|                13 |                          1 |                    13 |
|                14 |                          2 |                    28 |
|                15 |                          2 |                    30 |
|                20 |                          2 |                    40 |

Quantity can be inferred as the number of item rows within a consistently defined commercial grouping. The staging layer does not collapse these rows or add a derived quantity column.

---

### 7.5 Relationship-quality Controls

The permanent Dataform view:

```text
staging.dq_product_order_item_relationship_anomalies
```

reports:

| Anomaly or observation type | Validated baseline | Severity | Disposition |
| --- | ---: | --- | --- |
| `order_items_without_product` | 0 | Warning | Preserve and flag the item; exclude it from product-dependent canonical outputs until its missing product reference is investigated |
| `products_without_order_items` | 0 | Informational | Retain the product as valid catalogue data and exclude it only from analyses requiring an observed sale |
| `repeated_order_product_combinations` | 7,088 | Informational | Preserve every item row and interpret repeated rows as quantity only through an explicit downstream aggregation |
| `repeated_order_products_with_multiple_sellers` | 0 | Informational | Preserve the separate item rows and aggregate at a grain that includes `seller_id` |
| `repeated_order_products_with_multiple_prices` | 0 | Informational | Preserve the separate item rows and aggregate at a grain that includes unit price |
| `repeated_order_products_with_multiple_freight_values` | 0 | Informational | Preserve the separate item rows and aggregate at a grain that includes freight value |
| `repeated_order_products_with_multiple_shipping_limits` | 0 | Informational | Preserve the separate item rows and aggregate at a grain that includes the shipping limit |

The four commercial-consistency observations do not define future non-zero results as invalid. They detect when (order_id, product_id) is no longer sufficiently precise for deriving a single quantity group.

---

### 7.6 Canonical Modelling Implications

The canonical order-item fact SHOULD preserve:

```text
One row per (order_id, order_item_id)
```

At this grain:

- product_id references the product dimension;
- seller_id identifies the seller responsible for the item;
- price represents the item-level unit price;
- freight_value remains attributable to the individual item row;
- product attributes can be joined without changing row count;
- item-level monetary measures remain additive.

A downstream order-product summary MAY derive quantity using:

```sql
COUNT(*) AS quantity
```
The reusable grouping grain SHOULD include:

```text
order_id
product_id
seller_id
price
freight_value
shipping_limit_timestamp
```

This prevents future item rows with different sellers, prices, freight charges, or fulfilment terms from being incorrectly collapsed.

Order-level product measures MUST aggregate order items before joining them to other one-to-many order relationships such as payments or reviews.

---

### 7.7 Findings

The relationship exploration establishes that:

- 1. Every staged order item references a valid product.
- 2. Every staged product currently appears in at least one order item.
- 3. Product attributes can be joined to order-item grain without amplification.
- 4. Products are reused across orders as expected.
- 5. Repeated products within one order behave consistently like product quantity in the current data.
- 6. The unit-level (order_id, order_item_id) grain remains the safest canonical order-item grain.
- 7. Quantity derivation must remain explicit and commercially grain-aware.
- 8. Unused catalogue products must remain valid if they appear in future sources.

---

## 8. Seller–Order Item Relationship

### 8.1 Relationship definition

The seller–order-item relationship connects:

- `stg_sellers.seller_id`
- `stg_order_items.seller_id`

Each seller has one unique `seller_id`, while a seller may participate in multiple order-item rows and orders.

The relationship is:

```text
Seller 1 ────< Order Item
```

Orders and sellers form a many-to-many relationship through order items:

```text
Order 1 ────< Order Item >──── 1 Seller
```

Products and sellers also form a many-to-many relationship through order items because one seller may sell multiple products and one product may be sold by multiple sellers.

---

### 8.2 Coverage and Cardinality Results

| Metric                                    |  Result |
| ----------------------------------------- | ------: |
| Seller rows                               |   3,095 |
| Distinct seller IDs                       |   3,095 |
| Order-item rows                           | 112,650 |
| Referenced seller IDs                     |   3,095 |
| Orders with items                         |  98,666 |
| Order items without a seller              |       0 |
| Sellers without order items               |       0 |
| Sellers with one item row                 |     509 |
| Sellers with multiple item rows           |   2,586 |
| Sellers participating in one order        |     571 |
| Sellers participating in multiple orders  |   2,524 |
| Sellers associated with one product       |     746 |
| Sellers associated with multiple products |   2,349 |
| Minimum item rows per seller              |       1 |
| Maximum item rows per seller              |   2,033 |
| Average item rows per seller              | 36.3974 |
| Minimum orders per seller                 |       1 |
| Maximum orders per seller                 |   1,854 |
| Average orders per seller                 | 32.3134 |
| Maximum products per seller               |     399 |
| Item-to-seller joined rows                | 112,650 |
| Item-to-seller join factor                |  1.0000 |

Every staged order item references a valid seller, and every staged seller currently appears in at least one order item.

Joining seller attributes to order-item grain by seller_id does not amplify the item row count.

The absence of sellers without items describes the current Olist source extract. Future seller sources may legitimately contain registered sellers that have not yet completed a sale.

---

### 8.3 Seller Activity

Seller activity varies materially across the marketplace:

- 509 sellers occur in only one item row;
- 2,586 sellers occur in multiple item rows;
- 571 sellers participate in only one order;
- 2,524 sellers participate in multiple orders;
- 746 sellers are associated with one product;
- 2,349 sellers are associated with multiple products.

The most active seller is associated with:

- 2,033 item rows;
- 1,854 orders;
- 399 products.

These differences describe marketplace participation and seller concentration. They are not treated as source-quality anomalies.

---

### 8.4 Multi-seller Orders

Of the 98,666 orders containing item rows:

| Sellers per order | Orders | Percentage of item-bearing orders |
| ----------------: | -----: | --------------------------------: |
|                 1 | 97,388 |                          98.7047% |
|                 2 |  1,219 |                           1.2355% |
|                 3 |     54 |                           0.0547% |
|                 4 |      3 |                           0.0030% |
|                 5 |      2 |                           0.0020% |


A total of 1,278 orders contain items from multiple sellers.

These orders produce:

| Metric                                        |  Result |
| --------------------------------------------- | ------: |
| Item-bearing orders                           |  98,666 |
| Order–seller combinations                     | 100,010 |
| Additional order–seller associations          |   1,344 |
| Maximum sellers per order                     |       5 |
| Average sellers per order                     |  1.0136 |
| Maximum items per order–seller combination    |      21 |
| Maximum products per order–seller combination |       7 |


Seller MUST NOT be represented as one unqualified order-level attribute. Any order-level seller representation must preserve multiple seller associations or use an explicitly documented aggregation.

---

### 8.5 Product-seller Behaviour

| Metric                                           | Result |
| ------------------------------------------------ | -----: |
| Referenced products                              | 32,951 |
| Products sold by one seller                      | 31,726 |
| Products sold by multiple sellers                |  1,225 |
| Maximum sellers per product                      |      8 |
| Average sellers per product                      | 1.0454 |
| Order-product combinations with multiple sellers |      0 |


Approximately 3.7176% of referenced products are associated with multiple sellers across the dataset.

Seller is therefore not an intrinsic or permanent product attribute. The association between a product and seller belongs to the commercial order-item event.

No individual (order_id, product_id) combination currently contains multiple sellers. This supports the current quantity behavior while the permanent control detects future changes.

---

### 8.6 Relationship-quality Controls

The permanent Dataform view:

```text
staging.dq_seller_order_item_relationship_anomalies
```

reports:

| Anomaly or observation type | Validated baseline | Severity | Disposition |
| --- | ---: | --- | --- |
| `order_items_without_seller` | 0 | Warning | Preserve and flag the item; exclude it from seller-dependent canonical outputs until the missing seller reference is investigated |
| `sellers_without_order_items` | 0 | Informational | Retain the seller as valid marketplace data and exclude it only from analyses requiring observed transaction activity |
| `orders_with_multiple_sellers` | 1,278 | Informational | Preserve every seller association and require seller-aware aggregation in order-grain outputs |
| `products_with_multiple_sellers` | 1,225 | Informational | Preserve seller on the order-item event and do not model seller as a fixed product attribute |
| `order_product_combinations_with_multiple_sellers` | 0 | Informational | Preserve seller-level item separation and use seller-aware quantity aggregation if the condition appears |

The non-zero controls describe valid marketplace cardinality rather than quality failures.

The zero-baseline controls detect broken references or changes that affect the grain required for safe aggregation.

---

### 8.7 Canonical Modelling Implications

The canonical model SHOULD contain:

| Canonical relation | Grain | Purpose |
| --- | --- | --- |
| Seller dimension | One row per `seller_id` | Stores standardised seller attributes |
| Product dimension | One row per `product_id` | Stores product attributes independently of seller |
| Order-item fact | One row per `(order_id, order_item_id)` | Preserves the commercial association between order, product, and seller |
| Optional order–seller summary | One row per `(order_id, seller_id)` | Supports seller-level fulfilment and order analysis after aggregation |

The canonical order-item fact SHOULD retain both:

- product_id;
- seller_id.

Seller MUST NOT be:

- flattened directly onto order grain without resolving multi-seller orders;
- stored as a permanent product-dimension attribute;
- inferred from product identity alone.

Item measures MUST be aggregated to the required order–seller or seller–product grain before they are joined to other one-to-many relationships such as payments or reviews.

---

### 8.8 Findings

The relationship exploration establishes that:

- 1. Every staged order item references a valid seller.
- 2. Every staged seller currently participates in at least one item.
- 3. Seller attributes can be joined to order-item grain without amplification.
- 4. Most item-bearing orders have one seller, but 1,278 contain multiple sellers.
- 5. One product may be sold by multiple sellers.
- 6. Seller belongs to the commercial order-item event rather than the order or product alone.
- 7. The canonical order-item fact must preserve both seller and product references.
- 8. Seller-level order analysis requires explicit aggregation at (order_id, seller_id) grain.

---

## 9. Geographic Relationships

### 9.1 Relationship definition

Geographic relationships connect:

- `stg_customers.customer_zip_code_prefix`
- `stg_sellers.seller_zip_code_prefix`
- `stg_geolocations.geolocation_zip_code_prefix`

The geolocation relation contains repeated observations and is not unique by ZIP-code prefix.

The source relationship is therefore:

```text
Customer >──── ZIP Prefix ────< Geolocation Observation
Seller   >──── ZIP Prefix ────< Geolocation Observation
```

A direct join from customers or sellers to staged geolocation observations does not preserve entity grain.

---

### 9.1 Coverage Results

| Metric                                            |    Result |
| ------------------------------------------------- | --------: |
| Customer rows                                     |    99,441 |
| Distinct customer ZIP prefixes                    |    14,994 |
| Customers without a geolocation prefix            |       278 |
| Customer prefixes without geolocation             |       157 |
| Seller rows                                       |     3,095 |
| Distinct seller ZIP prefixes                      |     2,246 |
| Sellers without a geolocation prefix              |         7 |
| Seller prefixes without geolocation               |         7 |
| Geolocation rows                                  | 1,000,163 |
| Distinct geolocation ZIP prefixes                 |    19,015 |
| Geolocation prefixes without a customer or seller |     4,099 |

Approximately 0.2796% of customer records and 0.2262% of seller records do not have matching geolocation observations.

Missing customer coverage is concentrated in DF:

- 171 of the 278 uncovered customer records are in DF;
- those records span 67 ZIP prefixes;
- the remaining uncovered customers are distributed across multiple states.

Missing geolocation coverage does not invalidate the customer or seller record.

Affected entities retain their source-provided city and state. Resolved coordinates remain unavailable unless another governed reference source is introduced.

The 4,099 unused geolocation prefixes represent valid reference coverage rather than anomalies.

---

### 9.2 Geolocation Observation Cardinality

| Condition                                 | ZIP prefixes |
| ----------------------------------------- | -----------: |
| Multiple source observations              |       17,972 |
| Multiple distinct normalized observations |       17,823 |
| Multiple cities                           |        8,555 |
| Multiple states                           |            8 |
| Multiple coordinates                      |       17,781 |

A single ZIP prefix contains up to:

| Metric                           | Maximum |
| -------------------------------- | ------: |
| Source observations              |   1,146 |
| Distinct normalized observations |     779 |
| City values                      |       5 |
| State values                     |       2 |
| Coordinate pairs                 |     746 |

Repeated observations are expected characteristics of the source geolocation dataset. They MUST NOT be joined directly to customer, seller, order, or order-item grain.

---

### 9.4 Multi-sate ZIP Prefixes

Eight ZIP prefixes contain observations from more than one state:

| ZIP prefix | Dominant state | Dominant observations | Conflicting state | Conflicting observations |
| --- | --- | ---: | --- | ---: |
| `02116` | `SP` | 12 | `RN` | 1 |
| `04011` | `SP` | 178 | `AC` | 1 |
| `21550` | `RJ` | 170 | `AC` | 1 |
| `23056` | `RJ` | 60 | `AC` | 1 |
| `72915` | `GO` | 40 | `DF` | 1 |
| `78557` | `MT` | 96 | `RO` | 1 |
| `79750` | `MS` | 179 | `RS` | 1 |
| `80630` | `PR` | 122 | `SC` | 1 |

Each ambiguous prefix has one isolated conflicting observation and one clearly dominant state.

The observations are preserved in staging. A downstream resolved geographic reference may select the modal state using an explicit deterministic rule.

---

### 9.5 Modal-state Validation

The candidate state-resolution rule selects:

- 1. the state with the highest observation count for each ZIP prefix;
- 2. the alphabetically first state as a deterministic tie-breaker;

No ZIP prefix currently contains a tie between states with the highest observation count. The zero baseline is monitored because a future tie would make the geographic resolution semantically ambiguous even though the lexical tie-breaker remains technically deterministic.

The result was validated against covered customer and seller records:

| Entity    | Covered records | Records disagreeing with modal state |
| --------- | --------------: | -----------------------------------: |
| Customers |          99,163 |                                    0 |
| Sellers   |           3,088 |                                   35 |

The modal-state rule agrees with every covered customer record.

The same 35 seller records identified by the source-consistency profile disagree with the resolved state. Most contain a city and ZIP prefix that agree with geolocation evidence while the source seller state does not.

Of those seller records:

- 33 contain source state SP;
- one contains source state RN where ZIP resolves to RJ;
- one contains source state PA where the ZIP resolves to PR;

These records are retained and flagged. The source seller state is not overwritten in staging.

---

### 9.6 Direct-join amplification

| Join | Entity rows | Directly joined rows | Amplification factor |
| --- | ---: | ---: | ---: |
| Customers → staged geolocations | 99,441 | 15,083,733 | 151.6853 |
| Sellers → staged geolocations | 3,095 | 435,094 | 140.5796 |

Direct joins to geolocation observations would substantially overstate entity counts and any downstream measures.

Canonical models MUST NOT join customers, sellers, orders, or order items directly to stg_geolocations by ZIP prefix.

---

### 9.7 Relationship-quality Controls

The permanent Dataform view:

```text
staging.dq_geographic_relationship_anomalies
```

reports:

| Anomaly or observation type | Validated baseline | Severity | Disposition |
| --- | ---: | --- | --- |
| `customers_without_geolocation_prefix` | 278 | Warning | Retain the customer and source address; flag missing reference coverage and leave resolved coordinates unavailable |
| `customer_prefixes_without_geolocation_geolocation` | 157 | Informational | Monitor the distinct missing customer ZIP prefixes and investigate material baseline changes |
| `sellers_without_geolocation_prefix` | 7 |7 | Warning | Retain the seller and source address; flag missing reference coverage and leave resolved coordinates unavailable |
| `seller_prefixes_without_geolocation` | 7 | Informational | Monitor the distinct missing seller ZIP prefixes and investigate material baseline changes |
| `customers_disagreeing_with_modal_geolocation_state` | 0 | Warning | Preserve both values and prevent unreviewed geographic correction if customer-state consistency changes |
| `sellers_disagreeing_with_modal_geolocation_state` | 35 | Warning | Preserve the source state, expose the resolved state and mismatch flag, and use the resolved state only through documented downstream logic |
| `geolocation_prefixes_with_multiple_states` | 8 | Warning | Preserve all observations and resolve state downstream using an explicit deterministic rule |
| `geolocation_prefixes` using an explicit deterministic rule |
| `geolocation_prefixes_without_customer_or_seller` | 4,099 | Informational | Retain unused geographic reference coverage without treating it as invalid |
| `geolocation_prefixes_with_modal_state_ties` | 0 | Warning | Preserve all observations, apply the approved deterministic tie-breaker, and flag the ambiguous resolution for investigation |

These controls remain non-blocking at staging grain.

---

### 9.8 Canonical Modelling Implications

Mercury requires a resolved geographic reference with:

```text
One row per geolocation ZIP-code prefix
```

The resolved relation SHOULD expose:

- geolocation_zip_code_prefix;
- resolved state;
- resolved city or city key;
- representative latitude;
- representative longitude;
- source observation count;
- distinct observation count;
- state-ambiguity indicator;
- city-ambiguity indicator;
- coordinate-ambiguity indicator;
- documented resolution method.

The modal-state rule is validated for the current Olist source.

City and coordinate resolution MUST also be deterministic and documented before canonical implementation. A robust representatice-coordinate method should reduce sensitivity to isolated coordinate outliers.

Customer and seller dimensions SHOULD preserve:

- source city;
- source state;
- resolved geographic state;
- resolved geographic key where available;
- geographic coverage flag;
- state-mismatch flag.

For the 35 known seller mismatches, downstream geographic models may use the resolved state while preserving the original source state for lineage and investigation. This is a deterministic downstream correction under ADR-013, not a staging rewrite.

Entities without matching geolocation prefixes remain valid. They must not be removed from non-geographic analysis.

---

### 9.9 Findings

The geographic exploration establishes that:

- 1. Geolocation ZIP prefixes are not unique in staging.
- 2. Direct geolocation joins cause extreme row amplification.
- 3. Customer and seller coverage is high but incomplete.
- 4. Missing geographic coverage does not invalidate an entity.
- 5. Most geographic prefixes contain multiple observations and coordinates.
- 6. Eight prefixes contain isolated conflicting state observations.
- 7. A deterministic modal-state rule resolves those prefixes without ties.
- 8. The modal state agrees with every covered customer.
- 9. Thirty-five sellers contain source states inconsistent with ZIP-based geographic evidence.
- 10. Canonical models require a resolved one-row-per-ZIP geographic reference.
- 11. Source and resolved geographic attributes must remain distinguishable.

---

## 10. Cross-Relationship Join Amplification

**Status:** Planned

This section will evaluate combinations of multiple one-to-many relationships, particularly:

```text
orders
   |
   +-- order_items
   |
   +-- payments
   |
   +-- reviews
```

Directly joining multiple child relations at their source grains may multiply measures and produce analytically incorrect totals.

---

## 11. Completion Criteria

Relationship exploration is complete when:

- [x] customer–order relationships are fully profiled
- [x] order–order-item relationships are profiled
- [x] order–payment relationships are profiled
- [x] order–review relationships are profiled
- [x] product–order-item relationships are profiled
- [x] seller–order-item relationships are profiled
- [x] geographic relationships are profiled
- [ ] orphaned records and missing children are documented
- [ ] cardinalities are validated
- [ ] join amplification is measured
- [ ] related monetary measures are reconciled
- [ ] relationship anomalies have documented dispositions
- [ ] canonical modelling inputs and open decisions are recorded