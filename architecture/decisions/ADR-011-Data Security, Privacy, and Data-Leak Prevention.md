# ADR-011 — Data Security, Privacy, and Data-Leak Prevention

## Status

Accepted

## Date

2026-08-18

---

## Context

Mercury processes data that may contain customer, transactional, behavioral, and other potentially sensitive information.

As Mercury evolves from ingestion and warehouse loading toward replay, recovery, orchestration, observability, and production deployment, the number of code paths interacting with data increases.

This creates security risks that must be addressed explicitly rather than relying on individual components to behave securely by convention.

Examples include:

- customer data accidentally appearing in application logs;
- raw record values being persisted in exception messages;
- personally identifiable information (PII) entering replay-state metadata;
- credentials or secrets being committed to source control;
- overly broad service-account permissions;
- accidental public access to Raw storage;
- unnecessary local copies of customer data;
- recovery workflows exposing or duplicating sensitive artifacts;
- debugging output printing source records;
- test fixtures containing real customer data;
- operational metadata becoming an unintended secondary data store.

Mercury therefore requires a platform-wide security contract.

Security and privacy are cross-cutting architectural requirements and apply to all existing and future ADRs.

Where an earlier implementation conflicts with ADR-011, the implementation should be hardened without rewriting historical architectural decisions.

---

## Decision

Mercury will follow a secure-by-default architecture based on the following principles:

```text
least privilege
      +
data minimization
      +
private-by-default storage
      +
PII-safe observability
      +
secret isolation
      +
controlled data movement
      +
auditable operations
      ↓
secure data platform
```

Security controls must apply consistently across:

- ingestion;
- storage;
- warehouse loading;
- replay;
- recovery;
- orchestration;
- metadata;
- logging;
- testing;
- infrastructure;
- future downstream processing.

## 1. Data Classification

Mercury must distinguish between:

    DATA PLANE
    customer / source data

CONTROL PLANE
technical operational metadata

### Data Plane: 

Examples include:

- orders;
- payments;
- reviews;
- customer identifiers;
- behavioral records;
- transactional records;
- source CSV contents;
- future CRM or advertising data.

Data-plane information may contain sensitive or personally identifiable information.

### Control Plane

Examples include:

- run_id;
- event_id;
- delivery_date;
- source_object;
- replay stage;
- replay status;
- timestamps;
- technical destination identifiers;
- sanitized technical failure information.

The control plane must not become a secondary repository for customer data.

## 2. Data Minimization

Mercury must process, copy, persist, and expose only the data required for the operation being performed.

Components must not retain additional customer data merely because it is convenient for debugging or orchestration.

In particular:

    operational metadata
            ≠
    source data

Replay and recovery state must describe what happened to data without containing the data itself.

## 3. No Customer Data in Operational State

Operational state must never intentionally persist raw customer record values.

ReplayStateRecord and future orchestration metadata may contain technical facts such as:

    run_id
    event_id
    delivery_date
    source_object
    stage
    status
    timestamps
    sanitized error information

They must not contain values such as:

    customer names
    email addresses
    phone numbers
    postal addresses
    payment details
    review text
    raw CSV rows
    customer IDs unless explicitly required as technical identifiers
    arbitrary source payloads

The replay-state table is a control-plane dataset, not a debugging dump.

## 4. PII-Safe Error Handling

Raw exception strings must not automatically be assumed safe for persistent operational metadata.

A future connector, parser, API client, or warehouse component could raise an exception containing source values.

For example:

    invalid email john@example.com at row {...}

Persisting:

    str(exc)

without considering its contents could leak customer information into:

- replay-state tables;
- application logs;
- monitoring systems;
- CI output;
- alerting systems.

Mercury will therefore establish a sanitized operational-error boundary.

Persisted operational errors should describe:

    component
    operation
    source_object
    stage
    technical error category
    safe technical context

without including raw customer payloads.

Original exceptions may remain available transiently to the executing process where required for debugging, but customer data must not be deliberately copied into durable operational metadata.

Security-sensitive sanitization must fail conservatively.

## 5. Logging Policy

Mercury logs must be PII-safe by default.

Application code must not log:

- complete source records;
- raw CSV lines;
- dataframe contents containing customer data;
- API response bodies containing customer data;
- arbitrary request/response payloads;
- customer email addresses;
- phone numbers;
- postal addresses;
- payment information;
- credentials;
- access tokens;
- secrets.

Logging should prefer technical metadata such as:

    source_object=payments
    delivery_date=2017-05-19
    stage=warehouse
    status=failed
    rows=168
    run_id=<uuid>

