# Mercury GCP Infrastructure

**Project:** Mercury — Open Commerce Data Platform  
**Environment:** Development  
**GCP Project:** `mercury-data-platform-dev`  
**Primary Region:** `europe-west4`  
**Status:** Living implementation document

---

## 1. Purpose

This document records the concrete Google Cloud infrastructure currently used by Mercury.

Architecture Decision Records define the architectural rules governing the platform. This document describes how those decisions are currently implemented in the Mercury development environment.

It is intentionally implementation-focused.

In particular:

- ADR-006 defines the Raw storage abstraction;
- ADR-008 defines the BigQuery Raw loading architecture;
- ADR-010 defines replay, recovery, provenance, and reconciliation;
- ADR-011 defines Mercury's security and least-privilege requirements;
- ADR-012 defines the separation between Terraform-managed infrastructure and Dataform-managed analytical transformations.

This document should be updated when Mercury's deployed infrastructure materially changes.

---

## 2. Infrastructure Principles

Mercury separates infrastructure provisioning from application and transformation execution.

The responsibility model is:

```text
Terraform
    │
    ├── datasets
    ├── buckets
    ├── service accounts
    ├── IAM
    └── other GCP infrastructure
    │
    ▼
Provisioned Infrastructure
    │
    ├───────────────┐
    │               │
    ▼               ▼
Ingestion        Dataform
Runtime          Transformations
```

## 3. Google Cloud Project

Mercury's current development environment runs in:

    mercury-data-platform-dev

The primary regional location is:

    europe-west4

Mercury prefers explicit regional placement over broad multi-regions where practical so data location remains deliberate and infrastructure does not drift because of local CLI defaults.

## 4. Google Cloud Storage

### Raw Landing Bucket

Mercury's immutable Raw object storage is:

    gs://mercury-data-platform-dev-raw-01

purpose: 

```text
source delivery
      ↓
connector
      ↓
immutable GCS Raw artifact
```

Raw objects follow a deterministic hierarchy:

```text
raw/
└── <source_system>/
    └── <source_object>/
        └── ingestion_date=YYYY-MM-DD/
            └── <source_file>
```

Key characteristics include:

immutable create-only object creation;
source payload preservation;
SHA-256 integrity metadata;
Uniform Bucket-Level Access;
Public Access Prevention;
restricted destructive runtime access.

The detailed storage architecture is defined by [ADR-006](../../architecture/decisions/ADR-006-Abstract%20Raw%20Landing%20Storage%20Behind%20a%20StorageManager%20Interface.md).

Security validation of the bucket is documented under:

    docs/security/

## 5. BigQuery

Mercury currently uses three main BigQuery datasets.

```text
BigQuery
├── raw
├── metadata
└── staging
```

### 5.1 raw

Purpose:

    queryable source-faithful warehouse representation

The Raw dataset contains source-specific Raw tables loaded from immutable GCS artifacts.

Current Olist source tables include:

    customers
    geolocations
    orders
    order_items
    payments
    products
    reviews
    sellers

Raw schemas are explicit and source fields are intentionally loaded as STRING for the current ingestion design.

The Raw layer does not perform analytical standardisation.

Detailed behavior is governed by [ADR-008](../../architecture/decisions/ADR-008-Define%20the%20BigQuery%20Raw%20Loading%20Strategy.md).

### 5.2 metadata

Purpose: 

    Mercury operational control-plane state

The metadata dataset is separate from business Raw data.

It contains operational information required for capabilities such as:

- historical replay state;
- artifact provenance;
- warehouse-load provenance;
- recovery and reconciliation support.

Operational metadata must not become a secondary store for customer/source payload data.

The control-plane architecture is governed by [ADR-010](../../architecture/decisions/ADR-010-Persist%20Source-Level%20Historical%20Replay%20State%20and%20Derive%20Date-Level%20Completion.md) and [ADR-011](../../architecture/decisions/ADR-011-Data%20Security,%20Privacy,%20and%20Data-Leak%20Prevention.md).

### 5.3 staging

Purpose:

    standardised analytical representation

The staging dataset is the first analytical transformation layer above BigQuery Raw.

Current configuration:

    project     = mercury-data-platform-dev
    dataset     = staging
    location    = europe-west4
    managed_by  = terraform

The dataset was initially created during local Dataform experimentation.

Rather than deleting and recreating the correctly located dataset, Mercury imported the existing resource into Terraform state and brought its infrastructure metadata under Terraform management.

Terraform currently manages:

- dataset identity;
- regional location;
- description;
- Mercury environment/layer labels.

Dataform manages analytical relations created inside the dataset.

This establishes the intended separation:

```text
Terraform
    ↓
staging dataset

Dataform
    ↓
staging tables / views / assertions
```

## 6. Service Accounts

### 6.1 mercury-runtime

Current workload identity:

    mercury-runtime@mercury-data-platform-dev.iam.gserviceaccount.com

Purpose:

    ingestion and operational Raw-platform execution

