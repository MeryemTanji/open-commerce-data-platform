# Mercury Production Platform Design

## Status

Draft

## Date

2026-10-21

## Purpose

This document defines the implementation design for operating Mercury as a scheduled, observable, and reproducible production platform.

It translates ADR-014 into deployable runtime, orchestration, configuration, identity, infrastructure, failure-handling, and validation boundaries.

## Governing Decisions

This design implements:

- [ADR-009: Decouple Source Delivery from Pipeline Orchestration](../decisions/ADR-009-Decouple%20Source%20Delivery%20from%20Pipeline%20Orchestration.md);
- [ADR-010: Persist Source-Level Historical Replay State and Derive Date-Level Completion](../decisions/ADR-010-Persist%20Source-Level%20Historical%20Replay%20State%20and%20Derive%20Date-Level%20Completion.md);
- [ADR-011: Data Security, Privacy, and Data-Leak Prevention](../decisions/ADR-011-Data%20Security,%20Privacy,%20and%20Data-Leak%20Prevention.md);
- [ADR-012: Staging Layer Standardization and Semantic Contracts](../decisions/ADR-012-Staging%20Layer%20Standardization%20and%20Semantic%20Contracts.md);
- [ADR-013: Data Quality Anomaly Disposition and Monitoring Contract](../decisions/ADR-013-Data%20Quality%20Anomaly%20Disposition%20and%20Monitoring%20Contract.md);
- [ADR-014: Orchestrate Production Execution with Cloud Workflows](../decisions/ADR-014-Orchestrate-Production-Execution-with-Cloud-Workflows.md).

---

## 1. Scope

This document defines:

- the production execution topology;
- supported execution modes;
- the production ingestion command;
- runtime configuration;
- logical delivery-date handling;
- Olist simulation-input boundaries;
- Cloud Run container behavior;
- workflow state transitions;
- Dataform invocation;
- workload identities;
- Terraform ownership;
- retry and failure behavior;
- operational traceability;
- production validation requirements.

This document does not define:

- connector-specific extraction logic;
- Raw table schemas;
- staging or canonical contracts;
- anomaly-specific dispositions;
- final notification channels;
- data-product schemas;
- production environment promotion beyond the current development project.

Those concerns remain governed by their existing contracts or later implementation designs.

---

## 2. Production Architecture

Mercury's production execution path is:

```text
Cloud Scheduler
      |
      v
Cloud Workflows
      |
      v
Cloud Run ingestion job
      |
      +----> GCS Raw
      |
      +----> BigQuery Raw
      |
      +----> BigQuery metadata
      |
      v
Date-completion validation
      |
      v
Dataform workflow invocation
      |
      +----> staging
      |
      +----> canonical
      |
      v
Quality evaluation and monitoring
```

The orchestration path coordinates services without combining their data permissions.

A successful scheduler invocation does not itself represent successful publication.

Production publication succeeds only when the required ingestion, completion, transformation, and blocking-quality stages succeed.

---

## 3. Execution Modes

Mercury supports separate execution modes.

| Mode | Purpose |
| --- | --- |
| Scheduled day | Process one approved logical delivery date |
| Manual day | Re-run one explicitly supplied delivery date |
| Historical replay | Process an explicit controlled date range |
| Targeted recovery | Execute stages justified by durable evidence |

The initial production workflow will support scheduled-day and manual-day execution.

Historical replay and targeted recovery remain operator-initiated until separate workflow contracts are implemented.

A scheduled execution must never silently expand into a historical range.

---

## 4. Production Ingestion Command

Mercury will expose a Python module entry point:

```text
python -m mercury_ingestion.cli run-day \
    --delivery-date YYYY-MM-DD
```

The command will:

1. parse the requested delivery date;
2. validate required runtime configuration;
3. prepare temporary source workspace where required;
4. construct the source provider;
5. construct GCS storage;
6. construct the BigQuery Raw loader;
7. construct replay-state and provenance stores;
8. call `HistoricalReplayRunner.run_day()`;
9. emit a PII-safe structured summary;
10. exit according to the terminal result.

The production adapter must remain thin.

It must not duplicate behavior owned by the existing ingestion framework.

### 4.1 Exit behavior

| Exit code | Meaning |
| ---: | --- |
| `0` | Requested delivery completed successfully |
| `1` | Requested delivery was incomplete or partially successful |
| `2` | Execution failed before a valid delivery result was produced |
| `64` | Runtime configuration or command input was invalid |

Only exit code 0 permits downstream transformation.

### 4.2 Output contract

The command should emit a final structured log containing:

- execution identifier;
- ingestion run_id;
- environment;
- logical delivery date;
- source count;
- completed source count;
- failed source count;
- final status;
- safe failure category where applicable.

It must not log:

- source records;
- credentials or tokens;
- complete customer identifiers;
- sensitive object contents;
- unrestricted exception payloads.

---

## 5. Runtime Configuration

Infrastructure identifiers must not remain hardcoded in the production entry point.

The initial configuration contract is:

