# ADR-011 Phase 3 — Infrastructure Security and Least-Privilege Runtime Validation

**Status:** Complete  
**ADR:** ADR-011 — Data Security, Privacy, and Data-Leak Prevention  
**Phase:** 3 — Infrastructure Security and Runtime IAM Hardening  
**Environment:** `mercury-data-platform-dev`  
**Region:** `europe-west4`

---

## 1. Purpose

Phase 3 of ADR-011 validates and hardens the cloud infrastructure security boundary used by Mercury.

The primary objectives of this phase were to:

1. inspect the existing Google Cloud Storage and BigQuery security configuration;
2. introduce a dedicated Mercury runtime identity;
3. apply least-privilege IAM permissions to that identity;
4. separate infrastructure provisioning privileges from application runtime privileges;
5. remove unnecessarily broad BigQuery dataset access inherited through project special groups;
6. validate the resulting security boundary through positive and negative runtime tests;
7. confirm that Mercury can perform its legitimate ingestion and orchestration operations without broad administrative permissions;
8. avoid long-lived service-account credentials.

The guiding principle for this phase was:

> Mercury runtime permissions must be derived from demonstrated application requirements, not from broad convenience roles.

The runtime should be capable of performing Mercury's normal data-plane and orchestration work while being unable to perform infrastructure administration.

---

## 2. Scope

Phase 3 covered the following infrastructure components:

- Google Cloud Storage Raw bucket;
- BigQuery `raw` dataset;
- BigQuery `metadata` dataset;
- project-level BigQuery job execution;
- Mercury runtime identity;
- service-account impersonation for security validation;
- BigQuery replay-state resource behavior.

The following were explicitly outside the scope of this phase:

- production deployment configuration;
- CI/CD identities;
- infrastructure-as-code implementation;
- Secret Manager configuration;
- automated IAM provisioning;
- customer-specific production IAM;
- encryption-key redesign;
- service-account key generation.

No service-account key was created during this phase.

---

## 3. Environment Audited

The Phase 3 validation was performed against the Mercury development project:

```text
mercury-data-platform-dev
```

Primary region:

```text
europe-west4
```

The relevant infrastructure consisted of:

```text
Google Cloud Storage
└── mercury-data-platform-dev-raw-01

BigQuery
├── raw
└── metadata
```

The `metadata` dataset contains Mercury's historical replay state table:

```text
metadata.historical_replay_state
```

The `raw` dataset contains the source-specific Raw ingestion tables.

---

## 4. Initial GCS Security State

The Raw bucket inspected during Phase 3 was:

```text
gs://mercury-data-platform-dev-raw-01
```

The bucket configuration confirmed:

```text
Location:
europe-west4

Storage class:
STANDARD

Uniform Bucket-Level Access:
enabled

Public Access Prevention:
enforced

Soft-delete retention:
604800 seconds / 7 days

Customer-supplied encryption keys:
fully restricted
```

These settings establish useful baseline protections.

In particular:

- public access is explicitly prevented;
- object access is governed through bucket-level IAM rather than per-object ACLs;
- deleted objects have a seven-day soft-delete recovery window.

No public access finding was identified for the Raw bucket.

---

## 5. Initial GCS IAM State

Before introducing the dedicated runtime identity, the bucket IAM policy contained legacy project-level bindings derived from project roles.

The initial policy included:

```text
projectEditor → roles/storage.legacyBucketOwner
projectOwner  → roles/storage.legacyBucketOwner

projectViewer → roles/storage.legacyBucketReader

projectEditor → roles/storage.legacyObjectOwner
projectOwner  → roles/storage.legacyObjectOwner

projectViewer → roles/storage.legacyObjectReader
```

No dedicated Mercury runtime service account existed at the beginning of Phase 3.

This meant Mercury development execution relied on developer credentials rather than an explicitly bounded workload identity.

---

## 6. Initial Project IAM State

The project IAM policy initially contained the developer identity:

```text
user:meryem.tanji94@gmail.com
    → roles/owner
```

No Mercury runtime service account existed.

No runtime-specific BigQuery job role was present.