This identity was introduced and validated under [ADR-011](../../architecture/decisions/ADR-011-Data%20Security,%20Privacy,%20and%20Data-Leak%20Prevention.md).

Its permissions are intentionally bounded to the capabilities required by ingestion and orchestration.

The runtime is not intended to serve as a general Mercury administrator or as the transformation identity for Dataform.

### 6.2 Dataform Transformation Identity

**Status:** In progress

Mercury will use a separate workload identity for analytical transformations rather than extending the ingestion runtime identity.

Intended responsibility:

```text
BigQuery Raw
      │
      │ READ
      ▼
Dataform Transformation Runtime
      │
      │ WRITE / READ
      ▼
BigQuery Staging
```

The intended permission boundary is:

```text
Project
└── BigQuery job execution

raw dataset
└── read

staging dataset
└── read / write
```

The transformation identity should not require:

    GCS Raw access
    Raw modification
    arbitrary dataset creation
    IAM administration
    service-account administration
    access to unrelated datasets

The exact service-account and IAM configuration will be recorded here after implementation and validation.

## 7. Terraform

Terraform is Mercury's Infrastructure-as-Code tool.

Current repository location:

```text
terraform/
└── environments/
    └── dev/
        ├── providers.tf
        ├── variables.tf
        ├── main.tf
        ├── outputs.tf
        └── .terraform.lock.hcl
```

The initial Terraform implementation manages the BigQuery staging dataset.

Mercury is adopting Terraform incrementally rather than attempting to migrate all existing infrastructure into Infrastructure as Code at once.

Future candidates for Terraform management include:

- additional BigQuery datasets;
- Cloud Storage infrastructure;
- service accounts;
- IAM bindings;
- Cloud Run;
- Cloud Scheduler;
- other production infrastructure.

Infrastructure resources should be reviewed through:

```text
terraform fmt
      ↓
terraform init
      ↓
terraform validate
      ↓
terraform plan
      ↓
review
      ↓
terraform apply
```

Saved plans should be reviewed before application when practical.

## 8. Local Infrastructure Artifacts

Local execution may create files that must never be committed to source control.

Mercury's .gitignore protects artifacts including:

    Dataform local credentials
    Terraform working directories
    Terraform state
    Terraform saved plans
    local Terraform variable files

Examples include:

    dataform/.df-credentials.json
    .terraform/
    *.tfstate
    *.tfstate.*
    tfplan
    *.tfplan
    *.tfvars
    *.tfvars.json

Terraform's provider lock file:

    .terraform.lock.hcl

is intentionally version controlled.

No long-lived service-account key is required for Mercury's runtime model.

## 9. Dataform Infrastructure Boundary

Dataform is Mercury's analytical transformation framework.

Its responsibility includes:

- Raw source declarations;
- staging transformations;
- semantic casting;
- normalisation;
- staging assertions;
- future canonical transformations;
- future downstream analytical models.

Dataform is not Mercury's infrastructure-provisioning authority.

Therefore:

    Dataform
        ✕ should not create arbitrary datasets
        ✕ should not manage IAM
        ✕ should not administer GCS
        ✕ should not provision unrelated infrastructure

while:

    Terraform
        ✓ provisions infrastructure

    Dataform
        ✓ transforms data inside approved infrastructure

This boundary is governed by [ADR-011](../../architecture/decisions/ADR-011-Data%20Security,%20Privacy,%20and%20Data-Leak%20Prevention.md) and [ADR-012](../../architecture/decisions/ADR-012-Staging%20Layer%20Standardization%20and%20Semantic%20Contracts.md).

## 10. Current Infrastructure State

```text
GCP Project
mercury-data-platform-dev
        │
        ├── GCS
        │   └── immutable Raw Landing
        │
        ├── BigQuery
        │   ├── raw
        │   ├── metadata
        │   └── staging
        │
        ├── Service Accounts
        │   ├── mercury-runtime
        │   └── Dataform transformation identity
        │       └── IN PROGRESS
        │
        └── Terraform
            └── staging dataset management
```

## 11. Next Infrastructure Milestone

The next infrastructure task is to establish and validate the dedicated Dataform transformation identity.

The implementation sequence is:

```text
Create dedicated transformation identity
             ↓
Grant BigQuery job execution
             ↓
Grant Raw read access
             ↓
Grant Staging read/write access
             ↓
Validate prohibited capabilities
             ↓
Execute Dataform under intended boundary
```

After this is complete, this document should be updated with the final service-account name, IAM scopes, and validation results.

## 12. Related Documentation

Architectural Decisions:

    architecutre/decisions/

Relevant ADRs:

- ADR-006 — Raw Landing Storage Abstraction
- ADR-008 — BigQuery Raw Loading
- ADR-010 — Historical Replay State and Recovery
- ADR-011 — Data Security, Privacy, and Data-Leak Prevention
- ADR-012 — Staging Layer Standardization and Semantic Contracts

Security implementation evidence:

    docs/security/

Analytics-engineering implementation contract:

    docs/olist_staging_contracts.md