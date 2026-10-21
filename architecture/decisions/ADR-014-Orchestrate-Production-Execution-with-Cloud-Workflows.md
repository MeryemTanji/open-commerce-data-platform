# ADR-014: Orchestrate Production Execution with Cloud Workflows

## Status

Accepted

## Date

2026-10-21

## Context

Mercury has implemented and validated its ingestion, Raw-platform, staging, and canonical foundations.

The platform currently supports:

- reusable source connectors;
- immutable Raw storage;
- BigQuery Raw loading;
- durable replay state;
- targeted recovery;
- artifact and warehouse provenance;
- staging and canonical transformations;
- blocking assertions;
- non-blocking quality observations.

These capabilities have primarily been executed through locally initiated commands and manually triggered cloud operations.

Mercury now requires a production execution model that can:

- start ingestion on a schedule;
- process an explicit logical delivery date;
- wait for ingestion to reach a known terminal state;
- prevent transformation after incomplete ingestion;
- invoke Dataform only after required Raw data is complete;
- preserve separate ingestion and transformation identities;
- support manual replay and targeted recovery;
- expose execution failures through operational monitoring;
- provision runtime infrastructure reproducibly.

The existing `load_olist_history.py` script is a development and historical-bootstrap utility. It contains development-specific configuration, uses repository-relative source files, generates simulated deliveries, and coordinates historical ranges.

It must not become the scheduled production entry point.

The reusable ingestion framework beneath it already provides the required daily processing behavior through `HistoricalReplayRunner.run_day()`.

Mercury requires an orchestration boundary that coordinates this ingestion operation with downstream transformation without combining their implementation or permissions.

---

## Decision

Mercury will use:

- **Cloud Scheduler** for time-based triggers;
- **Cloud Workflows** for dependency orchestration;
- **Cloud Run Jobs** for finite ingestion workloads;
- **Dataform workflow invocations** for staging and canonical transformation;
- **Cloud Logging and Cloud Monitoring** for operational visibility;
- **Terraform** for runtime infrastructure and IAM.

The production execution path will be:

```text
CLOUD SCHEDULER
starts the production workflow

        |
        v

CLOUD WORKFLOWS
coordinates the execution

        |
        v

CLOUD RUN INGESTION JOB
processes one logical delivery date

        |
        v

INGESTION COMPLETION CHECK
requires durable completion evidence

        |
        v

DATAFORM WORKFLOW INVOCATION
publishes staging and canonical relations

        |
        v

QUALITY EVALUATION
records and classifies the outcome
```

Dataform MUST NOT execute merely because a fixed amount of time has passed since ingestion was scheduled.

Transformation may begin only after the workflow confirms that the required ingestion execution completed successfully.

---

## 1. Responsibility Boundaries

### ORCH-001 — Scheduling MUST remain separate from processing
Cloud Scheduler will initiate the production workflow.

It MUST NOT:
- execute ingestion logic;
- determine source completeness;
- transform business data;
- write Raw data;
- invoke Dataform independently of ingestion completion.

### ORCH-002 — Cloud Workflows MUST coordinate dependencies

Cloud Workflows will coordinate the approved execution sequence.

It MUST:

- validate required execution inputs;
- start the Cloud Run Job;
- wait for ingestion to reach a terminal state;
- stop downstream execution after failed or incomplete ingestion;
- invoke the approved Dataform workflow;
- wait for transformation to reach a terminal state;
- expose the final execution outcome.

It MUST NOT reproduce connector, replay-state, provenance, or transformation logic.

### ORCH-003 — Ingestion MUST execute as a finite job

Scheduled ingestion will execute as a Cloud Run Job rather than as a continuously running service.

The job will:

- process one explicitly requested delivery date;
- use the existing ingestion framework;
- preserve replay state and provenance;
- emit a non-zero exit status when the delivery is incomplete;
- terminate after processing.

Cloud Run local storage is temporary workspace and MUST NOT be treated as durable delivery state.

### ORCH-004 — Transformation MUST follow successful ingestion

The workflow will invoke Dataform only after the requested delivery is confirmed complete.

Transformation MUST NOT begin when:

- ingestion fails;
- ingestion is only partially successful;
- completion evidence is missing or contradictory;
- the completion check cannot execute;
- required Raw data is unavailable.

A failed or unknown Dataform state prevents the production workflow from reporting successful publication.

---

2. Production Entry Point
Mercury will introduce a thin production adapter around the existing ingestion framework.

Conceptually:

```text
python -m mercury_ingestion.cli run-day \
    --delivery-date YYYY-MM-DD
```

The adapter will: 

- validate its runtime configuration;
- accept an explicit logical delivery date;
- construct the required ingestion dependencies;
- call `HistoricalReplayRunner.run_day()`;
- emit a safe execution summary;
- return an appropriate process exit code.

It MUST NOT duplicate:

- connector mappings;
- source-delivery rules;
- storage behavior;
- Raw loading;
- replay-state transitions;
- provenance behavior;
- completion logic.

The existing historical-loading script will remain available for controlled bootstrap and replay operations.

---

## 3. Delivery-Date Semantics

Mercury distinguishes:

```text
workflow execution time
```

from:

```text
logical source delivery date
```

These values may differ.

The Cloud Run Job MUST NOT silently assume that the current system date is the correct business date.

The delivery date may be:

- provided explicitly by an operator;
- derived through an approved source schedule;
- selected using durable replay state;
- supplied by an approved source-delivery event.

The derivation rule must remain deterministic and source-aware.

Olist-specific simulation timing remains owned by `OlistSimulatedSourceProvider`. Future source providers may implement different availability rules without changing the platform orchestration model.

---

## 4. Identity Separation

Production components will use separate least-privilege identities.

| Identity | Responsibility |
| --- | --- |
| Scheduler identity | Start the approved production workflow |
| Workflow identity | Coordinate approved service executions |
| Ingestion identity | Write Raw artifacts, load BigQuery Raw, and update operational metadata |
| Dataform identity | Read Raw and manage staging and canonical relations |

The workflow identity may invoke the Cloud Run Job and Dataform workflow but MUST NOT inherit their underlying data permissions.

The ingestion identity MUST NOT manage staging or canonical relations.

The Dataform identity MUST NOT modify Raw data, access Raw object storage, update ingestion metadata, or administer datasets.

No runtime identity may administer IAM.

---

## 5. Infrastructure Ownership

Production runtime infrastructure will be managed through Terraform.

This includes, where applicable:

- enabled service APIs;
- runtime service accounts;
- Artifact Registry;
- Cloud Run Jobs;
- Cloud Workflows;
- Cloud Scheduler;
- service-to-service IAM;
- runtime configuration;
- monitoring resources.

Runtime application code MUST NOT create:

- datasets;
- buckets;
- service accounts;
- IAM policies;
- schedules;
- workflows;
- Cloud Run resources.

The detailed ownership of operational tables and other runtime resources will be defined in the production-platform design.

---

## 6. Retry and Recovery Principles

Retries must preserve Mercury's existing reliability contracts.

Repeated execution of the same logical delivery date MUST NOT:

- overwrite immutable Raw artifacts;
- remove previous replay-state evidence;
- fabricate completion;
- skip required validation;
- trigger transformation after failed ingestion.

Scheduled execution, historical replay, and targeted recovery remain separate operational paths:

```text
SCHEDULED EXECUTION
processes one approved logical delivery date

HISTORICAL REPLAY
processes an explicitly requested date or range

TARGETED RECOVERY
executes only stages justified by durable evidence
```

The scheduled path MUST NOT silently expand into an unbounded historical replay.

Ambiguous states must continue to route to reconciliation or manual review.

---

## 7. Operational Traceability

Production execution must preserve correlation between:

- scheduler invocation;
- workflow execution;
- Cloud Run Job execution;
- ingestion run_id;
- logical delivery date;
- replay-state records;
- Raw artifact provenance;
- warehouse-load provenance;
- Dataform invocation;
- quality evaluation;
- final workflow result.

Operational logs must comply with [ADR-011](ADR-011-Data%20Security,%20Privacy,%20and%20Data-Leak%20Prevention.md) and MUST NOT contain credentials, access tokens, unnecessary personal data, or Raw record contents.