This was acceptable for infrastructure development but not appropriate as the intended long-term application runtime model.

---

## 7. Initial BigQuery Dataset Access

The project contained two relevant datasets:

```text
raw
metadata
```

Both datasets initially contained BigQuery's project special-group access pattern:

```text
projectWriters → WRITER
projectOwners  → OWNER
projectReaders → READER
```

The developer identity also had explicit dataset ownership:

```text
meryem.tanji94@gmail.com → OWNER
```

The special-group entries meant that project-level readers, writers, and owners could inherit corresponding dataset access.

For datasets that may contain customer/source data or operational metadata, this was broader than Mercury's desired least-privilege model.

---

## 8. Authentication Review

Local development uses Google Application Default Credentials (ADC).

ADC was configured with:

```text
quota project:
mercury-data-platform-dev
```

The active developer account was:

```text
meryem.tanji94@gmail.com
```

No service accounts existed in the project before Phase 3.

The security decision for Mercury is:

```text
Local development
    → developer ADC is permitted

Deployed/runtime execution
    → dedicated workload identity required

Long-lived service-account key
    → prohibited
```

The local ADC credential file is security-sensitive and must never be copied into the repository or committed to source control.

---

## 9. Runtime Identity Design

A dedicated service account was created:

```text
mercury-runtime@mercury-data-platform-dev.iam.gserviceaccount.com
```

Display name:

```text
Mercury Runtime
```

Purpose:

```text
Least-privilege runtime identity for Mercury ingestion and orchestration
```

The service account was created without a service-account key.

This establishes a clear separation between:

```text
Human / infrastructure identity
        │
        ├── infrastructure provisioning
        ├── IAM administration
        ├── dataset creation
        ├── bucket creation
        └── deployment administration

Mercury runtime identity
        │
        ├── Raw object creation
        ├── BigQuery job execution
        ├── Raw dataset writes
        └── metadata read/write operations
```

---

## 10. Runtime IAM Policy

### 10.1 GCS Raw Bucket

The runtime identity was granted:

```text
roles/storage.objectCreator
```

on:

```text
gs://mercury-data-platform-dev-raw-01
```

The grant is bucket-scoped rather than project-scoped.

This permits Mercury to create new Raw objects without granting broad Storage administration privileges.

The runtime was not granted:

```text
roles/storage.admin
roles/storage.objectAdmin
```

or equivalent broad storage privileges.

---

## 11. BigQuery Job Execution

The runtime identity was granted:

```text
roles/bigquery.jobUser
```

at project level on:

```text
mercury-data-platform-dev
```

This allows Mercury to submit BigQuery jobs.

It does not grant dataset creation or general BigQuery administration.

The runtime was not granted:

```text
roles/bigquery.admin
```

or another broad project-level BigQuery administrative role.

---

## 12. BigQuery Raw Dataset Access

The runtime identity was explicitly granted:

```text
WRITER
```

on:

```text
mercury-data-platform-dev.raw
```

This corresponds to the dataset-level data-editing capability required by Mercury's Raw loader.

The runtime can therefore create and write tables inside the existing `raw` dataset as required by ingestion.

It does not receive permission to create arbitrary datasets.

---

## 13. BigQuery Metadata Dataset Access

The runtime identity was explicitly granted:

```text
WRITER
```

on:

```text
mercury-data-platform-dev.metadata
```

This supports Mercury's replay-state operations, including:

- creating permitted tables inside the existing dataset;
- appending state records;
- querying replay state;
- maintaining the replay-state control plane.

Again, this access applies to the existing dataset and does not grant arbitrary dataset creation capability.

---

## 14. Dataset Provisioning Boundary

During Phase 3, the following design rule was established:

> Dataset creation is an infrastructure/bootstrap responsibility and must not be a normal Mercury runtime capability.

The intended boundary is:

```text
INFRASTRUCTURE / HUMAN ADMINISTRATION

create GCS buckets
create BigQuery datasets
configure IAM
provision environment resources

                ↓

APPLICATION RUNTIME

write approved GCS objects
submit BigQuery jobs
create/write permitted tables
append/query operational metadata
```

