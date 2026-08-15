# ADR-005 — Introduce a Shared CSV Connector Abstraction

## Status

Accepted

## Context

Mercury's ingestion framework was intentionally designed in layers.

`BaseConnector` owns the format-agnostic ingestion lifecycle for a single source:

1. create ingestion metadata
2. validate the source
3. count logical records
4. land the source unchanged in Raw storage
5. record success or failure

Concrete connectors were then implemented for the eight Olist source objects:

- Customers
- Orders
- Order Items
- Products
- Sellers
- Payments
- Reviews
- Geolocations

The concrete connectors were deliberately implemented independently before introducing a shared CSV abstraction.

This was done to avoid premature abstraction. At the beginning of the project, there was not enough evidence to know which behaviors were genuinely common across source connectors and which similarities were specific to the first few datasets.

After implementing all eight connectors, a stable pattern became clear.

Every connector performs the same CSV-specific technical operations:

- verify that the source path exists
- verify that the source path is a regular file
- require a `.csv` extension, case-insensitively
- reject zero-byte files
- open the file using `utf-8-sig`
- parse the source using `csv.DictReader`
- require a header
- verify that all source-specific required columns exist
- allow additional columns
- ignore column ordering
- count logical CSV records excluding the header
- preserve quoted fields and multiline CSV semantics
- avoid modifying or transforming source data

The parts that differ between connectors are primarily declarative or domain-specific:

- `SOURCE_SYSTEM`
- `SOURCE_OBJECT`
- required columns
- dataset grain
- source-level key or lack of one
- relationship keys
- downstream business-quality expectations
- source-specific documentation

The repeated CSV implementation is therefore no longer incidental duplication. It represents a stable source-format capability that can be separated from the generic ingestion lifecycle.

## Decision

Mercury will introduce a new abstract class:

```text
BaseConnector
    ↓
BaseCsvConnector
    ↓
Concrete CSV connectors