Quality-result persistence and alert evaluation remain governed by [ADR-013](ADR-013-Data%20Quality%20Anomaly%20Disposition%20and%20Monitoring%20Contract.md).

---

## ## Relationship to Existing Decisions

[ADR-009](./ADR-009-Decouple%20Source%20Delivery%20from%20Pipeline%20Orchestration.md) separates source delivery from pipeline orchestration.

[ADR-010](ADR-010-Persist%20Source-Level%20Historical%20Replay%20State%20and%20Derive%20Date-Level%20Completion.md) establishes durable replay state, completion, recovery, and provenance.

[ADR-011](ADR-011-Data%20Security,%20Privacy,%20and%20Data-Leak%20Prevention.md) establishes security and data-leak-prevention requirements.

[ADR-012](ADR-012-Staging%20Layer%20Standardization%20and%20Semantic%20Contracts.md) defines the staging and semantic transformation boundary.

[ADR-013](ADR-013-Data%20Quality%20Anomaly%20Disposition%20and%20Monitoring%20Contract.md) defines quality disposition, historical evaluation, and alerting requirements.

This ADR operationalises those decisions through a production execution architecture. It does not replace their source, recovery, security, transformation, or quality contracts.

---

## Consequences

### Positive

- Ingestion and transformation execute in an explicit dependency order.
- Dataform cannot publish after incomplete ingestion.
- Finite ingestion workloads use an appropriate serverless runtime.
- Scheduling remains separate from business processing.
- Runtime identities retain narrow responsibilities.
- Scheduled execution, replay, and recovery remain distinct.
- Failures remain traceable across service boundaries.
- Runtime infrastructure can be reproduced through Terraform.
- Future source providers can reuse the same orchestration model.

### rade-offs

- Cloud Workflows introduces an additional managed service.
- Multiple service identities and IAM bindings must be maintained.
- Dataform requires a managed production invocation mechanism.
- Cross-service failure paths require explicit testing.
- The Olist simulation requires a durable production-input strategy.
- Terraform scope expands beyond analytical datasets and IAM.

These costs are accepted because independent schedules or a single over-privileged runtime would weaken dependency control, security separation, and operational traceability.

---

## Alternatives Considered

### 1. Schedule ingestion and Dataform independently
Rejected.

A time delay cannot prove that ingestion completed successfully. Dataform could publish incomplete data after slow, failed, or partial ingestion.

### 2. Run ingestion and Dataform in one Cloud Run container
Rejected.

This would combine Python ingestion, Dataform execution, dependencies, credentials, and permissions inside one runtime boundary.

### 3. Trigger only the Cloud Run Job from Cloud Scheduler
Rejected as the complete orchestration model.

Direct scheduling does not coordinate dependent transformation, quality evaluation, or final workflow status.

### 4. Use Cloud Composer
Rejected for the current scope.

Composer introduces more operational complexity and cost than Mercury's current sequential serverless workflow requires.

This decision may be revisited if future orchestration requires substantially more complex dynamic workflows.

### 5. Use only Dataform schedules
Rejected.

Dataform scheduling cannot execute Mercury's Python ingestion framework or validate ingestion completion before transformation.

### 6. Deploy the historical-loading script unchanged
Rejected.

The script contains development-specific configuration, local file dependencies, source generation, and historical-range behavior.

---

## Implementation Boundary

This ADR records the durable service and responsibility decisions.

The production-platform design will define:

- the workflow sequence and state transitions;
- production CLI configuration;
- logical delivery-date resolution;
- Olist simulation storage;
- Dataform repository and invocation configuration;
- Terraform resources and module structure;
- service-account names and IAM bindings;
- retry and timeout values;
- logging and monitoring behavior;
- production validation evidence.

---


## Decision Summary

Mercury will use Cloud Scheduler to initiate production execution, Cloud Workflows to coordinate dependencies, Cloud Run Jobs to execute ingestion, and Dataform workflow invocations to publish staging and canonical relations.

The governing principle is:

> Schedule centrally. Execute separately. Transform only after complete ingestion. Preserve evidence across every stage.

Scheduled execution, historical replay, and targeted recovery remain explicit and independently controlled.

A production execution succeeds only when every required ingestion, transformation, and quality stage reaches a known and valid terminal state.