This reduces the blast radius of a compromised runtime identity.

---

## 15. BigQueryReplayStateStore Validation

The existing `BigQueryReplayStateStore.ensure_resources()` implementation was reviewed because it calls an idempotent dataset creation operation before ensuring its replay-state table.

A potential concern was that this might require the runtime to possess:

```text
bigquery.datasets.create
```

Phase 3 testing demonstrated that this concern does not require broadening runtime IAM.

The runtime was explicitly tested attempting to create a new dataset.

Result:

```text
403 Forbidden

User does not have:
bigquery.datasets.create
```

Therefore:

```text
Create arbitrary new dataset
→ DENIED
```

The runtime was then tested against the already-existing `metadata` dataset using the same idempotent `exists_ok=True` behavior.

Result:

```text
Existing metadata dataset
→ accepted
```

Finally, the actual:

```text
BigQueryReplayStateStore.ensure_resources()
```

path was executed using impersonated `mercury-runtime` credentials.

Result:

```text
PASS
```

Therefore the current behavior produces the desired security boundary:

```text
Existing metadata dataset
    → runtime can ensure/use resources

Missing metadata dataset
    → runtime cannot provision it

Arbitrary new dataset
    → runtime cannot create it
```

No application code change was required for this behavior during Phase 3.

---

## 16. Service-Account Impersonation

Security validation was performed using short-lived service-account impersonation.

The developer identity was granted:

```text
roles/iam.serviceAccountTokenCreator
```

on the specific:

```text
mercury-runtime
```

service account.

This allows the developer to test Mercury exactly as the runtime identity without creating or downloading a service-account key.

The impersonation grant does not grant additional privileges to `mercury-runtime` itself.

This approach was used throughout the runtime boundary tests.

---

## 17. GCS Runtime Boundary Tests

Phase 3 explicitly tested both permitted and forbidden GCS behavior.

### 17.1 Bucket Listing

Test:

```text
mercury-runtime attempts to list project buckets
```

Expected:

```text
DENIED
```

Actual:

```text
403 Forbidden

storage.buckets.list denied
```

Result:

```text
PASS
```

This confirms that runtime object creation access does not provide broad project bucket discovery.

---

### 17.2 New Raw Object Creation

A synthetic security-test object was uploaded using impersonated runtime credentials.

The test deliberately used the same create-only pattern used by Mercury's GCS storage implementation:

```python
if_generation_match=0
```

Expected:

```text
ALLOWED
```

Actual:

```text
PASS: mercury-runtime created a new GCS object
```

Result:

```text
PASS
```

This proves the runtime can perform its legitimate Raw landing operation.

---

### 17.3 Existing Raw Object Overwrite

The exact same upload was attempted again against the existing object.

Expected:

```text
REJECTED
```

Actual:

```text
412 PreconditionFailed

At least one of the pre-conditions you specified did not hold.
```

Result:

```text
PASS
```

This validates Mercury's immutable Raw object contract.

The `if_generation_match=0` precondition prevents an existing Raw object from being silently replaced.

---

### 17.4 Raw Object Deletion

The runtime identity attempted to delete the synthetic object.

Expected:

```text
DENIED
```

Actual:

```text
403 Forbidden

storage.objects.delete denied
```

Result:

```text
PASS
```

The runtime therefore cannot delete Raw artifacts.

---

## 18. Validated GCS Security Boundary

The final validated GCS behavior is:

| Capability | Expected | Actual | Result |
|---|---|---|---|
| List project buckets | Denied | Denied | PASS |
| Create new Raw object | Allowed | Allowed | PASS |
| Overwrite existing Raw object | Denied | Denied by generation precondition | PASS |
| Delete Raw object | Denied | Denied | PASS |

This produces the desired operational model:

```text
Mercury runtime
        │
        ├── CREATE new immutable Raw object       YES
        │
        ├── OVERWRITE existing Raw object         NO
        │
        ├── DELETE Raw object                     NO
        │
        └── LIST project buckets                  NO
```

---

## 19. BigQuery Runtime Boundary Tests