Logging may include non-identifying technical aggregates such as record counts where doing so does not reveal sensitive information about very small or restricted populations.

rather than source contents.

Debug logging does not create an exception to this rule.

## 6. Secrets and Credentials

Mercury must never hard-code credentials or secrets.

The following must never be committed to source control:

- service-account private keys;
- API keys;
- access tokens;
- refresh tokens;
- database passwords;
- webhook secrets;
- OAuth client secrets;
- private encryption keys;
- production credentials.

Local and production authentication should use credential mechanisms appropriate to the environment.

For Google Cloud workloads, Mercury should prefer workload identity / attached service-account credentials rather than long-lived service-account key files.

Where application secrets are required, they should be stored in an approved secret-management system such as Google Secret Manager.

Secrets must never appear in:

- source code;
- Git history;
- replay state;
- logs;
- exception messages;
- test snapshots.

## 7. Least-Privilege IAM

Every Mercury runtime identity must receive only the permissions required for its responsibility.

Mercury must avoid broad project-level roles such as:

    Owner
    Editor

for application workloads.

Where practical, separate runtime responsibilities should use appropriately scoped identities and permissions.

Examples may include:

    ingestion runtime
    recovery runtime
    transformation runtime
    deployment identity
    human developer access

A compromised runtime identity should not automatically provide unrestricted access to the entire Mercury environment.

Mercury separates infrastructure provisioning from application execution. Human or deployment identities provision and administer cloud resources, while mercury-runtime receives only the permissions required for normal ingestion and orchestration. The runtime may create immutable Raw artifacts, execute BigQuery jobs, and operate within explicitly approved datasets, but it cannot delete Raw objects, create arbitrary datasets, or administer IAM.

                HUMAN / INFRASTRUCTURE
                         │
              provision infrastructure
                         │
             ┌───────────┴───────────┐
             ▼                       ▼
           GCS Raw               BigQuery
                                 raw / metadata
             │                       │
             └───────────┬───────────┘
                         ▼
                 mercury-runtime
                         │
              ONLY runtime operations
                         │
        ┌────────────────┼────────────────┐
        ▼                ▼                ▼
   create Raw       execute BQ       write approved
    artifacts          jobs             datasets

      ✕                ✕                ✕
    delete         create datasets   administer IAM

IAM design should be reviewed whenever a new component requires additional cloud capabilities.

## 8. Service-Account Security

Service accounts are workload identities and must be treated as security-sensitive resources.

Mercury should:

- avoid long-lived service-account keys where possible;
- use attached workload identities in Google Cloud;
- scope service-account permissions narrowly;
- avoid unnecessary impersonation privileges;
- avoid sharing highly privileged service accounts between unrelated workloads;
- periodically review unused permissions and identities.

Application code must not assume broad cloud permissions are available.

## 9. Private Raw Storage

Mercury Raw storage contains potentially sensitive source data and must be private by default.

Cloud Storage buckets containing Mercury data must not intentionally permit public access.

Production infrastructure should enforce:

    Public Access Prevention

where Raw data must never be public.

Mercury should also use:

    Uniform Bucket-Level Access

so Cloud IAM remains the authoritative access-control mechanism rather than mixing IAM with per-object ACLs.

Raw objects must not be made public for debugging, sharing, or recovery.

## 10. No Public or Signed URLs for Internal Data Movement

Internal Mercury pipeline operations should use authenticated cloud-resource references such as:

    gs://bucket/object

rather than publicly accessible URLs.

Recovery must not generate public URLs for Raw artifacts.

Signed URLs should not be introduced into internal pipeline execution unless a future ADR establishes a specific justified requirement and associated controls.

## 11. Controlled Data Movement

Mercury should minimize unnecessary movement and duplication of customer data.

Where cloud services can communicate using authenticated resource references, Mercury should prefer that approach.

For example:

    GCS Raw
    ↓
    gs:// reference
    ↓
    BigQuery load

is preferable to:

    GCS
    ↓
    download customer file
    ↓
    local recovery process
    ↓
    upload again
    ↓
    BigQuery

Recovery operations must reuse existing validated immutable artifacts without downloading them unless downloading is explicitly required by a future capability.

## 12. Local Development Data

Real production customer data should not be required for normal local development or automated testing.

Mercury should prefer:

- simulators;
- synthetic data;
- generated fixtures;
- deliberately anonymized test data.

The existing Olist simulation approach is consistent with this principle.

Production customer extracts must not be committed to the repository.

.gitignore and repository practices must prevent accidental commits of:

- generated Raw files;
- local secrets;
- credential files;
- environment files containing secrets;
- production exports.

## 13. Test Security

Security behavior must be tested rather than documented only.

