# ADR-011 Phase 1 — Existing-Code Security Audit

## Status

Complete

## Date 

2026-08-18

## Related Decision

ADR-011 — Data Security, Privacy, and Data-Leak Prevention

## Purpose

This document records the findings of ADR-011 Phase 1: the security audit of Mercury's existing implementation.

The audit was intentionally read-only.

Its purpose was to determine whether the existing Mercury implementation complies with the security contract established by ADR-011 before additional recovery execution capabilities are introduced under ADR-010 Phase 3B.

No application code, tests, documentation, infrastructure, or architectural behavior was changed as part of the audit.

The full test suite was executed after the audit:

```text
978 passed
0 failed
```

This matched the pre-audit baseline.

---

## Executive Summary

The audit found no evidence of an active or already-occurring customer-data leak.

In particular, no evidence was found of:

- customer/source data being emitted through production logging;
- customer/source payloads being intentionally stored in replay or recovery metadata;
- credentials or secrets being embedded in the current working tree;
- application code enabling public GCS access;
- application code generating signed or public URLs for Raw artifacts;
- BigQuery loading downloading or unnecessarily duplicating Raw artifacts;
- real customer data being used by Mercury's automated tests.

The audit did, however, identify one important structural security gap:

> Arbitrary exception text can currently cross from the data-processing path into durable control-plane metadata without a sanitization boundary.

This is not evidence that sensitive data has already leaked.

It means the current architecture does not structurally prevent a future exception containing source values from being persisted into operational metadata.

This must be hardened before ADR-010 Phase 3B recovery execution is implemented.

---

## Findings Summary

The audit produced 19 numbered findings.

The normalized classification is:

| Classification | Count |
| --- | ---: |
| COMPLIANT | 13 |
| HARDEN | 4 |
| INFRASTRUCTURE | 2 |
| FUTURE | 0 |
| **Total** | **19** |

The original audit also identified several future security requirements.

Those are recorded separately in this document rather than counted as numbered findings because they apply to capabilities that do not yet exist.

### Severity

No CRITICAL security issue was identified.

The actionable application findings consist of:

- two HIGH-severity findings;
- one MEDIUM-severity finding;
- one LOW-severity dependency-management finding.

The first three findings share the same underlying root cause: unconstrained exception text crossing into operational metadata.

---

# 1. Application Hardening Findings

## F-01 — Unsanitized Unexpected Exception Text Enters Replay State

**Classification:** HARDEN  
**Severity:** HIGH  
**Component:** `orchestration/replay.py`  
**Phase:** ADR-011 Phase 2

`HistoricalReplayRunner` currently converts unexpected ingestion and warehouse exceptions using:

```python
str(exc)
```

and supplies the resulting string directly to:

```python
ReplayStateRecord.failed(..., error_message=...)
```

The replay-state record is subsequently persisted to BigQuery.

There is currently no sanitization, allowlist, bounded error representation, or equivalent security boundary between the arbitrary exception and durable replay metadata.

### Risk

A future connector, parser, API client, Google Cloud operation, or other dependency could produce an exception containing a source value.

For example, an upstream exception could theoretically contain:

```text
invalid value jane@example.com at record 42
```

Without a security boundary, that text could enter the replay-state control plane.

### Current Exposure

No evidence was found that this has happened.

Existing Mercury connector exceptions reviewed during the audit contained technical, structural, or path-related information rather than source-record contents.

The finding therefore represents a latent structural weakness rather than a known data leak.

### Phase 2 Objective

Introduce a PII-safe operational-error boundary before arbitrary exception information is allowed into durable replay state.

---

## F-02 — Connector Failure Metadata Propagates Unsanitized Error Text Into Replay State

**Classification:** HARDEN  
**Severity:** HIGH  
**Component:** `orchestration/replay.py`  
**Phase:** ADR-011 Phase 2

Ordinary connector failures propagate:

```text
IngestionMetadata.error_message
        ↓
ReplayStateRecord.error_message
        ↓
BigQuery replay-state metadata
```

`IngestionMetadata.error_message` originates from arbitrary exception text captured by `BaseConnector.run()`.

The replay layer therefore inherits the same security weakness even when it does not call `str(exc)` directly.

### Risk

Sensitive source information appearing in an upstream connector exception could be propagated through multiple control-plane objects before becoming durable replay metadata.

### Current Exposure

No evidence of an actual leak was found.

### Phase 2 Objective

Ensure that error information entering replay state has already crossed a trusted sanitization boundary and cannot contain arbitrary source payload information.

---

## F-03 — BaseConnector Is the Origin of Unconstrained Exception Metadata

**Classification:** HARDEN  
**Severity:** MEDIUM  
**Component:** `connectors/base.py`  
**Phase:** ADR-011 Phase 2

