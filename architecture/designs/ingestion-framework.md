# Mercury Ingestion Framework

## Purpose

The ingestion framework defines how source data enters Mercury.

Its purpose is to provide a consistent, reusable pattern for extracting data from independent source systems and preserving it in the Raw Landing layer.

The framework separates source-specific extraction logic from shared platform capabilities such as configuration, logging, validation, metadata generation, and raw file storage.

---

## Design Goals

The ingestion framework should:

- support multiple independent source systems;
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

The initial implementation supports batch ingestion from local public datasets.

The framework will first ingest the Olist e-commerce dataset, with individual files representing separate Nova Commerce operational systems.

The initial version will not include:

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

| Mercury Source | Reference Dataset |
|---|---|
| Commerce Platform | Orders and order items |
| Customer Platform | Customers |
| Product Catalogue | Products and category translation |
| Payment Platform | Order payments |
| Review Platform | Order reviews |
| Seller Platform | Sellers |
| Logistics Platform | Order delivery timestamps and geolocation |

Each source is ingested independently and receives its own configuration, execution metadata, and raw landing path.

---

## High-Level Flow

```mermaid
flowchart LR
    A[Source System] --> B[Source Connector]
    B --> C[Basic Source Validation]
    C --> D[Immutable Raw File]
    D --> E[Ingestion Metadata]
    E --> F[Raw Landing Zone]