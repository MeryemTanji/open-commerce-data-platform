# ADR-005 — Introduce a Shared CSV Connector Abstraction

## Status

Accepted

## Date

2026-08-15

---

## Context

Mercury's ingestion framework was intentionally designed in layers.

`BaseConnector` owns the format-agnostic ingestion lifecycle for one source:

1. create ingestion metadata;
2. validate the source;
3. count logical records;
4. land the source unchanged through the configured storage capability;
5. record success or failure.

Concrete connectors were then implemented for all eight Olist source objects:

- Customers;
- Orders;
- Order Items;
- Products;
- Sellers;
- Payments;
- Reviews;
- Geolocations.

The connectors were deliberately implemented independently before introducing a shared CSV abstraction.

This avoided premature abstraction. Early in the project there was insufficient evidence to know which behaviors were genuinely common across CSV sources and which similarities were specific to the first few datasets.

After implementing all eight connectors, a stable technical pattern became clear.

Every CSV connector requires the same technical behavior:

- verify that the source path exists;
- verify that the source path is a regular file;
- require a `.csv` extension, case-insensitively;
- reject zero-byte files;
- open files using `utf-8-sig`;
- parse CSV safely using Python's `csv` module;
- require a header;
- verify source-specific required columns;
- allow additional columns;
- ignore column ordering;
- count logical CSV records excluding the header;
- correctly handle quoted fields and multiline records;
- preserve source values without transformation.

The parts that differ between connectors are primarily declarative or domain-specific:

- `SOURCE_SYSTEM`;
- `SOURCE_OBJECT`;
- required source columns;
- dataset grain;
- source-level keys or lack of a unique key;
- relationship keys;
- source-specific documentation;
- downstream business-quality expectations.

The repeated CSV behavior is therefore no longer incidental duplication. It represents a proven source-format capability that can be separated from the generic ingestion lifecycle.

---

## Decision

Mercury will introduce a shared abstract CSV connector layer:

```text
BaseConnector
    ↓
BaseCsvConnector
    ↓
Concrete CSV Connectors
```

`BaseConnector` remains format-agnostic.

`BaseCsvConnector` will own only technical behavior that has been proven common across CSV sources.

Concrete connectors will inherit from `BaseCsvConnector` and provide their source-specific configuration and domain documentation.

---

## Responsibility Boundaries

### `BaseConnector`

`BaseConnector` owns the generic ingestion lifecycle.

It is responsible for:

- ingestion execution lifecycle;
- ingestion metadata creation;
- success/failure handling;
- calling source validation;
- calling logical record counting;
- handing the source artifact to the configured storage abstraction.

It must not contain:

- CSV parsing assumptions;
- CSV encoding assumptions;
- source-specific required columns;
- business rules;
- BigQuery behavior;
- transformation logic.

---

### `BaseCsvConnector`

`BaseCsvConnector` owns shared technical CSV behavior.

It is responsible for:

- validating that the source is an accessible regular CSV file;
- rejecting empty files;
- opening CSVs with `utf-8-sig`;
- parsing headers and logical records safely;
- validating source-specific required columns supplied by subclasses;
- allowing additional columns;
- treating column order as non-semantic;
- counting logical data records excluding the header;
- preserving quoted and multiline CSV semantics.

It must not:

- rename fields;
- cast source values;
- trim or normalize source values;
- deduplicate records;
- apply business-quality rules;
- define source grain;
- define business keys;
- join sources;
- write directly to BigQuery.

---

### Concrete CSV Connectors

Each concrete connector owns the identity and source contract of one source object.

A concrete connector defines:

- `SOURCE_SYSTEM`;
- `SOURCE_OBJECT`;
- required source columns;
- source grain;
- known keys and relationships;
- source-specific documentation.

Concrete connectors should contain minimal executable logic where the shared CSV behavior is sufficient.

This makes the source-specific classes declarative rather than duplicating CSV mechanics.

---

## Required-Column Validation

Each concrete connector declares the columns required for its source contract.

`BaseCsvConnector` validates that those required fields are present.

Additional source columns are allowed.

Column order is not significant.

This means a source delivery may evolve by adding unused fields without automatically breaking ingestion, while removal of fields Mercury currently depends on fails clearly.

Automatic schema evolution is not part of this decision.

---

## Raw Preservation

The CSV abstraction performs structural validation only.

It does not transform the source artifact before Raw Landing.

The source file remains the artifact passed to the storage layer.

Therefore:

```text
Source CSV
    ↓
Structural Validation
    ↓
StorageManager
    ↓
Raw Landing
```

does not become:

```text
Source CSV
    ↓
Cleaned/Rewritten CSV
    ↓
Raw Landing
```

Business interpretation remains downstream.

---

## Logical Record Counting

CSV record counting must use CSV-aware parsing rather than naïve line counting.

This matters because fields such as review comments may legally contain quoted embedded newlines.

For example, one logical CSV record may span multiple physical text lines.

Mercury therefore counts parsed CSV records, excluding the header.

This keeps `record_count` consistent with the records a downstream CSV reader would observe.

---

## Encoding

Version 1 uses:

```text
utf-8-sig
```

for CSV reading.

This handles ordinary UTF-8 files while tolerating a UTF-8 byte-order mark when present.

The abstraction does not perform character-set conversion or text normalization.

If a future source uses a different encoding, that requirement should be introduced explicitly rather than silently guessed.

---

## Relationship to Storage

CSV handling and physical Raw storage remain separate capabilities.

Conceptually:

```text
BaseCsvConnector
        ↓
StorageManager
        ├── LocalStorageManager
        └── GCSStorageManager
```

The connector validates and describes the source.

The storage implementation determines how the unchanged source artifact is physically landed.

This boundary is formalized further by ADR-006.

---

## Relationship to Future Source Types

`BaseCsvConnector` is intentionally a CSV-specific abstraction.

It is not intended to become a universal source connector.

Future transports or formats may justify their own abstractions, for example:

```text
BaseConnector
    ├── BaseCsvConnector
    ├── Future API Connector
    └── Future Database Connector
```

A REST API, JSON source, database export, or streaming source should not be forced through CSV-specific behavior solely to reuse this abstraction.

This preserves Mercury's broader goal of supporting heterogeneous source systems.

---

## Alternatives Considered

### Alternative 1 — Keep CSV Logic in Every Concrete Connector

Rejected because all eight connectors demonstrated the same stable technical CSV behavior.

Continuing to duplicate it would:

- increase maintenance cost;
- make fixes inconsistent;
- create larger source-specific classes;
- increase the risk of behavior drifting between connectors.

---

### Alternative 2 — Introduce the Abstraction Before Implementing All Connectors

Rejected during the initial connector work.

At that stage, the common behavior had not yet been proven.

Waiting allowed Mercury to abstract from evidence rather than speculation.

---

### Alternative 3 — Move CSV Logic into `BaseConnector`

Rejected because `BaseConnector` is intentionally format-agnostic.

Adding CSV assumptions there would make future non-CSV source types inherit irrelevant behavior.

---

### Alternative 4 — Create a Generic Universal Parser Abstraction

Rejected as premature.

Mercury currently has a proven CSV pattern, not a proven universal parsing pattern.

Additional abstractions should be introduced only when multiple concrete implementations justify them.

---

## Consequences

### Positive

- removes repeated CSV implementation across eight connectors;
- keeps `BaseConnector` format-agnostic;
- centralizes CSV parsing and validation behavior;
- makes technical fixes apply consistently to all CSV sources;
- reduces concrete connectors to source-specific contracts;
- preserves a clean path for future non-CSV connectors;
- improves testability of shared CSV behavior.

### Trade-Offs

- introduces another inheritance layer;
- changes concrete connectors from independently implemented classes to subclasses of a common CSV base;
- requires care not to move domain-specific logic into the shared abstraction.

These trade-offs are accepted because the abstraction was introduced only after the common behavior had been demonstrated repeatedly.

---

## Implementation Outcome

The resulting connector hierarchy is:

```text
BaseConnector
    ↓
BaseCsvConnector
    ↓
├── CustomersConnector
├── OrdersConnector
├── OrderItemsConnector
├── ProductsConnector
├── SellersConnector
├── PaymentsConnector
├── ReviewsConnector
└── GeolocationConnector
```

All eight connectors continue to expose their existing source identities and source contracts while sharing one CSV implementation.

The abstraction does not change:

- Raw source values;
- storage behavior;
- ingestion metadata semantics;
- source grain;
- downstream transformation responsibilities.

---

## Decision Summary

Mercury will use `BaseCsvConnector` as the shared technical abstraction for proven CSV behavior.

`BaseConnector` remains responsible for the format-independent ingestion lifecycle.

Concrete connectors remain responsible for source identity, schema requirements, grain, relationships, and source-specific documentation.

The decision follows Mercury's broader principle:

> Abstract only after repeated implementations demonstrate a stable common capability.