`BaseConnector.run()` currently handles arbitrary connector exceptions using the equivalent of:

```python
metadata.mark_failed(str(exc))
```

This is the earliest point at which arbitrary exception text becomes part of an operational metadata object.

Current connector implementations do not appear to raise source-value-containing exceptions.

However, `BaseConnector` intentionally supports a broader connector lifecycle, and future API, parser, or non-CSV connectors could raise exceptions whose messages contain sensitive values.

### Root Cause Relationship

F-01, F-02, and F-03 are not independent architectural problems.

They are three manifestations of one root security issue:

```text
arbitrary exception
        ↓
str(exc)
        ↓
operational metadata
        ↓
durable control-plane state
```

ADR-011 Phase 2 should therefore solve this at the architectural boundary rather than independently patching individual call sites.

---

## F-17 — Dependency Constraints Are Lower-Bound Only

**Classification:** HARDEN  
**Severity:** LOW  
**Component:** `pyproject.toml`  
**Phase:** ADR-011 Phase 2 / opportunistic

Mercury currently declares:

```text
google-cloud-storage>=2.0
google-cloud-bigquery>=3.0
```

without upper bounds or a dependency lock mechanism.

This means a future environment installation could resolve to a major dependency version that has not been explicitly validated against Mercury.

### Security Impact

This is primarily dependency and supply-chain hygiene.

It is not a direct customer-data leakage path and no current security incident is associated with it.

### Priority

This finding is non-blocking for ADR-010 Phase 3B.

It may be addressed opportunistically as part of ADR-011 hardening or later dependency/CI security work.

---

# 2. Security-Positive Existing Design

Thirteen findings confirmed existing Mercury behavior as compliant with ADR-011.

## Technical Metadata Separation

`IngestionMetadata` consists of technical operational fields rather than source-row values.

`ReplayStateRecord` similarly consists of technical state information, with the exception of the unconstrained content permitted by its `error_message` field, which is addressed by F-01 through F-03.

`SourceDelivery` contains technical delivery information and filesystem references rather than source payloads.

---

## Private GCS Application Behavior

`GCSStorageManager`:

- uses Application Default Credentials;
- does not embed credentials;
- does not create object ACLs;
- does not generate signed URLs;
- does not generate public URLs;
- uses immutable create-only writes;
- does not read file contents into application strings during upload.

Create-only GCS behavior is enforced through generation preconditions rather than check-then-write behavior.

---

## Controlled BigQuery Data Movement

`BigQueryRawLoader` loads Raw data directly from authenticated:

```text
gs://
```

references.

It does not:

- download Raw artifacts;
- read source files into the loader process;
- print artifact contents;
- create unnecessary copies as part of warehouse loading.

This existing behavior is directly aligned with ADR-011's controlled-data-movement principle and should be preserved by recovery execution.

---

## Replay-State Integrity

`BigQueryReplayStateStore` remains append-only.

Existing replay-state rows are not mutated or deleted by the state-store implementation.

Variable query values such as delivery dates and source objects use BigQuery query parameters.

State persistence fails closed: insertion errors raise rather than being silently ignored.

---

## Recovery Planning Boundary

`orchestration/recovery.py` remains a pure planning/domain layer.

It contains:

- no cloud calls;
- no storage operations;
- no connector execution;
- no source payload access;
- no arbitrary exception-derived reason strings.

Recovery evidence and plans contain technical identifiers, enums, booleans, and existing replay-state context rather than customer payloads.

This boundary must be preserved when ADR-010 Phase 3B introduces recovery execution.

---

## Logging

No `print()` or logging calls were found in the production Mercury package during the audit.

Therefore, no current production logging-based data-leak path was identified.

This does not remove the ADR-011 requirement that future observability remain PII-safe.

---

## Development and Test Data

Existing development and automated-test behavior uses synthetic, public Olist-derived, or hand-constructed fixture data.

No requirement for real production customer data was identified in the automated test suite.

---

# 3. Infrastructure Findings

Two numbered findings identify security controls that cannot be established solely through the current Python application.

These are not current application-code violations.

They require infrastructure/deployment validation.

## F-18 — GCS Infrastructure Security

**Classification:** INFRASTRUCTURE  
**Severity:** HIGH  
**Phase:** ADR-011 Phase 3

The application does not enable public access.

However, application-code inspection cannot prove whether deployed Raw buckets enforce:

- Public Access Prevention;
- Uniform Bucket-Level Access.

These controls must be verified and ultimately managed through Mercury's infrastructure configuration.

---

## F-19 — IAM and Runtime Identity Security

**Classification:** INFRASTRUCTURE  
**Severity:** HIGH  
**Phase:** ADR-011 Phase 3

Application code correctly relies on Application Default Credentials and does not assume embedded credentials.

