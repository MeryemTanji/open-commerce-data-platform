# Olist Canonical Publication Contract

## Status

Draft

## Date

2026-09-21

## Purpose

This document defines the publication requirements for Mercury’s initial Olist canonical business model.

It establishes when a canonical relation or complete canonical build may be treated as valid, reusable, and safe for downstream consumption.

This contract translates the platform-wide canonical design, Olist model contracts, anomaly dispositions, and validated relationship findings into an executable publication boundary.

It does not repeat the complete column-level contracts or source-quality evidence maintained in the supporting Olist documentation.

## Governing Documents

This contract implements and depends on:

- [Canonical Model Design](../../../../architecture/designs/canonical_model_design.md)
- [Olist Canonical Model Overview](olist_canonical_model_overview.md)
- [Olist Canonical Dimension Contracts](olist_dimension_contracts.md)
- [Olist Canonical Fact Contracts](olist_fact_contracts.md)
- [Olist Staging Contracts](../../staging/olist_staging_contracts.md)
- [Olist Anomaly Disposition Register](../../staging/olist_anomaly_disposition.md)
- [Olist Relationship Profile](../../relationships/olist_relationship_profile.md)
- [ADR-013: Data Quality Anomaly Disposition and Monitoring Contract](../../../../architecture/decisions/ADR-013-Data%20Quality%20Anomaly%20Disposition%20and%20Monitoring%20Contract.md)

## 1. Scope

This document defines:

- the canonical publication boundary;
- canonical dependency and execution order;
- relation-level publication gates;
- blocking and non-blocking control behavior;
- row-count and grain reconciliation;
- canonical referential-integrity requirements;
- anomaly-disposition enforcement;
- join-amplification safeguards;
- monetary reconciliation requirements;
- validation and evidence requirements;
- initial completion criteria for the Olist canonical model.

This document does not define:

- Raw ingestion behavior;
- staging transformation logic;
- detailed canonical column contracts;
- source-anomaly baselines;
- operational quality-history storage;
- alert-delivery infrastructure;
- consumer-specific data products;
- dashboard-specific acceptance criteria.

Those concerns remain governed by their corresponding contracts and architectural decisions.

## 2. Publication Boundary

### 2.1 Published relations

The initial Olist canonical publication includes:

#### Dimensions

```text
canonical.dim_customer
canonical.dim_product
canonical.dim_seller
canonical.dim_date
canonical.dim_location
```

#### Facts

```text
canonical.fct_orders
canonical.fct_order_items
canonical.fct_payments
canonical.fct_reviews
```

#### Bridges

```text
canonical.bridge_order_reviews
```

Approved intermediate relations may support these models but are not part of the public canonical interface unless explicitly promoted through a reviewed contract change.

### 2.2 Publication meaning

A canonical relation is publishable when:

- its Dataform action executes successfully;
- its declared blocking controls execute successfully;
- every blocking control passes;
- its grain and key contract are satisfied;
- its required parent references are valid;
- governed anomaly dispositions are implemented;
- required source and staging reconciliation checks pass;
- no unknown control state remains unresolved.

A relation existing physically in BigQuery does not, by itself, mean that it is approved for consumption.

If a table is created or replaced before a dependent assertion fails, the affected execution is unsuccessful and the relation must not be treated as publishable.

### 2.3 Publication unit

Publication is evaluated at two levels:

| Level | Meaning |
| --- | --- |
| Relation publication | One canonical relation and all its blocking controls are valid |
| Graph publication | All required canonical relations and graph-level controls are valid |

A downstream data product may depend only on relations that have passed their complete publication gates.

The initial Olist canonical model is complete only when the full graph is publishable.

## 3. Publication States

Each relation execution has one of the following logical states:

| State         | Meaning                                                          |
| ------------- | ---------------------------------------------------------------- |
| `candidate`   | Relation was built but all required controls have not yet passed |
| `publishable` | Relation and all required blocking controls passed               |
| `rejected`    | At least one blocking control failed                             |
| `unknown`     | A required relation or control did not execute successfully      |

A rejected or unknown relation must not be interpreted as successfully published.

A previous successful state must not hide a failed or unknown current execution.

Operational persistence and historical evaluation of these states will be implemented as part of Mercury’s production observability boundary.

## 4. Canonical Dependency Order

### 4.1 Dependency principles