Mercury should maintain regression tests for security-sensitive invariants where practical.

Examples include:

- secrets are not required in source code;
- operational error metadata does not expose supplied sensitive values;
- recovery does not download Raw artifacts for LOAD_ONLY;
- control-plane records do not contain source payloads;
- storage behavior does not introduce public ACLs;
- recovery does not weaken immutable storage semantics.

Security tests should use synthetic sentinel values rather than real customer information.

For example:

    sensitive-test-email@example.invalid

can be deliberately injected into a failing synthetic operation and tests can assert that it never appears in persisted operational metadata.

## 14. Recovery Security

ADR-010 Phase 3 recovery must comply with ADR-011.

    SKIP

Must perform no data-plane operation.

    INGEST_AND_LOAD

Must reuse the normal secure ingestion path.

Recovery must not introduce a second, less-controlled ingestion mechanism.

    LOAD_ONLY

Must reuse the validated immutable GCS artifact through its authenticated gs:// reference.

It must not:

- download the Raw artifact;
- print its contents;
- create a public URL;
- create a signed URL;
- duplicate the object unnecessarily.

    RECONCILE

Physical-state inspection must minimize access to source contents.

Where metadata is sufficient to establish physical state, Mercury should not read customer payloads.

    MANUAL_REVIEW

Manual review does not grant permission to expose customer data.

Diagnostic information surfaced to operators must remain PII-safe.

## 15. Security of Recovery Metadata

Future recovery execution may persist:

    run_id
    event_id
    delivery_date
    source_object
    stage
    status
    technical destination
    sanitized error information

It must not persist source records or customer payloads merely to explain recovery decisions.

RecoveryPlan, recovery execution results, and future reconciliation records remain control-plane objects.

## 16. BigQuery Security

Raw BigQuery datasets must be treated as sensitive data stores.

Access should follow least privilege.

Application workloads should receive only the dataset/table permissions required by their responsibility.

Human access to Raw data should not automatically follow from access to Mercury source code or deployment tooling.

As Mercury develops curated and consumption layers, additional controls may include:

- authorized views;
- column-level access controls;
- policy tags;
- data masking;
- separate datasets by security boundary.

Those controls should be introduced where the sensitivity and consumption model require them.

## 17. Encryption

Mercury relies on cloud-provider encryption at rest and authenticated encrypted transport as the baseline.

If regulatory, contractual, or client requirements later require customer-managed encryption keys or additional cryptographic controls, those requirements should be addressed explicitly through infrastructure design and, where appropriate, a dedicated ADR.

Application code must not invent custom encryption schemes for customer data.

## 18. Data Retention and Deletion

Security includes limiting how long sensitive data exists.

Mercury infrastructure should eventually define explicit retention policies for:

- Raw GCS data;
- BigQuery Raw data;
- operational replay metadata;
- temporary/generated files;
- logs.

Retention requirements may vary by client and data category.

ADR-011 establishes the requirement for explicit retention but does not define universal retention periods.

Client-specific legal or contractual requirements take precedence.

## 19. Repository Security

The Mercury Git repository must contain:

    code
    tests
    synthetic fixtures
    documentation
    infrastructure definitions

and must not contain:

    production customer data
    credentials
    private keys
    access tokens
    production secrets
    sensitive exports

Repository history must be treated as effectively persistent.

Removing a secret in a later commit is not considered sufficient remediation if the secret was previously committed.

## 20. Dependency Security

Third-party dependencies expand Mercury's security boundary.

Mercury should:

- keep dependencies minimal;
- prefer established libraries;
- pin or constrain dependencies appropriately;
- review dependency updates;
- avoid adding packages for functionality already available safely in the standard library or existing dependencies;
- introduce automated dependency vulnerability scanning when CI/CD security controls are established.

## 21. Secure Defaults Over Developer Convenience

When security and convenience conflict, Mercury should default to the safer behavior.

Examples:

    do not print payload
    instead of
    print payload for debugging

    deny unexpected access
    instead of
    grant broad permissions temporarily

    fail recovery clearly
    instead of
    bypass validation

    use authenticated resource references
    instead of
    generate externally accessible URLs

Security controls should not silently disappear in development mode.

## 22. Failure Behavior

Security-sensitive failures should fail closed.

Examples include:

- inability to establish artifact validity;
- unexpected credential state;
- inability to persist trustworthy control-plane state;
- inconsistent recovery evidence;
- unsafe reconciliation state.

Mercury must not bypass a security or integrity control merely to allow a pipeline to continue.

## 23. Auditability

Security-relevant operations should remain attributable through technical metadata without exposing customer data.

