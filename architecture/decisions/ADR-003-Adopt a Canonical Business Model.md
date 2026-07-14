# ADR-003 — Adopt a Canonical Business Model

## Status

Accepted

## Date

2026-07-14

---

## Context

Mercury integrates operational data from multiple independent business systems.

Each source system represents business entities differently, using its own schemas, naming conventions, identifiers, and data structures.

If downstream consumers interact directly with source-specific schemas, every analytical use case becomes tightly coupled to the operational systems that generated the data.

As additional source systems are introduced, analytical models become increasingly difficult to maintain and business definitions become inconsistent.

Mercury therefore requires a stable business representation that remains independent of any individual operational system.

---

## Decision

Mercury adopts a canonical business model.

Rather than exposing source-specific schemas, Mercury transforms operational data into shared business entities that represent the organization's core concepts.

Examples include:

- Customer
- Product
- Order
- Seller
- Payment
- Review
- Delivery

These canonical entities become the foundation for all downstream data products.

---

## Rationale

The canonical business model separates operational systems from analytical consumers.

Changes to source systems can be absorbed within the ingestion and staging layers without affecting downstream business models.

This approach provides several advantages:

- consistent business definitions;
- reusable transformation logic;
- simplified reporting;
- reduced coupling between systems;
- improved maintainability;
- easier onboarding of new data sources.

Business users consume stable concepts rather than technical source-system schemas.

---

## Alternatives Considered

### Expose source-system schemas

Rejected.

Consumers become tightly coupled to operational systems, making reporting and analytics difficult to maintain as source systems evolve.

---

### Build project-specific models

Rejected.

Creating separate business models for each analytical use case duplicates transformation logic and prevents reuse across the platform.

---

### Canonical business model (Accepted)

Accepted.

A shared business model establishes consistent business definitions while allowing operational systems to evolve independently.

---

## Consequences

### Benefits

- Stable business definitions
- Reusable analytical models
- Lower maintenance effort
- Simplified source system integration
- Improved platform consistency
- Easier cross-domain analytics

### Trade-offs

- Additional transformation layer
- Initial modelling effort
- Governance required for canonical definitions

These trade-offs are considered acceptable because they create a long-term reusable foundation for analytical development.

---

## Related Decisions

- ADR-001 — Adopt a Layered Data Platform Architecture
- ADR-002 — Preserve Immutable Raw Data