Every dependency must be declared through Dataform references or explicit action dependencies.

Canonical SQL must not rely on filename ordering or incidental execution order.

The dependency graph must remain acyclic.

Canonical facts must not depend on summaries derived from themselves.

When `fct_orders` requires item, payment, or review summaries, those summaries must be built directly from validated staging relations at one row per source order.

### 4.2 Logical execution order

The initial logical order is:

```text
Validated staging relations
        ↓
Canonical preparation relations
        ↓
Independent dimensions
        ↓
Dependent dimensions and review entities
        ↓
Order fact
        ↓
Order-item and payment facts
        ↓
Order–review bridge
        ↓
Canonical controls
        ↓
Publication decision
```

### 4.3 Relation dependencies

| Relation | Required upstream dependencies |
| --- | --- |
| `dim_date` | Governed calendar boundaries |
| `dim_location` | `stg_geolocations`; customer and seller postal-code references |
| `dim_customer` | `stg_customers` |
| `dim_product` | `stg_products` |
| `dim_seller` | `stg_sellers`; `dim_location` |
| `fct_reviews` | `stg_reviews`; `dim_date`; review-consolidation preparation |
| `fct_orders` | `stg_orders`; `stg_customers`; customer, location, and date dimensions; order-level summaries |
| `fct_order_items` | `stg_order_items`; `fct_orders`; product, seller, and date dimensions |
| `fct_payments` | `stg_payments`; `fct_orders` |
| `bridge_order_reviews` | Staged order–review associations; `fct_orders`; `fct_reviews` |

Intermediate order-level summaries must aggregate item, payment, and review evidence independently before joining it to `fct_orders`.

## 5. Control Classes

### 5.1 Blocking controls

A blocking control protects structural integrity, declared grain, key stability, required reference integrity, or publication safety.

A failing blocking control makes the affected relation rejected.

Blocking controls include:

- primary-key non-nullability;
- primary-key uniqueness;
- declared-grain uniqueness;
- required-value checks;
- deterministic-key consistency;
- required accepted-domain checks;
- required parent-reference checks;
- source-to-canonical row-count reconciliation;
- uncontrolled row-amplification detection;
- required monetary derivation checks;
- disposition-specific structural safeguards.

### 5.2 Non-blocking controls

A non-blocking control records a known or emerging quality condition without automatically rejecting an otherwise structurally valid relation.

Non-blocking controls include:

- approved source anomalies;
- known relationship-coverage gaps;
- baseline-aware cardinality observations;
- optional metadata absence;
- preserved chronology anomalies;
- source classifications requiring monitoring;
- reconciliation differences that must remain visible.

A non-blocking condition may remain publishable only when:

- the condition has a documented disposition;
- its severity is assigned;
- required lineage is preserved;
- the condition is exposed through the governed status or indicator;
- affected measures are withheld or qualified where required;
- its monitoring control executes successfully.

### 5.3 Unknown control states

A failed control execution is not equivalent to a passing control with zero anomalies.

If a required control cannot execute:

- its state is `unknown`;
- the affected publication decision remains unresolved;
- the execution must not be reported as successful;
- investigation is required before downstream approval.

## 6. Relation-Level Publication Gates

### 6.1 Dimension gates

| Relation | Required publication gates |
| --- | --- |
| `dim_customer` | Customer grain; deterministic key; unique and complete source identity |
| `dim_product` | Product grain; deterministic key; unique source identity; governed attribute domains |
| `dim_seller` | Seller grain; deterministic key; unique source identity; valid location reference |
| `dim_date` | Complete date range; unique date key; consistent calendar attributes |
| `dim_location` | Location grain; deterministic resolution; complete referenced-prefix coverage |

Detailed rules remain defined in the Olist dimension contracts.

### 6.2 Fact gates

| Relation | Required publication gates |
| --- | --- |
| `fct_orders` | Order grain; source-count preservation; customer and date resolution; lifecycle controls; safe summaries |
| `fct_order_items` | Item grain; source-count preservation; order, product, and seller resolution; monetary consistency |
| `fct_payments` | Payment grain; source-count preservation; order resolution; payment-value and anomaly consistency |
| `fct_reviews` | Review grain; safe payload consolidation; valid date references; chronology controls |

Detailed rules remain defined in the Olist fact contracts.

### 6.3 Bridge gates