| Variable | Responsibility |
| --- | --- |
| `MERCURY_ENVIRONMENT` | Identifies the runtime environment |
| `MERCURY_PROJECT_ID` | GCP project containing Mercury resources |
| `MERCURY_REGION` | Regional runtime location |
| `MERCURY_RAW_BUCKET` | Immutable Raw landing bucket |
| `MERCURY_RAW_DATASET` | BigQuery Raw dataset |
| `MERCURY_METADATA_DATASET` | BigQuery operational metadata dataset |
| `MERCURY_SOURCE_INPUT_URI` | Durable source or simulation-input location |
| `MERCURY_WORKFLOW_EXECUTION_ID` | Correlates the job with its workflow execution |

The delivery date remains a command argument because it identifies the unit of work rather than static infrastructure configuration.

Configuration validation must occur before source processing begins.

Missing, blank, malformed, or contradictory required values must fail the job clearly.

---

## 6. Logical Delivery Date

The workflow must resolve one logical delivery date before starting ingestion.

The request contract is conceptually:

```text
environment
execution_mode
delivery_date
workflow_execution_id
```

For manual execution, `delivery_date` must be supplied explicitly.

For scheduled execution, the workflow may derive the date through an approved source-specific rule or select it from durable replay state.

The Cloud Run Job must receive the resolved date and must not derive a different date independently.

The Olist provider remains responsible for its existing relationship between business delivery date and ingestion date.

---

## 7. Olist Simulation Input

Olist is a simulated source domain rather than a live operational source.

The production container must not rely on repository-relative data or embed mutable source deliveries inside the image.

The initial production simulation boundary will be:

```text
Durable simulation input
        |
        v
Temporary Cloud Run workspace
        |
        v
Olist source simulation
        |
        v
Existing ingestion framework
```

The ingestion identity receives read-only access to the approved simulation input.

Generated local files exist only for the duration of the job.

Durable platform evidence remains in:

- immutable GCS Raw objects;
- BigQuery Raw tables;
- replay-state history;
- artifact provenance;
- warehouse-load provenance.

A future real source provider may replace the Olist simulation provider without changing the production orchestration contract.

---

## 8. Cloud Run Job

The ingestion runtime will be packaged as a container and deployed as a Cloud Run Job.

The container will:

- install the Mercury ingestion package;
- expose the production module entry point;
- contain no credentials;
- contain no mutable environment-specific configuration;
- contain no durable execution state;
- use Application Default Credentials;
- write only temporary files to its local filesystem;
- terminate after completing its requested operation.

The image will be stored in Artifact Registry.

Production job revisions should reference an immutable image digest where practical.

The initial job will use one task. Source-level isolation remains handled by the ingestion framework rather than Cloud Run task parallelism.

---

## 9. Workflow Contract

The production workflow will execute these ordered stages:

```text
VALIDATE REQUEST
      |
      v
EXECUTE INGESTION JOB
      |
      v
CHECK JOB TERMINAL STATE
      |
      v
VALIDATE DURABLE DATE COMPLETION
      |
      v
INVOKE DATAFORM
      |
      v
CHECK DATAFORM TERMINAL STATE
      |
      v
RECORD FINAL RESULT
```

### 9.1 Ingestion gate

The workflow stops before Dataform when:

- the Cloud Run Job fails;
- the job times out;
- the job reports an incomplete delivery;
- durable completion evidence is absent;
- replay state is contradictory;
- the completion check fails.

### 9.2 Transformation gate

The Dataform invocation must execute the approved staging and canonical publication graph, including blocking assertions.

The workflow fails publication when:

- Dataform compilation fails;
- an action fails;
- a blocking assertion fails;
- the invocation times out;
- the terminal state is unknown.

Non-blocking observations do not fail publication when they execute successfully and report governed findings.

Failure to execute a required non-blocking observation is an unknown quality state and must be recorded accordingly.

---

## 10. Workload Identities

| Identity | Responsibility |
| --- | --- |
| Scheduler identity | Start the approved production workflow |
| Workflow identity | Invoke and inspect approved production services |
| Ingestion identity | Write Raw artifacts, load Raw tables, and update metadata |
| Dataform identity | Read Raw and manage staging and canonical relations |

No identity may receive broad Owner, Editor, BigQuery Admin, Storage Admin, or IAM administration roles.

### 10.1 Scheduler identity

May:

- start the approved workflow.

Must not:

- invoke arbitrary workflows;
- invoke the ingestion job directly;
- access business data.

### 10.2 Workflow identity

May:

- execute and inspect the approved Cloud Run Job;
- invoke and inspect the approved Dataform workflow;
- perform the minimum required completion check.

Must not:

- write Raw data;
- manage analytical relations;
- administer infrastructure.

### 10.3 Ingestion identity

May:

- read approved simulation inputs;
- create immutable Raw objects;
- load approved BigQuery Raw relations;
- write operational metadata;
- execute required BigQuery jobs.

Must not:

- manage staging or canonical relations;
- invoke Dataform;
- administer datasets or IAM.

### 10.4 Dataform identity

Retains the validated Phase 3 boundary:

- project-level BigQuery job execution;
- read-only BigQuery Raw access;
- staging relation management;
- canonical relation management;
- no GCS Raw access;
- no metadata access;
- no dataset or IAM administration.

