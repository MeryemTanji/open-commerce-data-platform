# ADR-001 — Adopt a Layered Data Platform Architecture

## Status

Accepted

## Date

2026-07-14

---

## Context

Modern organizations generate operational data across multiple business systems.

Without a common architectural foundation, data platforms often evolve into collections of project-specific pipelines, duplicated transformation logic, and isolated analytical solutions.

As new business initiatives emerge, engineering teams repeatedly solve the same foundational problems instead of building on shared capabilities.

Mercury aims to demonstrate a different approach.

Rather than building pipelines for individual use cases, Mercury is designed as a reusable data foundation upon which multiple analytical products can be developed.

The platform therefore requires an architecture that separates ingestion, standardization, business modelling, and data product generation into clearly defined responsibilities.

---

## Decision

Mercury adopts a layered data platform architecture consisting of:

Operational Sources

↓

Raw Landing

↓

Staging

↓

Canonical Data Model

↓

Data Products

↓

Applications & Analytics

Each layer has a single responsibility and communicates only with adjacent layers.

The architecture emphasizes reuse, standardization, and independent evolution of each layer.

---

## Rationale

A layered architecture provides several long-term advantages.

- Raw operational data is preserved for replay and auditing.
- Data standardization is isolated from business logic.
- Canonical models provide consistent business definitions.
- Data products can be developed without modifying ingestion pipelines.
- New analytical use cases reuse existing platform capabilities instead of creating new pipelines.

This approach prioritizes building a reusable foundation before building individual analytical solutions.

---

## Alternatives Considered

### Project-specific pipelines

Rejected.

Although simple initially, project-based pipelines duplicate logic, increase maintenance costs, and reduce consistency across analytical solutions.

### Single transformation layer

Rejected.

Combining ingestion, cleaning, and business modelling into one layer creates tightly coupled pipelines that become difficult to maintain as the platform grows.

### Layered data platform (Accepted)

Accepted.

Provides clear separation of concerns, improves maintainability, enables reusable data products, and supports incremental platform growth.

---

## Consequences

### Benefits

- Reusable platform capabilities
- Standardized engineering patterns
- Easier testing
- Better governance
- Simplified onboarding of new data sources
- Independent evolution of platform layers

### Trade-offs

- More platform components
- Additional documentation
- Increased orchestration complexity
- Slightly higher storage requirements

These trade-offs are considered acceptable because they support Mercury's primary objective:

**Build a reusable data foundation rather than isolated data pipelines.**