### 19.1 Query Job Execution

The runtime identity executed:

```sql
SELECT 1 AS test_value
```

using impersonated credentials.

Expected:

```text
ALLOWED
```

Actual:

```text
PASS: BigQuery job executed; test_value=1
```

Result:

```text
PASS
```

This confirms that `roles/bigquery.jobUser` provides the required job-execution capability.

---

### 19.2 Dataset Creation

The runtime attempted to create:

```text
mercury_runtime_should_not_create_this
```

Expected:

```text
DENIED
```

Actual:

```text
403 Forbidden

User does not have bigquery.datasets.create permission
```

Result:

```text
PASS
```

This proves that infrastructure provisioning remains outside the runtime boundary.

---

### 19.3 Raw Dataset Write

A temporary table was created inside:

```text
raw
```

using impersonated runtime credentials.

Expected:

```text
ALLOWED
```

Actual:

```text
PASS: mercury-runtime wrote to the existing raw dataset
Rows: 1
```

Result:

```text
PASS
```

This proves that Mercury can perform the warehouse-side Raw operations required by ingestion.

---

### 19.4 Metadata Write and Query

A temporary table was created inside:

```text
metadata
```

and queried using the runtime identity.

Expected:

```text
ALLOWED
```

Actual:

```text
PASS: mercury-runtime wrote to and queried the existing metadata dataset
Rows returned: 1
```

Result:

```text
PASS
```

This validates the read/write capabilities required by replay-state orchestration.

---

## 20. Validated BigQuery Security Boundary

The resulting BigQuery capability matrix is:

| Capability | Expected | Actual | Result |
|---|---|---|---|
| Submit BigQuery jobs | Allowed | Allowed | PASS |
| Create arbitrary dataset | Denied | Denied | PASS |
| Write inside `raw` | Allowed | Allowed | PASS |
| Write inside `metadata` | Allowed | Allowed | PASS |
| Query `metadata` | Allowed | Allowed | PASS |
| Ensure existing replay-state resources | Allowed | Allowed | PASS |

The resulting boundary is:

```text
Mercury runtime
        │
        ├── SUBMIT BigQuery job               YES
        ├── WRITE approved Raw dataset         YES
        ├── WRITE approved metadata dataset    YES
        ├── QUERY approved metadata            YES
        └── CREATE arbitrary dataset           NO
```

---

## 21. Dataset ACL Hardening

After validating the explicit runtime grants, the default BigQuery special-group entries were removed from both datasets.

Removed from `raw`:

```text
projectWriters → WRITER
projectOwners  → OWNER
projectReaders → READER
```

Removed from `metadata`:

```text
projectWriters → WRITER
projectOwners  → OWNER
projectReaders → READER
```

The explicit identities were preserved.

Final `raw` access:

```text
mercury-runtime@mercury-data-platform-dev.iam.gserviceaccount.com
    → WRITER

meryem.tanji94@gmail.com
    → OWNER
```

Final `metadata` access:

```text
mercury-runtime@mercury-data-platform-dev.iam.gserviceaccount.com
    → WRITER

meryem.tanji94@gmail.com
    → OWNER
```

This prevents project-wide Reader/Writer/Owner special groups from automatically inheriting dataset access through these dataset ACLs.

---

## 22. Post-Hardening Smoke Tests

After removing the broad special-group entries, the runtime identity was tested again.

### Raw

A new temporary table was successfully written to the existing `raw` dataset.

Result:

```text
PASS: raw access still works after IAM hardening
```

### Metadata

A new temporary table was successfully written and queried inside `metadata`.

Result:

```text
PASS: metadata access still works after IAM hardening
```

Therefore removal of the broad dataset special groups did not break Mercury's explicit runtime permissions.

This confirms that Mercury's operational access now comes from its dedicated runtime grant rather than accidental inheritance through project-wide dataset groups.

---

## 23. Final Runtime Permission Model

The validated development runtime policy is:

```text
mercury-runtime
│
├── GCS Raw bucket
│   └── roles/storage.objectCreator
│
├── GCP project
│   └── roles/bigquery.jobUser
│
├── BigQuery raw
│   └── WRITER
│
└── BigQuery metadata
    └── WRITER
```

