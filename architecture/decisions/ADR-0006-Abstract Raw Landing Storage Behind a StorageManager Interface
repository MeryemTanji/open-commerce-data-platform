# ADR-006 — Abstract Raw Landing Storage Behind a StorageManager Interface

## Status

Accepted

## Context

Mercury's ingestion framework was initially developed and validated using local filesystem storage.

During Phase 1, source connectors received a `LocalStorageManager` and used it to land source files into an immutable, date-partitioned Raw Landing structure:

    <root_directory>/
        raw/
            <source_system>/
                <source_object>/
                    ingestion_date=YYYY-MM-DD/
                        <original_filename>

`LocalStorageManager` is responsible only for the technical act of landing a source artifact. It:

- preserves the source file unchanged;
- prevents accidental overwrite of an existing destination;
- computes a SHA-256 checksum;
- records the landed file size;
- returns a `StorageResult` describing the landed artifact.

It intentionally does not:

- parse source data;
- validate business rules;
- count source records;
- transform data;
- load data into an analytical warehouse;
- manage ingestion metadata.

This separation has worked well during local development.

However, the original implementation introduced a concrete dependency between the ingestion framework and local filesystem storage. `BaseConnector` expects a `LocalStorageManager`, meaning connectors cannot use another Raw Landing implementation without changing the connector abstraction itself.

Phase 2 introduces the first real alternative storage implementation: Google Cloud Storage.

Mercury therefore now has two legitimate Raw Landing targets:

1. the local filesystem for local development and testing;
2. Google Cloud Storage for cloud execution.

This creates a demonstrated need for a shared storage abstraction.

As with the introduction of `BaseCsvConnector`, Mercury deliberately deferred this abstraction until repeated or alternative behavior existed in concrete implementations. The storage interface is therefore being introduced in response to a proven requirement rather than speculative future extensibility.

---

## Decision

Mercury will introduce a `StorageManager` abstraction representing the capability to land an immutable Raw source artifact.

Both local filesystem storage and Google Cloud Storage will implement this abstraction:

    StorageManager
        ├── LocalStorageManager
        └── GCSStorageManager

Source connectors will depend on `StorageManager`, not on either concrete implementation.

The storage contract will preserve the existing `save_file()` interface:

    save_file(
        source_file: Path,
        source_system: str,
        source_object: str,
        ingestion_date: date,
    ) -> StorageResult

The existing `StorageResult` will remain the common technical result returned by all storage implementations:

    StorageResult
        landing_path
        checksum
        file_size_bytes

This allows connector behavior and ingestion metadata generation to remain independent of the physical storage technology.

---

## StorageManager Contract

A storage implementation must accept:

- a local source file;
- the source system identifier;
- the source object identifier;
- the ingestion date.

It must land the source artifact without changing its contents and return:

### `landing_path`

The authoritative location of the landed artifact.

For local storage this may be:

    C:\...\data\raw\order_platform\orders\ingestion_date=2026-08-16\olist_orders_dataset.csv

For Google Cloud Storage this may be:

    gs://mercury-data-platform-dev-raw-01/raw/order_platform/orders/ingestion_date=2026-08-16/olist_orders_dataset.csv

Consumers of `StorageResult` must treat `landing_path` as a storage URI/location string rather than assuming that it represents a local filesystem path.

### `checksum`

The SHA-256 checksum of the source artifact.

SHA-256 remains Mercury's storage-independent integrity checksum even when the underlying storage provider exposes additional checksum mechanisms.

This ensures that checksum semantics remain consistent across local and cloud storage implementations.

### `file_size_bytes`

The size of the landed artifact in bytes.

This remains storage-independent technical metadata.

---

## Logical Raw Landing Layout

All storage implementations should preserve the same logical Raw Landing hierarchy where practical:

    raw/
        <source_system>/
            <source_object>/
                ingestion_date=YYYY-MM-DD/
                    <original_filename>

The physical representation differs by storage technology, but the logical organization does not.

For example:

### Local filesystem

    data/
        raw/
            order_platform/
                orders/
                    ingestion_date=2026-08-16/
                        olist_orders_dataset.csv

### Google Cloud Storage

    gs://<bucket>/
        raw/
            order_platform/
                orders/
                    ingestion_date=2026-08-16/
                        olist_orders_dataset.csv

Maintaining this structure keeps local development behavior aligned with cloud execution and makes Raw artifacts predictable regardless of storage backend.

---

## Immutability and Overwrite Protection

Mercury's Raw Landing layer is immutable.