`bridge_order_reviews` must satisfy:

- one row per `(order_key, review_key)`;
- non-null canonical parent keys;
- valid references to both parent relations;
- preservation of every publishable staged association;
- no fabricated association;
- no duplicate canonical relationship;
- preserved source relationship lineage.

## 7. Key and Grain Validation

### 7.1 Canonical keys

Every generated canonical key must be:

- non-null;
- deterministic;
- unique at the declared relation grain;
- derived from the approved key version and components;
- consistent with its preserved source identifiers.

A cryptographic hash does not remove the need for uniqueness or consistency assertions.

### 7.2 Source mappings

Every source-derived canonical relation must verify that:

- one canonical key does not map to multiple source-identifier combinations;
- one governed source identity does not map to multiple canonical keys;
- compound source keys use their components in the declared order;
- source namespaces are preserved and normalized consistently.

### 7.3 Grain preservation

Each relation must enforce the grain declared in its detailed contract.

A relation must be rejected when:

- duplicate rows exist at its declared grain;
- a join changes its grain unexpectedly;
- consolidation removes distinct business events;
- a one-to-many relationship is embedded without explicit aggregation;
- an intermediate relation violates its declared one-row-per-parent contract.

## 8. Row-Count Reconciliation

### 8.1 Direct source reconciliation

Physical canonical facts that preserve staged observations must reconcile with their staging inputs.

| Canonical relation | Reconciliation expectation |
| --- | --- |
| `fct_orders` | One row per staged order |
| `fct_order_items` | One row per staged order item |
| `fct_payments` | One row per staged payment |
| `fct_reviews` | One row per distinct publishable review identity |
| `bridge_order_reviews` | One row per distinct publishable staged order–review association |

Dimensions must reconcile to their governed identity grains rather than necessarily matching staging row counts.

### 8.2 Consolidated review reconciliation

Because staged review rows contain order associations, `fct_reviews` is reconciled against:

```text
COUNT(DISTINCT source_review_id)
```

after governed payload-consistency validation.

`bridge_order_reviews` is reconciled separately against distinct staged:

```text
(source_order_id, source_review_id)
```

associations whose canonical parents are publishable.

This separation prevents repeated associations from being mistaken for duplicate review entities.

### 8.3 Reconciliation failures

An unexplained row-count difference is blocking.

An approved difference must be:

- documented;
- reproducible;
- attributable to a governed disposition;
- visible in validation evidence;
- reflected in the relation’s reconciliation rule.

## 9. Referential Integrity

### 9.1 Required references

A populated canonical foreign key must resolve to exactly one row in its declared parent relation.

Required canonical relationships include:

| Child relation                     | Parent relation |
| ---------------------------------- | --------------- |
| `fct_orders.customer_key`          | `dim_customer`  |
| `fct_orders.customer_location_key` | `dim_location`  |
| `dim_seller.location_key`          | `dim_location`  |
| `fct_order_items.order_key`        | `fct_orders`    |
| `fct_order_items.product_key`      | `dim_product`   |
| `fct_order_items.seller_key`       | `dim_seller`    |
| `fct_payments.order_key`           | `fct_orders`    |
| `bridge_order_reviews.order_key`   | `fct_orders`    |
| `bridge_order_reviews.review_key`  | `fct_reviews`   |
| Role-specific date keys            | `dim_date`      |

### 9.2 Nullable references

A nullable canonical foreign key is permitted only when its detailed relation contract defines:

- the applicable unresolved-reference status;
- preservation of the source identifier;
- the affected downstream limitation;
- the corresponding quality control.

A missing canonical reference must not be concealed through a fabricated unknown member unless a future reviewed contract explicitly introduces one.

### 9.3 Reference-status consistency

When a relation exposes a reference status:

- `matched` requires a populated, valid canonical foreign key;
- a missing-reference status requires a `NULL` canonical foreign key;
- the original source identifier must remain available;
- unsupported status values are blocking.

## 10. Anomaly-Disposition Enforcement

### 10.1 Registered anomalies

Every anomaly affecting canonical publication must be registered in the Olist anomaly-disposition register.

The register remains authoritative for:

- control identity;
- validated baseline;
- severity;
- approved disposition;
- notification condition;
- ownership and response expectations.

This publication contract defines how those dispositions affect canonical acceptance without duplicating the complete register.