No broad Storage or BigQuery administrative role is required.

Specifically, Mercury does not require:

```text
roles/storage.admin
roles/storage.objectAdmin
roles/bigquery.admin
roles/owner
roles/editor
```

for normal runtime execution.

---

## 24. Final Human / Runtime Separation

The resulting architecture is:

```text
                    HUMAN / INFRASTRUCTURE
                            │
             ┌──────────────┼──────────────┐
             │              │              │
        create bucket   create datasets   configure IAM
             │              │              │
             └──────────────┬──────────────┘
                            │
                     provisioned env
                            │
                            ▼
                     MERCURY RUNTIME
                            │
          ┌─────────────────┼─────────────────┐
          │                 │                 │
      create Raw       BigQuery jobs      replay state
       objects              │                 │
          │                 │                 │
      no delete         approved          approved
      no overwrite      datasets          metadata
```

The runtime cannot independently expand its infrastructure footprint by creating new datasets or administering storage.

---

## 25. Credential Security

No service-account key was created during Phase 3.

Runtime testing used service-account impersonation and short-lived credentials.

This is intentional.

Mercury's security posture should continue to prefer:

```text
workload identity / attached service identity
                or
short-lived impersonated credentials
```

over:

```text
downloaded JSON service-account keys
```

Long-lived service-account keys should not become part of the normal Mercury deployment model.

---

## 26. Temporary Test Artifacts

The security-boundary tests used deliberately synthetic resources only.

Temporary artifacts included:

```text
GCS:
security-tests/security-boundary-test.txt

BigQuery raw:
security_boundary_test
security_boundary_test_final

BigQuery metadata:
security_boundary_test
security_boundary_test_final
```

These test artifacts were removed after validation.

The existing production-shaped Mercury tables were left intact, including:

```text
metadata.historical_replay_state
```

No customer test data was required for the IAM boundary validation.

---

## 27. Security Findings Closed by Phase 3

### Finding 1 — No dedicated runtime identity

**Before**

Mercury development relied on developer credentials.

**After**

A dedicated:

```text
mercury-runtime
```

service account exists with explicitly bounded permissions.

**Status:** Closed.

---

### Finding 2 — Runtime identity could have been granted broad convenience roles

**Risk**

A broad role such as Storage Admin or BigQuery Admin would unnecessarily increase blast radius.

**Resolution**

Runtime permissions were derived from tested capabilities and restricted to:

```text
storage.objectCreator
bigquery.jobUser
raw WRITER
metadata WRITER
```

**Status:** Closed.

---

### Finding 3 — Runtime dataset provisioning ambiguity

**Risk**

If runtime required dataset creation, it would need a broader project-level BigQuery permission.

**Resolution**

Testing proved:

```text
new dataset creation → denied
existing metadata ensure → succeeds
```

Therefore infrastructure provisioning remains human/infrastructure-owned without breaking normal runtime behavior.

**Status:** Closed.

---

### Finding 4 — Broad BigQuery dataset special-group access

**Before**

Both datasets inherited access through:

```text
projectReaders
projectWriters
projectOwners
```

**After**

Those entries were removed.

Access is now explicitly granted to the required principals.

**Status:** Closed.

---

### Finding 5 — Potential long-lived runtime credentials

**Risk**

Service-account key files introduce persistent credential material that can be copied, leaked, or committed.

**Resolution**

No service-account key was created.

Testing used service-account impersonation and short-lived credentials.

**Status:** Closed for the Phase 3 implementation.

---

## 28. Security Properties Established

Phase 3 establishes the following security properties for the current Mercury development infrastructure:

### Least privilege

Mercury receives only the cloud capabilities demonstrated to be necessary for runtime operation.

### Explicit access

Sensitive BigQuery datasets no longer rely on broad project special-group ACL entries.

### Immutable Raw landing

Runtime can create new Raw objects but Mercury's create-only write contract prevents replacement of an existing Raw artifact.

### Restricted deletion