A storage manager must therefore prevent an existing destination artifact from being silently overwritten.

### LocalStorageManager

The local implementation checks whether the destination file already exists and raises `FileExistsError` rather than replacing it.

It also copies through a temporary file before renaming to the final destination so that a partially written file is not exposed at the intended destination.

### GCSStorageManager

The Google Cloud Storage implementation must preserve equivalent create-only semantics.

It must use Google Cloud Storage's object-generation precondition when uploading a new Raw object:

    if_generation_match=0

This ensures that the upload succeeds only when no live object already exists at the destination.

The implementation must not rely solely on:

    check whether object exists
        ↓
    upload object

because another writer could create the object between those two operations.

Using a storage-level precondition provides atomic create-only behavior and preserves Mercury's Raw immutability guarantee under concurrent execution.

Provider-specific exceptions may be translated into Mercury's existing storage-level error semantics where appropriate so callers do not need to understand Google Cloud Storage implementation details.

---

## Integrity Verification

Mercury will continue to use SHA-256 as its platform-level artifact integrity checksum.

The checksum represents the bytes of the source artifact and must have the same meaning regardless of whether the artifact is stored locally or in Google Cloud Storage.

Google Cloud Storage may independently calculate provider-specific integrity values such as CRC32C or MD5 where applicable. These mechanisms are useful for transport and provider-level integrity validation but do not replace Mercury's SHA-256 metadata contract.

Therefore:

    LocalStorageManager
            │
            └── SHA-256
                    │
                    ▼
               StorageResult

    GCSStorageManager
            │
            └── SHA-256
                    │
                    ▼
               StorageResult

The meaning of `StorageResult.checksum` remains stable across implementations.

---

## Separation from BigQuery

`GCSStorageManager` will not be responsible for loading Raw files into BigQuery.

Cloud Storage Raw Landing and BigQuery Raw ingestion are separate platform capabilities.

The responsibility boundary is:

    Source Connector
            ↓
    StorageManager
            ↓
    Immutable Raw Artifact
            ↓
    separate warehouse-loading capability
            ↓
    BigQuery Raw Table

This preserves the single-responsibility boundary already established by `LocalStorageManager`.

A storage implementation answers:

> Where and how should this source artifact be safely landed?

It does not answer:

> How should the contents of this artifact become an analytical table?

BigQuery loading will therefore be designed separately.

---

## Authentication

`GCSStorageManager` will use Google Cloud Application Default Credentials rather than accepting credential files or secrets directly through the connector API.

During local development:

    Mercury Python
        ↓
    Application Default Credentials
        ↓
    Developer Google identity
        ↓
    Google Cloud Storage

During future cloud deployment:

    Mercury workload
        ↓
    Application Default Credentials
        ↓
    Workload service account
        ↓
    Google Cloud Storage

This allows authentication identity to change between environments without changing connector or storage-manager business logic.

Service-account JSON keys must not be stored in the Mercury repository.

---

## Connector Independence

Concrete source connectors must not contain storage-specific behavior.

For example, `OrdersConnector` should not know whether its source artifact is being landed to:

- a local Windows filesystem;
- Google Cloud Storage;
- another future implementation.

Its responsibility remains:

1. validate source structure;
2. determine source metadata;
3. request that the configured storage capability land the artifact;
4. use the returned `StorageResult` to construct ingestion metadata.

Therefore the dependency direction becomes:

    BaseConnector
          │
          ▼
    StorageManager
       /      \
      /        \
     ▼          ▼
    Local      GCS

rather than:

    BaseConnector
          │
          ▼
    LocalStorageManager

This keeps source semantics independent from infrastructure choices.

---

## Implementation Approach

The change will be introduced incrementally.

### Step 1 — Introduce StorageManager

Create an abstract `StorageManager` defining the existing `save_file()` contract.

### Step 2 — Adapt LocalStorageManager

`LocalStorageManager` will implement `StorageManager`.

Its existing externally observable behavior should remain unchanged.

### Step 3 — Generalize BaseConnector

`BaseConnector` will accept the `StorageManager` abstraction rather than requiring `LocalStorageManager`.

Concrete connectors should require no behavioral changes.

### Step 4 — Regression Verification

Run the complete existing automated test suite.

All existing connector and ingestion tests must continue to pass before any GCS implementation is introduced.

This proves that introducing the abstraction has not changed established local behavior.

### Step 5 — Implement GCSStorageManager

Add the Google Cloud Storage implementation against the established contract.

It will:

- target a configured bucket;
- preserve the logical Raw Landing path;
- upload source bytes without transformation;
- enforce create-only object creation;
- calculate Mercury's SHA-256 checksum;
- return `StorageResult`.

### Step 6 — Cloud Integration Verification

Execute a real source connector using `GCSStorageManager` against Mercury's development GCS bucket.

Verify:

- the object exists at the expected path;
- the object is stored in the intended bucket;
- the source bytes are preserved;
- SHA-256 integrity matches the source file;
- file size matches;
- the returned `landing_path` is the correct `gs://` URI;
- attempting to land the same destination again does not overwrite the existing object.

### Step 7 — Full Multi-Source Verification

After individual cloud storage behavior is validated, execute Mercury's complete eight-source ingestion batch against the cloud storage implementation.

This verifies that changing storage backend does not change connector semantics.

---

## Alternatives Considered

### Keep BaseConnector dependent on LocalStorageManager

Rejected.

This would require source connectors or the connector base class to change whenever Mercury runs outside the local filesystem environment.

It would couple source ingestion behavior to infrastructure.

---

### Make GCSStorageManager inherit from LocalStorageManager

Rejected.

Google Cloud Storage is not a specialized form of local filesystem storage.

Although both provide the same Raw Landing capability, their implementation semantics differ substantially, including path representation, atomicity mechanisms, API behavior, authentication, and failure modes.

Both should implement a shared capability rather than one pretending to be a subtype of the other.

---

### Use duck typing without an explicit abstraction

Rejected for the current design.

Mercury already uses explicit component contracts and runtime validation within its ingestion framework.

An explicit storage abstraction makes the dependency boundary visible, testable, and documented.

---

### Introduce the storage abstraction during Phase 1

Rejected retrospectively as premature abstraction.

At that point Mercury had only one storage implementation.

Although cloud storage was anticipated, the exact shared behavior had not yet been proven by a second implementation requirement.

Introducing the abstraction now allows it to be derived from working local behavior and concrete GCS requirements.

---

### Include BigQuery loading inside GCSStorageManager

Rejected.

Cloud Storage and BigQuery serve different platform responsibilities.

Combining them would couple artifact preservation to warehouse loading, make failure handling ambiguous, and reduce the ability to replay Raw data independently.

---

### Replace SHA-256 with Google Cloud Storage checksums

Rejected.

Doing so would make the meaning of ingestion metadata dependent on the storage provider.

Mercury requires one stable integrity definition across storage implementations.

Provider-native checksums may complement this but do not replace the platform-level SHA-256 contract.

---

## Consequences

### Positive

- Connectors become independent of physical storage technology.
- Local and cloud execution can use the same connector implementations.
- Existing `StorageResult` semantics remain stable.
- Raw Landing layout remains consistent between environments.
- GCS can enforce immutable writes atomically.
- Authentication can change between local and cloud environments without changing connector code.
- BigQuery loading remains independently evolvable.
- Future storage implementations can be introduced behind an established contract if a real requirement emerges.

### Negative

- The storage layer gains an additional abstraction.
- Runtime type relationships and tests must be updated.
- GCS introduces provider-specific failure modes that must be mapped carefully.
- Integration testing now requires both local tests and selected real-cloud verification.

These costs are justified because Mercury now has two concrete storage implementations requiring the same capability.

---

## Non-Goals

This decision does not introduce:

- BigQuery table loading;
- BigQuery schema management;
- data transformation;
- business validation;
- record-level deduplication;
- lifecycle policies beyond existing bucket configuration;
- distributed locking;
- cross-region replication;
- object versioning;
- automatic retries across the ingestion framework;
- service-account key files;
- support for arbitrary storage providers.

These capabilities may be evaluated separately when concrete requirements emerge.

---

## Resulting Architecture

After this decision, the Raw Landing portion of Mercury becomes:

    Source files
         │
         ▼
    Source Connectors
         │
         ▼
    BaseConnector
         │
         ▼
    StorageManager
       /        \
      /          \
     ▼            ▼
    Local         GCS
     │             │
     ▼             ▼
    Local Raw     Cloud Raw
    Landing       Landing
         \         /
          \       /
           ▼     ▼
         StorageResult
              │
              ▼
       Ingestion Metadata

The storage backend becomes an infrastructure choice rather than a source-connector concern.

---

## Principle Established

Mercury source connectors depend on storage capabilities, not storage technologies.

Infrastructure-specific behavior belongs behind explicit platform interfaces, and shared abstractions should be introduced only when concrete implementations demonstrate the need for them.