However, Python-code inspection cannot prove:

- least-privilege runtime IAM;
- absence of broad Owner/Editor grants;
- workload-identity configuration;
- service-account role scoping;
- BigQuery dataset/table IAM.

These must be validated against the deployed Google Cloud environment and ultimately managed through infrastructure configuration.

---

## Additional Infrastructure Controls

The audit also identified the following controls as belonging to the infrastructure boundary:

- BigQuery Raw dataset/table IAM;
- Secret Manager policy when secrets are introduced;
- encryption configuration and any future customer-managed-key requirements;
- runtime workload identity.

These do not represent additional numbered findings.

---

# 4. Future Security Requirements

The audit identified requirements that apply to functionality not yet implemented.

They are deliberately not counted as current security defects.

## ADR-010 Phase 3B — Recovery Execution

Recovery execution must preserve ADR-011's security boundary.

In particular:

```text
LOAD_ONLY
    ↓
validated gs:// artifact
    ↓
BigQueryRawLoader
```

must not introduce:

- Raw artifact downloads;
- signed URLs;
- public URLs;
- unnecessary artifact duplication;
- source payload logging;
- unsanitized operational errors.

---

## ADR-010 Phase 3C — Reconciliation

Physical-state reconciliation should inspect only the minimum information required to establish trustworthy state.

Artifact contents should not be read merely because they are available if metadata is sufficient.

---

## Production Logging and Observability

No logging infrastructure currently exists.

When introduced, it must comply with ADR-011's PII-safe logging contract from its first implementation.

---

## CI/CD Security

Future CI/CD security work should include appropriate:

- secret scanning;
- dependency vulnerability scanning;
- static security analysis where useful;
- infrastructure policy validation.

---

## Data Retention

ADR-011 establishes explicit retention as a future requirement for:

- GCS Raw;
- BigQuery Raw;
- replay metadata;
- temporary/generated files;
- logs.

Client-specific retention periods remain outside the scope of this audit.

---

# 5. Repository Security Caveat

No credentials, secrets, `.env` files, private keys, tokens, or production-data files were found in the working tree examined during the audit.

However, Git history itself was not directly available to the audit environment.

Therefore the audit establishes:

> No credential or production-data exposure was identified in the current working tree.

It does not establish:

> No secret has ever existed anywhere in repository history.

Repository-history secret scanning should be addressed through future CI/CD security controls.

---

# 6. Phase 2 Scope

The blocking security work before ADR-010 Phase 3B is intentionally narrow.

Phase 2 must address:

```text
F-01
F-02
F-03
```

as one coherent architectural problem:

```text
CURRENT

Exception
    ↓
str(exc)
    ↓
IngestionMetadata
    ↓
ReplayStateRecord
    ↓
BigQuery metadata


TARGET

Exception
    ↓
PII-safe operational-error boundary
    ↓
safe technical error representation
    ↓
IngestionMetadata / ReplayStateRecord
    ↓
BigQuery metadata
```

The implementation should not rely on attempting to recognize every possible form of PII after arbitrary exception text has already been accepted.

The preferred security principle is:

> Persist only information Mercury deliberately constructs and knows is safe.

F-17 may be addressed opportunistically but does not block ADR-010 Phase 3B.

---

# 7. Development Gate

ADR-010 Phase 3B recovery execution remains temporarily paused.

Development may resume after ADR-011 Phase 2 has established and tested the safe operational-error boundary required by F-01 through F-03.

The following infrastructure and future requirements do not block Phase 3B application development:

- F-17 dependency constraint improvement;
- F-18 infrastructure enforcement;
- F-19 infrastructure IAM verification;
- future CI/CD security tooling;
- future retention enforcement.

Phase 3B itself must nevertheless conform to ADR-011 from its initial implementation.

---

# 8. Audit Conclusion

ADR-011 Phase 1 found no evidence that Mercury is currently leaking customer/source data through its application architecture.

Several existing design choices already support a strong security boundary:

```text
ADC authentication
        +
immutable private-oriented GCS behavior
        +
direct gs:// → BigQuery loading
        +
technical-only replay state
        +
pure recovery planning
        +
append-only control-plane history
        +
synthetic/public development data
```

The primary application-security weakness is concentrated in one cross-cutting error-handling pattern:

```text
arbitrary exception text
        ↓
durable operational metadata
```

This weakness is structural rather than evidence of an existing incident.

ADR-011 Phase 2 will establish a safe operational-error boundary before Mercury adds recovery execution under ADR-010 Phase 3B.

---

## Phase 1 Completion

ADR-011 Phase 1 is complete.

Baseline before audit:

```text
978 passed
0 failed
```

Baseline after audit:

```text
978 passed
0 failed
```

No files were modified by the audit itself.

No application behavior changed.

No ADR-010 behavior changed.