### 10.2 Canonical implementation

When a disposition requires canonical treatment, the affected model must implement the applicable combination of:

- source-value preservation;
- canonical reference status;
- anomaly indicator;
- resolved value and resolution method;
- conditional measure suppression;
- downstream-use restriction;
- deterministic aggregation;
- relationship preservation.

A documented disposition is not complete merely because the anomaly is mentioned in prose.

Its required treatment must be testable in the implemented canonical relation.

### 10.3 Zero-baseline conditions

A zero-baseline non-blocking control must still execute.

If its anomaly count becomes positive:

- the result is not silently treated as normal;
- the condition must be surfaced for engineering review;
- its existing future-response disposition applies;
- affected canonical outputs must respect any defined usage restriction.

Whether the condition rejects publication depends on its registered disposition and the safety of the implemented canonical treatment.

### 10.4 New anomaly types

A newly discovered anomaly type has no approved canonical disposition.

It must be:

- recorded;
- classified;
- assigned severity and ownership;
- investigated;
- given an explicit disposition;
- incorporated into the relevant contract before unqualified downstream use.

## 11. Join-Amplification Controls

### 11.1 Protected grains

The canonical model preserves distinct grains for:

- orders;
- order items;
- payments;
- reviews;
- order–review associations.

These relations must not be flattened into one uncontrolled detailed table.

### 11.2 Independent aggregation

When multiple child processes contribute to an order-grain output:

```text
order items
payments
reviews
```

each process must first be aggregated independently to one row per order.

Only those one-row-per-order summaries may be combined with `fct_orders`.

### 11.3 Amplification assertions

Canonical controls must verify that:

- joining a dimension does not change the child relation’s row count;
- joining one-row-per-order summaries does not change the order count;
- intermediate summaries contain no duplicate parent keys;
- item totals are not multiplied by payment or review cardinality;
- payment totals are not multiplied by item or review cardinality;
- review counts distinguish review entities from order–review associations.

An unexpected amplification factor greater than one is blocking unless the target relation explicitly declares the expanded grain.

## 12. Monetary Reconciliation

### 12.1 Independent measures

Mercury preserves:

```text
item_based_order_total
```

and:

```text
payment_total
```

as independently derived measures.

The item-based total is calculated from staged order-item evidence.

The payment total is calculated from staged payment evidence.

Neither value may overwrite the other.

### 12.2 Comparison boundary

Monetary reconciliation occurs only after:

- order items are aggregated to one row per order;
- payments are aggregated to one row per order;
- both summaries are joined safely to the order grain.

The approved comparison tolerance is:

```text
0.01
```

### 12.3 Reconciliation outcomes

The governed reconciliation outcomes are defined in the `fct_orders` contract.

Publication controls must verify that:

- the reconciliation status belongs to the approved domain;
- comparable totals produce the correct status;
- non-comparable orders are not assigned a reconciled outcome;
- the signed and absolute differences are internally consistent;
- missing evidence is not replaced with an inferred amount;
- zero-value payments remain preserved.

A reconciliation difference is not automatically a structural failure.

It remains publishable when its approved status and source evidence are preserved.

An internally inconsistent reconciliation result is blocking.

## 13. Non-Blocking Canonical Quality Outputs

Canonical quality views may expose conditions that should be monitored without rejecting structurally valid relations.

Such views may report:

- unresolved canonical references;
- source-to-resolved geographic mismatches;
- preserved lifecycle anomalies;
- payment-sequence and value observations;
- review chronology and reuse conditions;
- reconciliation outcomes;
- relation-level anomaly counts and rates.

A non-blocking canonical quality output must:

- use a stable anomaly type;
- expose an unambiguous count or affected-record grain;
- preserve traceability to the governed control;
- distinguish zero results from execution failure;
- avoid duplicating an existing control without adding canonical validation value.

The initial implementation may reuse staging and relationship-quality views when they already monitor the authoritative source condition.

A new canonical quality view is required only when the canonical transformation introduces a new resolution, aggregation, status, or publication risk.

## 14. Dataform Implementation Requirements

### 14.1 Relation configuration

Every canonical Dataform action must declare:

- relation type;
- `canonical` schema;
- stable relation name;
- meaningful description;
- appropriate tags;
- dependencies through `${ref()}` or explicit dependency declarations.