Mercury's existing:

    run_id
    event_id
    delivery_date
    source_object
    stage
    status
    timestamps

provide the foundation for operational auditability.

Future observability should build on these technical identifiers rather than copying source payloads into logs.

## 24. Existing-Code Security Review

Adoption of ADR-011 requires a targeted review of the existing Mercury implementation.

The review must inspect at minimum:

    BaseConnector
    ConnectorRunMetadata
    IngestionRunner
    GCSStorageManager
    BigQueryRawLoader
    ReplayStateRecord
    ReplayStateStore
    BigQueryReplayStateStore
    HistoricalReplayRunner
    RecoveryPlanner

The purpose is not to redesign these components.

The review should identify only concrete violations or weaknesses relative to ADR-011.

Compliant behavior should remain unchanged.

Particular attention must be paid to:

    exception
        ↓
    str(exc)
        ↓
    metadata / replay state / logs

because arbitrary exception text may contain source data.

## 25. Implementation Sequence

ADR-011 will be implemented incrementally.

### Phase 1 — Existing-Code Security Audit

Review the current implementation against ADR-011.

Classify findings as:

    COMPLIANT
    HARDEN
    INFRASTRUCTURE
    FUTURE

No speculative refactoring should be performed.

### Phase 2 — Application Hardening

Implement narrowly scoped fixes identified by the audit.

Likely areas include:

- PII-safe persistent error handling;
- control-plane metadata sanitization;
- repository protections;
- security regression tests.

All existing functional behavior should remain unchanged unless that behavior violates the security contract.

### Phase 3 — Infrastructure Security

When Mercury infrastructure is managed declaratively, enforce appropriate controls including:

- least-privilege service accounts;
- private Raw storage;
- Uniform Bucket-Level Access;
- Public Access Prevention;
- secret-management integration;
- appropriately scoped BigQuery permissions.

### Phase 4 — CI/CD Security Controls

Introduce automated controls such as:

- secret scanning;
- dependency vulnerability scanning;
- static security analysis where useful;
- infrastructure policy validation.

## 26. Relationship to Previous ADRs

ADR-011 is cross-cutting.

It does not invalidate the architectural decisions made in ADR-001 through ADR-010.

Instead:

    All existing and future Mercury components must satisfy the security and privacy constraints established by ADR-011.

Where an implementation detail from an earlier ADR violates ADR-011, the implementation should be hardened while preserving the original architectural intent wherever possible.

Historical ADRs should not be rewritten merely to make them appear as though ADR-011 existed when they were originally authored.

## 27. Relationship to ADR-010 Phase 3

ADR-010 Phase 3B must not proceed without applying the relevant ADR-011 requirements to its design.

In particular:

    RecoveryPlan
        ↓
    Recovery execution
        ↓
    authenticated existing components
        ↓
    minimum necessary data movement
        ↓
    PII-safe state and errors

Recovery execution must not become an alternative path around Mercury's security controls.

## Non Goals

ADR-011 does not attempt to define:

- client-specific legal retention periods;
- GDPR legal bases;
- consent-management policy;
- organization-wide incident-response procedures;
- enterprise SIEM architecture;
- regulatory certification;
- client-specific data-processing agreements;
- universal data-classification taxonomies;
- custom cryptographic protocols.

These may require separate governance, legal, infrastructure, or architectural decisions.

## Consequences

### Positive

Mercury gains an explicit security contract before recovery and production orchestration expand the number of data-access paths.

Security expectations become testable rather than implicit.

Operational metadata remains separated from customer data.

Recovery can be designed securely from the beginning rather than retrofitted later.

Infrastructure security requirements are documented before production deployment.

### Trade-offs

Some debugging techniques become intentionally less convenient because raw payloads cannot be freely printed or persisted.

Error handling requires deliberate sanitization.

Least-privilege IAM requires more configuration than broad project-level permissions.

Security regression tests and infrastructure controls add engineering work.

These costs are accepted because Mercury handles potentially sensitive customer data.

## Expected Outcome

Mercury should be able to process sensitive customer data while maintaining the following boundary:

    Customer Data
        │
        │ controlled authenticated processing
        ▼
    Private Data Plane
        │
        ├───────────────┐
        │               │
        ▼               ▼
    GCS Raw          BigQuery
        │
        │ technical facts only
        ▼
    Control Plane
        │
        ▼
    Replay / Recovery / Logs
        │
        └── NO CUSTOMER PAYLOADS

The security objective is not merely:

"do not intentionally leak data"

but:

> Design Mercury so that normal development, operation, debugging, replay, and recovery do not create unnecessary opportunities for sensitive data to escape its intended security boundary.