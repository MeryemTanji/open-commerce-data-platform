# ADR-004 — Publish Reusable Data Products

## Status

Accepted

## Date

2026-07-14

---

## Context

Modern analytics teams often create datasets for individual reports, dashboards, or machine learning projects.

As new business requirements emerge, transformation logic is frequently duplicated across teams, resulting in inconsistent business definitions, increased maintenance effort, and limited reuse.

Mercury aims to solve this problem by publishing reusable data products that can serve multiple analytical use cases from a shared business foundation.

---

## Decision

Mercury will publish curated data products built upon the canonical business model.

A data product represents a trusted, documented, and reusable business asset rather than a dataset created for a single consumer.

Each data product will:

- solve a clearly defined business problem;
- expose stable business definitions;
- be independently documented;
- include automated quality validation;
- be reusable across dashboards, analytics, applications, and machine learning workloads.

Data products are considered the primary interface between the platform and its consumers.

---

## Rationale

Publishing reusable data products allows Mercury to separate platform engineering from individual analytical projects.

Rather than rebuilding business logic for every report or application, consumers access trusted datasets that already implement common business definitions.

This approach provides several advantages:

- reduced duplication;
- faster analytical development;
- consistent business metrics;
- simplified maintenance;
- improved governance;
- easier onboarding of new consumers.

Data products become long-lived platform assets rather than temporary project deliverables.

---

## Examples

Examples of data products include:

- Customer 360
- Sales Performance
- Product Performance
- Seller Performance
- Delivery Performance
- Customer Lifetime Value Features

Each product is derived from the canonical business model and may support multiple downstream use cases simultaneously.

---

## Alternatives Considered

### Build datasets for individual projects

Rejected.

Project-specific datasets duplicate business logic and increase long-term maintenance costs.

---

### Allow each consumer to transform canonical data

Rejected.

This approach creates inconsistent business definitions and reduces trust in analytical outputs.

---

### Publish reusable data products (Accepted)

Accepted.

Reusable data products establish a shared analytical foundation while reducing duplicated engineering effort across future use cases.

---

## Consequences

### Benefits

- Reusable analytical assets
- Consistent business definitions
- Faster delivery of new use cases
- Reduced engineering effort
- Improved governance
- Better scalability

### Trade-offs

- Additional modelling effort
- Product ownership required
- Documentation must be maintained
- Strong governance becomes more important

These trade-offs are acceptable because reusable data products are the primary mechanism through which Mercury delivers long-term value.

## Related Decisions

- ADR-001 — Adopt a Layered Data Platform Architecture
- ADR-002 — Preserve Immutable Raw Data
- ADR-003 — Adopt a Canonical Business Model