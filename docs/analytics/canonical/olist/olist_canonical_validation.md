# Olist Canonical Model Validation

## Status

Passed

## Validation Date

2026-10-21

## Purpose

This document records the implementation and publication evidence for Mercury's initial Olist canonical model.

Detailed grains, semantics, anomaly dispositions, and publication requirements remain defined in the Olist canonical contracts.

## 1. Published Inventory

The canonical graph contains 14 relations:

- five dimensions:
  - `dim_customer`;
  - `dim_date`;
  - `dim_location`;
  - `dim_product`;
  - `dim_seller`;
- four facts:
  - `fct_orders`;
  - `fct_order_items`;
  - `fct_payments`;
  - `fct_reviews`;
- one bridge:
  - `bridge_order_reviews`;
- four governed intermediate relations:
  - `int_geolocation_resolution`;
  - `int_order_item_summary`;
  - `int_order_payment_summary`;
  - `int_order_review_summary`.

## 2. Dataform Validation

The complete Dataform project compiled successfully with:

- 118 actions;
- 35 datasets;
- 83 assertions.

The canonical publication selection contained:

- 14 canonical relations;
- 62 canonical assertions.

All canonical relations:

- compiled successfully;
- passed BigQuery dry-run validation;
- executed successfully.

All canonical assertions passed.

The 13 non-blocking staging quality observations also compiled and executed successfully.

## 3. Source Reconciliation

The validated canonical event counts are:

| Canonical relation | Validated row count |
| --- | ---: |
| `fct_orders` | 99,441 |
| `fct_order_items` | 112,650 |
| `fct_payments` | 103,886 |
| `fct_reviews` | 98,410 |
| `bridge_order_reviews` | 99,224 |

The bridge preserves all 99,224 distinct staged order–review associations.

The review model publishes 98,410 distinct review identities while preserving repeated review associations through the bridge.

## 4. Monetary Reconciliation

The canonical order-item population reconciles to:

| Measure | Validated total |
| --- | ---: |
| Item price | 13,591,643.70 |
| Freight | 2,251,909.54 |
| Item-based order total | 15,843,553.24 |

The order-level reconciliation distribution is:

| Status | Order count |
| --- | ---: |
| `reconciled` | 98,362 |
| `payment_above_item_total` | 264 |
| `payment_below_item_total` | 39 |
| `not_comparable_missing_items` | 775 |
| `not_comparable_missing_payments` | 1 |

Differences remain visible and are not corrected by overwriting independently meaningful measures.

## 5. Publication Safeguards

The executed controls validated:

- declared relation grains;
- deterministic canonical keys;
- source-to-canonical row reconciliation;
- required parent references;
- role-specific date references;
- customer, product, and seller resolution;
- lifecycle and chronology contracts;
- review consolidation safety;
- bridge association preservation;
- independently aggregated child summaries;
- monetary reconciliation behaviour;
- prevention of unintended join amplification.

Approved warning-level anomalies remain observable without blocking otherwise valid canonical records.

## 6. Infrastructure Boundary

The `canonical` BigQuery dataset and its IAM boundary remain managed through Terraform.

Dataform may create and modify relations inside the dataset but may not create datasets or administer IAM.

No infrastructure change was required for canonical model publication.

## 7. Result

The initial Olist canonical graph satisfies its documented publication contract and is approved as the governed foundation for reusable data products.

Production scheduling, persistent quality history, alert delivery, and operational monitoring remain Phase 4 responsibilities.