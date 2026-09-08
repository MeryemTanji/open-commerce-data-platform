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

### 3.6 Canonical modelling implications

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

### 3.7 Remaining customer exploration

Before finalizing the canonical customer design, Mercury must investigate whether multiple customer records associated with the same `customer_unique_id` contain different:

- ZIP-code prefixes;
- cities;
- states;
- observed order timestamps.

This will determine whether customer location can be treated as a single stable attribute or requires order-contextual or historically varying treatment.

---

## 4. Order–Order Item Relationship

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

**Status:** Planned

---

## 6. Order–Review Relationship

**Status:** Planned

---

## 7. Product–Order Item Relationship

**Status:** Planned

---

## 8. Seller–Order Item Relationship

**Status:** Planned

---

## 9. Geographic Relationships

**Status:** Planned

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
- [ ] order–payment relationships are profiled
- [ ] order–review relationships are profiled
- [ ] product–order-item relationships are profiled
- [ ] seller–order-item relationships are profiled
- [ ] geographic relationships are profiled
- [ ] orphaned records and missing children are documented
- [ ] cardinalities are validated
- [ ] join amplification is measured
- [ ] related monetary measures are reconciled
- [ ] relationship anomalies have documented dispositions
- [ ] canonical modelling inputs and open decisions are recorded