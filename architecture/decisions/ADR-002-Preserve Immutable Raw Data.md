# ADR-002 — Preserve Immutable Raw Data

## Status

Accepted

## Date

2026-07-14

---

## Context

Mercury is designed to integrate operational data from multiple independent source systems.

Source data may contain inconsistencies, missing values, duplicates, schema changes, or late-arriving records. As business requirements evolve, transformation logic will also change over time.

Without preserving the original source data, historical transformations become difficult to reproduce, debugging data quality issues becomes more complex, and downstream models cannot be reliably rebuilt.

Mercury therefore requires a trustworthy and reproducible foundation upon which all subsequent transformations can be performed.

---

## Decision

Mercury will preserve all source data exactly as it is received.

The Raw Landing layer is immutable.

Data stored in this layer will not be modified, cleaned, deduplicated, enriched, or transformed.

Every source system is ingested independently, preserving both the original payload and ingestion metadata.

All business transformations occur only in downstream platform layers.

---

## Rationale

Separating data ingestion from data transformation creates a clear boundary between operational systems and analytical processing.

An immutable raw layer provides several engineering advantages:

- reproducible data pipelines;
- replayability of historical data;
- simplified debugging;
- traceability from data products back to source systems;
- protection against accidental data loss;
- independent evolution of transformation logic.

This separation allows Mercury to rebuild downstream layers without requiring data to be extracted again from operational systems.

---

## Alternatives Considered

### Transform data during ingestion

Rejected.

Cleaning or modifying data during ingestion permanently alters the original operational records and makes historical replay difficult.

---

### Store only transformed data

Rejected.

Discarding raw operational data removes the platform's ability to reproduce historical processing, investigate data quality issues, or adapt to changing business rules.

---

### Preserve immutable raw data (Accepted)

Accepted.

Preserving raw operational data establishes a reliable system of record while allowing downstream transformations to evolve independently.

---

## Consequences

### Benefits

- Reproducible pipelines
- Replayable historical data
- Improved debugging
- Better data lineage
- Clear separation of concerns
- Greater platform resilience

### Trade-offs

- Increased storage requirements
- Additional orchestration steps
- More platform components to maintain

These trade-offs are considered acceptable because storage is significantly less expensive than rebuilding or recovering lost operational data.

---

## Related Decisions

- ADR-001 — Adopt a Layered Data Platform Architecture