Runtime cannot delete Raw GCS objects.

### Infrastructure separation

Runtime cannot create arbitrary BigQuery datasets.

### Keyless runtime design

No long-lived service-account key is required.

### Fail-closed provisioning

If required infrastructure has not been provisioned, runtime is not granted administrative authority merely to create it.

---

## 29. Residual Considerations

Phase 3 deliberately does not claim that all future production IAM is complete.

The following should remain part of future infrastructure/deployment work:

- production-specific runtime identities;
- CI/CD deployment identities;
- automated IAM provisioning;
- infrastructure-as-code representation of bucket, dataset, and IAM configuration;
- environment-specific access boundaries;
- Secret Manager permissions where secrets are introduced;
- periodic IAM review;
- service-account lifecycle management;
- audit-log monitoring and alerting;
- review of whether additional read-only operational identities are required.

The current developer account remains highly privileged because the development environment is still being actively provisioned.

That privilege should not be interpreted as the intended runtime or production-user access model.

---

## 30. Recommended Infrastructure-as-Code Direction

The configuration validated during Phase 3 should eventually be represented declaratively.

The desired infrastructure definition should include:

```text
GCS Raw bucket
    public access prevention
    uniform bucket-level access
    retention / recovery settings
    runtime objectCreator grant

BigQuery raw dataset
    explicit runtime access
    explicit administrative access

BigQuery metadata dataset
    explicit runtime access
    explicit administrative access

Mercury runtime service account
    project-level BigQuery jobUser
    resource-scoped storage/data access
```

Infrastructure-as-code should reproduce the validated policy rather than introducing broader predefined roles for convenience.

---

## 31. Phase 3 Acceptance Criteria

Phase 3 is considered complete because the following criteria were demonstrated:

- [x] GCS bucket security configuration inspected.
- [x] BigQuery dataset access inspected.
- [x] Project IAM inspected.
- [x] Dedicated Mercury runtime identity created.
- [x] No service-account key created.
- [x] GCS access scoped to Raw object creation.
- [x] BigQuery job execution granted explicitly.
- [x] `raw` dataset access granted explicitly.
- [x] `metadata` dataset access granted explicitly.
- [x] Runtime cannot list project buckets.
- [x] Runtime can create a new Raw object.
- [x] Existing Raw object replacement is rejected.
- [x] Runtime cannot delete Raw objects.
- [x] Runtime can execute BigQuery jobs.
- [x] Runtime cannot create arbitrary BigQuery datasets.
- [x] Runtime can write to the existing `raw` dataset.
- [x] Runtime can write/query the existing `metadata` dataset.
- [x] `BigQueryReplayStateStore.ensure_resources()` works against provisioned infrastructure.
- [x] Broad `projectReaders` dataset access removed.
- [x] Broad `projectWriters` dataset access removed.
- [x] Broad `projectOwners` dataset access removed.
- [x] Explicit developer ownership preserved.
- [x] Explicit Mercury runtime access preserved.
- [x] Runtime capabilities re-tested after ACL hardening.
- [x] Temporary security-test artifacts removed.

---

## 32. Phase 3 Conclusion

ADR-011 Phase 3 established and experimentally validated a least-privilege infrastructure boundary for Mercury.

The most important result is that Mercury does not need broad cloud administrative privileges to perform its runtime responsibilities.

The validated model is:

```text
Infrastructure provisioning
        ↓
human / deployment responsibility

Runtime execution
        ↓
dedicated mercury-runtime identity

Raw GCS
        ↓
create only

BigQuery
        ↓
jobs + approved dataset access

Infrastructure administration
        ↓
denied to runtime
```

Positive tests demonstrated that Mercury retains the capabilities required for ingestion and orchestration.

Negative tests demonstrated that the same identity is prevented from performing operations outside its responsibility, including Raw object deletion, broad bucket discovery, and arbitrary BigQuery dataset creation.

The BigQuery dataset ACLs were additionally hardened so that access no longer depends on broad project Reader/Writer/Owner special groups.

No long-lived service-account credential was introduced.

**ADR-011 Phase 3 status: COMPLETE.**