### 14.2 Blocking assertions

Built-in assertions may be used for:

- non-null columns;
- unique keys;
- accepted row conditions.

Custom assertions are required when publication safety depends on:

- compound reconciliation;
- referential integrity;
- deterministic-key mapping;
- row-count preservation;
- join-amplification detection;
- status-to-key consistency;
- payload-consolidation safety;
- cross-relation measure validation.

### 14.3 Non-blocking views

Non-blocking quality observations must use Dataform views or tables rather than assertions when their approved behavior is to report rather than fail.

Their names should follow:

```text
dq_<subject>_<condition>
```

unless an existing governed naming pattern already applies.

### 14.4 Intermediate relations

Intermediate relations must:

- have one clearly declared purpose;
- declare their grain;
- use a stable internal naming convention;
- remain outside the public canonical contract;
- avoid consumer-specific logic;
- include controls when their output protects downstream grain or measures.

An intermediate relation becoming a downstream dependency requires explicit review before it is treated as a public interface.

## 15. Validation Sequence

The initial canonical validation sequence is:

- 1. compile the complete Dataform graph;
- 2. inspect the compiled action inventory;
- 3. dry-run canonical relations and controls;
- 4. execute required upstream staging relations when necessary;
- 5. execute canonical preparation relations;
- 6. execute canonical dimensions;
- 7. execute canonical facts;
- 8. execute `bridge_order_reviews`;
- 9. execute all blocking canonical assertions;
- 10. execute non-blocking canonical quality views;
- 11. validate relation schemas and descriptions;
- 12. reconcile canonical row counts with governed staging inputs;
- 13. verify canonical referential integrity;
- 14. verify monetary reconciliation behavior;
- 15. verify join-amplification safeguards;
- 16. compare anomaly outputs with approved baselines;
- 17. record validation evidence;
- 18. approve or reject the canonical graph publication.

A successful dry run confirms query validity but does not replace execution and data validation.

A successful table build does not replace assertion execution.

## 16. Validation Evidence

The completion record for the initial implementation must include:

- Dataform compilation result;
- dry-run result;
- execution result;
- created canonical relation inventory;
- blocking assertion results;
- canonical row counts;
- primary-key uniqueness results;
- required-reference results;
- source-to-canonical reconciliation results;
- monetary reconciliation distribution;
- anomaly counts compared with approved baselines;
- confirmation that controlled joins preserve their intended grains;
- Terraform confirmation that the canonical dataset and IAM match configuration;
- Git commit references for implementation and documentation.

Validation evidence may be summarized in the implementation documentation without reproducing full command output or warehouse job metadata unnecessarily.

## 17. Failure and Recovery Behavior

When a blocking control fails:

- the affected relation is rejected;
- dependent publication must not be approved;
- the failing evidence must be preserved;
- the cause must be investigated;
- the relation must be rebuilt and revalidated after correction.

When a non-blocking condition exceeds its approved baseline:

- the canonical relation remains governed by its registered disposition;
- affected usage restrictions remain in force;
- engineering review is required;
- the new result must not silently replace the approved baseline.

When a required control fails to execute:

- the publication state is `unknown`;
- the absence of results must not be interpreted as zero anomalies;
- the control must be restored and rerun before approval.

A recovery is complete only when the failed or unknown controls execute successfully and the relation again satisfies its publication gates.

## 18. Initial Completion Criteria

The Olist canonical model is ready for downstream data-product development when:

- every planned canonical dimension is implemented;
- every planned canonical fact is implemented;
- `bridge_order_reviews` is implemented;
- every relation conforms to its documented grain;
- deterministic canonical keys are implemented consistently;
- blocking canonical controls pass;
- required references are valid;
- approved nullable-reference behavior is enforced;
- source-to-canonical row counts reconcile;
- review entities and associations reconcile independently;
- monetary measures reconcile according to the governed rules;
- join-amplification safeguards pass;
- known anomalies receive their approved canonical treatments;
- non-blocking quality outputs execute successfully;
- the complete Dataform graph compiles, dry-runs, and executes successfully;
- validation evidence is recorded;
- the ROADMAP and README reflect the resulting implementation state.

Completion of this contract authorizes implementation of reusable data products above the canonical layer. It does not complete the future production work required for historical quality results, automated baseline evaluation, alert delivery, scheduling, or operational promotion workflows.