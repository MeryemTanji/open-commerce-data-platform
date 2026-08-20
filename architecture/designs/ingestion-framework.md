# Mercury Ingestion Framework

## Purpose

The ingestion framework defines how source data enters Mercury.

Its purpose is to provide a consistent, reusable pattern for extracting data from independent source systems and preserving it in the Raw Landing layer.

The framework separates source-specific extraction logic from shared platform capabilities such as configuration, logging, validation, metadata generation, and raw file storage.

---

## Design Goals

The ingestion framework should:

- support multiple independent source systems;
- support sources with different refresh and delivery patterns;
- support historical replay of incremental source deliveries;
- preserve source data without transformation;
- use a consistent connector interface;
- produce structured ingestion metadata;
- support repeatable and idempotent execution;
- fail clearly and safely;
- remain simple enough to run locally;
- allow future deployment to cloud execution services;
- minimize source-specific code outside individual connectors.

---

## Scope

The initial implementation supports batch ingestion from public datasets, including one-off master/reference loads and simulated daily incremental deliveries derived from historical source data.

The framework first ingests the Olist e-commerce dataset, with individual files treated as separate Nova Commerce operational source objects.

The initial version does not include:

- real-time streaming;
- change data capture;
- direct production API integrations;
- distributed processing;
- automatic schema evolution;
- enterprise secrets management.

These capabilities may be introduced later when justified by a concrete requirement.

---

## Source-System Model

Although the initial data originates from one public dataset, Mercury treats each business function as an independent operational source.

| Mercury Source | Source Object | Reference Dataset |
|---|---|---|
| Customer Platform | Customers | `olist_customers_dataset.csv` |
| Order Platform | Orders | `olist_orders_dataset.csv` |
| Order Platform | Order Items | `olist_order_items_dataset.csv` |
| Product Catalogue | Products | `olist_products_dataset.csv` |
| Marketplace Platform | Sellers | `olist_sellers_dataset.csv` |
| Payment Platform | Payments | `olist_order_payments_dataset.csv` |
| Review Platform | Reviews | `olist_order_reviews_dataset.csv` |
| Public Geographic Source | Geolocations | `olist_geolocation_dataset.csv` |

Each source is ingested independently and receives its own configuration, execution metadata, and Raw Landing path.

---

## Source Delivery Patterns

Mercury does not assume that every source system delivers data at the same frequency or using the same loading pattern.

In a real commerce environment, some operational sources continuously produce new transactional data, while other sources behave more like master or reference datasets and may change less frequently.

The Olist dataset is provided as a collection of static historical CSV files. To make Mercury behave more like a real data platform, the ingestion framework simulates different source-delivery patterns using the temporal information that actually exists in the source data.

Mercury Version 1 distinguishes between:

1. **initial / one-off source loads**;
2. **daily incremental source loads**.

The framework does not fabricate timestamps or artificial update histories for datasets that do not contain reliable temporal information.

---

### Initial / One-Off Loads

The following sources are treated as master or reference datasets during Version 1:

| Source Object | Version 1 Loading Pattern | Rationale |
|---|---|---|
| Customers | Initial load | The Olist customer dataset does not contain a reliable customer-created timestamp. Mercury therefore treats the available customer population as an existing customer master at the beginning of the simulation. |
| Products | Initial load | Product creation or update timestamps are not available. Mercury Version 1 assumes the product catalogue remains stable during the simulated period rather than inventing product-history events. |
| Sellers | Initial load | Seller creation or onboarding timestamps are not available. Mercury therefore treats the seller population as an existing marketplace master dataset. |
| Geolocations | Initial load | Geolocation data is external geographic reference data rather than transactional business activity and is treated as static during Version 1. |

These sources may change in a real production environment.

For example, a real commerce platform would onboard new customers, products, and sellers over time. Mercury deliberately does not simulate those changes unless the source data provides a defensible way to determine when they occurred.

This keeps the simulation grounded in the source rather than manufacturing temporal behaviour solely for demonstration purposes.

---

### Daily Incremental Loads

Transactional sources with reliable temporal information are replayed as daily incremental deliveries.

| Source Object | Incremental Date Logic |
|---|---|
| Orders | `order_purchase_timestamp` |
| Order Items | Derived from the parent Order's `order_purchase_timestamp` |
| Payments | Derived from the parent Order's `order_purchase_timestamp` |
| Reviews | `review_creation_date` |

Each simulated daily delivery contains only the records associated with that business date.

This is an **incremental delivery model**, not a cumulative snapshot model.

For example:

```text
2017-05-01
    orders created on 2017-05-01

2017-05-02
    orders created on 2017-05-02

2017-05-03
    orders created on 2017-05-03
```

### Simulated Delivery and Ingestion Dates

Mercury distinguishes the business date represented by a source delivery from the date on which that delivery is ingested.

For the Olist historical simulation:

```text
delivery_date
    = business date represented by the source records

ingestion_date
    = simulated date on which Mercury processes that delivery
```

Transactional daily deliveries are simulated as being ingested on the following calendar day:

```text
ingestion_date = delivery_date + 1 day
```

For example:

```text
order_purchase_timestamp = 2017-05-19
delivery_date             = 2017-05-19
ingestion_date            = 2017-05-20
```

The `delivery_date` remains the logical date of the incremental delivery and determines the corresponding business-date partition in Raw storage and BigQuery.

The `ingestion_date` represents when the simulated ingestion process runs.

This `+1 day` relationship is specific to the Olist historical simulation. It is not a generic Mercury ingestion rule and must not be encoded into reusable connector, storage, warehouse-loading, replay, or recovery components.

A future production source integration should provide its actual delivery and processing timing according to that source's real delivery behaviour rather than applying the Olist simulation rule.