---

## 11. Terraform Ownership

Terraform will manage infrastructure boundaries.

Application workloads will manage data within those boundaries.

| Resource | Owner |
| --- | --- |
| Service APIs | Terraform |
| Datasets and buckets | Terraform |
| Service accounts and IAM | Terraform |
| Artifact Registry | Terraform |
| Cloud Run Job | Terraform |
| Cloud Workflow | Terraform |
| Cloud Scheduler job | Terraform |
| Monitoring resources | Terraform |
| Raw objects | Ingestion runtime |
| BigQuery Raw relations | Ingestion framework |
| Operational metadata relations | Ingestion framework within the Terraform-managed dataset |
| Staging and canonical relations | Dataform |

Existing resources must be evaluated for import before Terraform attempts to create replacements.

Correctly configured data-bearing resources must not be destroyed merely to introduce Terraform ownership.

---

## 12. Retry and Failure Model

Retries must be conservative and compatible with Mercury's idempotency contracts.

Automatic retries are appropriate only where an operation is safe to repeat.

A retry must preserve:

- immutable Raw object behavior;
- deterministic object naming;
- append-only replay-state history;
- run-level identifiers;
- provenance for repeated attempts;
- source-level failure isolation.

The workflow must not retry indefinitely.

Ambiguous or contradictory states must route to reconciliation or manual review.

Transformation retries require confirmed complete Raw input and must not bypass failed assertions.

Exact retry counts and timeouts will be selected during resource implementation and validated against realistic execution duration.

---

## 13. Observability

Every production run must correlate:

- scheduler invocation;
- workflow execution;
- Cloud Run execution;
- ingestion `run_id`;
- logical delivery date;
- source-level replay state;
- Raw artifact provenance;
- warehouse-load provenance;
- Dataform invocation;
- quality evaluation;
- final workflow status.

Cloud Logging will receive structured operational events.

Cloud Monitoring will initially cover:

- workflow failure;
- Cloud Run Job failure;
- ingestion incompleteness;
- Dataform failure;
- unknown quality state;
- missing scheduled execution where detectable.

Historical quality evaluation, baseline comparison, and alert disposition remain governed by [ADR-013](../decisions/ADR-013-Data%20Quality%20Anomaly%20Disposition%20and%20Monitoring%20Contract.md).

---

## 14. Security Requirements

The production platform must:

- use keyless workload authentication;
- use separate workload identities;
- prevent public invocation;
- prevent public bucket access;
- prevent destructive Raw mutation;
- avoid credentials in container images;
- avoid secrets in environment-variable source files;
- redact unsafe exception details;
- preserve least-privilege dataset access;
- protect Terraform state and local credentials.

Security validation must include both permitted and prohibited operations for every new workload identity.

---

## 15. Validation Requirements

The production implementation is not complete until Mercury validates:

- production CLI input handling;
- environment configuration validation;
- container build and local execution;
- keyless Cloud Run authentication;
- permitted ingestion operations;
- prohibited ingestion operations;
- scheduler-to-workflow invocation;
- workflow-to-job invocation;
- ingestion failure propagation;
- durable completion gating;
- workflow-to-Dataform invocation;
- blocking assertion propagation;
- non-blocking observation execution;
- execution correlation;
- Terraform reproducibility;
- absence of unintended infrastructure changes;
- manual execution of one controlled delivery date;
- scheduled execution of one controlled delivery date.

Validation evidence must record the deployed resource versions and relevant execution identifiers without exposing credentials or sensitive data.

---

## 16. Implementation Sequence

The initial implementation order is:

1. implement the production CLI;
2. add configuration validation and tests;
3. define the Olist simulation-input boundary;
4. create the ingestion container;
5. validate the container locally;
6. bring required datasets and buckets under Terraform ownership;
7. provision Artifact Registry;
8. provision runtime identities and IAM;
9. deploy the Cloud Run Job;
10. configure managed Dataform invocation;
11. implement the Cloud Workflow;
12. add Cloud Scheduler;
13. implement operational monitoring;
14. validate the complete production path;
15. update infrastructure documentation and runbooks.

Each step should be committed and validated independently where practical.

---

## 17. Source-Specific Runtime Contracts

This document defines the platform-wide production architecture.

Source-specific runtime behavior must be documented separately when it introduces material rules such as:

- delivery availability timing;
- logical-date derivation;
- authentication requirements;
- extraction cursors;
- source-specific retry behavior;
- expected delivery membership;
- simulation mechanics.

Olist is the first implementation. Its simulation mechanics must not redefine Mercury's reusable production boundaries.

---

## Design Summary

Mercury's production platform separates triggering, orchestration, ingestion, transformation, and monitoring.

Cloud Scheduler starts the workflow.

Cloud Workflows coordinates the required dependency gates.

Cloud Run executes one finite ingestion unit.

Dataform publishes analytical relations only after durable ingestion completion.

Terraform owns the infrastructure boundary, while ingestion and Dataform manage data within their approved scopes.

The governing execution rule is:

> No transformation without complete ingestion. No success without a known quality state. No runtime without explicit ownership and traceability.