# Dataform Transformation Identity Validation

**Status:** Complete  
**Security contract:** ADR-011 — Data Security, Privacy, and Data-Leak Prevention  
**Environment:** `mercury-data-platform-dev`  
**Region:** `europe-west4`  
**Validation date:** 2026-08-27

---

## 1. Purpose

This document records the implementation and validation of Mercury’s dedicated Dataform transformation identity.

The transformation identity is intentionally separate from:

```text
mercury-runtime
```

which remains responsible for ingestion and operational Raw-platform execution.

The Dataform identity is designed to:

- execute BigQuery transformation jobs;
- read source-faithful data from BigQuery Raw;
- create and manage analytical relations inside BigQuery Staging;
- operate without access to Raw GCS artifacts or unrelated BigQuery datasets;
- use short-lived credentials rather than a service-account key.

This document contains the detailed validation evidence. The final infrastructure configuration is summarized separately in:

```text
docs/infrastructure/gcp_infrastructure.md
```

---

## 2. Transformation Identity

The dedicated service account is:

```text
mercury-dataform@mercury-data-platform-dev.iam.gserviceaccount.com
```

Display name:

```text
Mercury Dataform
```

Purpose:

```text
Dedicated least-privilege service account for Mercury analytical transformations.
```

The service account was created and is managed through Terraform.

No service-account key was created.

---

## 3. Terraform-Managed IAM Boundary

The transformation identity receives the following permissions:

| Scope | Role | Purpose |
|---|---|---|
| Project `mercury-data-platform-dev` | `roles/bigquery.jobUser` | Execute BigQuery jobs |
| BigQuery dataset `raw` | `roles/bigquery.dataViewer` | Read Raw tables and data |
| BigQuery dataset `staging` | `roles/bigquery.dataEditor` | Create, replace, read, update, and delete staging relations |

The developer identity:

```text
user:meryem.tanji94@gmail.com
```

receives:

```text
roles/iam.serviceAccountTokenCreator
```

only on the dedicated `mercury-dataform` service account.

This enables local validation through short-lived impersonated credentials without granting project-wide impersonation.

The relevant Terraform resources are:

```text
google_service_account.dataform

google_project_iam_member.dataform_bigquery_job_user

google_bigquery_dataset_iam_member.dataform_raw_reader

google_bigquery_dataset_iam_member.dataform_staging_editor

google_service_account_iam_member.dataform_developer_token_creator
```

After deployment, Terraform reported no configuration drift:

```text
No changes. Your infrastructure matches the configuration.
```

---

## 4. Explicitly Prohibited Capabilities

The Dataform identity was not granted:

- GCS Raw access;
- BigQuery Raw modification rights;
- access to the `metadata` dataset;
- arbitrary BigQuery dataset creation;
- IAM administration;
- service-account administration;
- project Editor or Owner;
- broad BigQuery administration;
- broad Storage administration.

The intended boundary is:

```text
BigQuery Raw
     │
     │ read only
     ▼
mercury-dataform
     │
     │ transformations
     ▼
BigQuery Staging
     │
     └── controlled read/write
```

---

## 5. Credential and Impersonation Validation

The developer identity successfully generated a short-lived access token by impersonating:

```text
mercury-dataform@mercury-data-platform-dev.iam.gserviceaccount.com
```

Result:

```text
IMPERSONATION_OK
```

Google Application Default Credentials were then configured to use the same impersonated identity.

Result:

```text
IMPERSONATED_ADC_OK
```

The local Dataform credentials configuration references only:

```text
projectId:
mercury-data-platform-dev

location:
europe-west4
```

The local credentials file remains protected from source control.

No private key, access token, or long-lived service-account credential was added to the repository.

---

## 6. Positive Permission Validation

### 6.1 BigQuery Job Execution and Raw Read

The transformation identity executed a query against:

```text
mercury-data-platform-dev.raw.customers
```

The query returned:

```text
row_count = 99441
```

Result:

```text
PASS
```

This demonstrated that the identity can:

- execute BigQuery jobs;
- access the Raw dataset;
- read Raw table data.

### 6.2 Staging Relation Lifecycle

A temporary synthetic table was created inside:

```text
mercury-data-platform-dev.staging
```

The table was queried successfully and returned:

```text
test_value = 1
```

The same transformation identity then deleted the temporary table.

Result:

```text
STAGING_CLEANUP_OK
```

This demonstrated the create, read, and delete capabilities required for Dataform-managed staging relations.

No customer data was used in this validation.

---

## 7. Negative Permission Validation

### 7.1 Raw Modification

The transformation identity attempted to create a synthetic table inside:

```text
mercury-data-platform-dev.raw
```

Google Cloud denied:

```text
bigquery.tables.create
```

Result:

```text
RAW_WRITE_DENIED_OK
```

### 7.2 Arbitrary Dataset Creation

The transformation identity attempted to create a new BigQuery dataset.

Google Cloud denied:

```text
bigquery.datasets.create
```

Result:

```text
DATASET_CREATION_DENIED_OK
```

### 7.3 Raw GCS Access

The transformation identity attempted to list objects in:

```text
gs://mercury-data-platform-dev-raw-01
```

Google Cloud denied:

```text
storage.objects.list
```

Result:

```text
GCS_RAW_ACCESS_DENIED_OK
```

No Raw object names or payload contents were exposed.

### 7.4 Metadata Dataset Access

The transformation identity attempted to list tables in:

```text
mercury-data-platform-dev.metadata
```

The request was denied.

Result:

```text
METADATA_ACCESS_DENIED_OK
```

---

## 8. Validated Capability Matrix

| Capability | Expected | Actual | Result |
|---|---|---|---|
| Impersonate `mercury-dataform` using short-lived credentials | Allowed for approved developer | Allowed | PASS |
| Execute BigQuery jobs | Allowed | Allowed | PASS |
| Read BigQuery Raw | Allowed | Allowed | PASS |
| Create relations in BigQuery Staging | Allowed | Allowed | PASS |
| Read relations in BigQuery Staging | Allowed | Allowed | PASS |
| Delete temporary relations in BigQuery Staging | Allowed | Allowed | PASS |
| Modify BigQuery Raw | Denied | Denied | PASS |
| Create arbitrary BigQuery datasets | Denied | Denied | PASS |
| Access Raw GCS | Denied | Denied | PASS |
| Access BigQuery Metadata | Denied | Denied | PASS |

---

## 9. Dataform Compilation and Execution

The Dataform project compiled successfully under the impersonated Application Default Credentials.

Compilation produced three actions:

```text
staging.stg_customers

staging.staging_stg_customers_assertions_uniqueKey_0

staging.staging_stg_customers_assertions_rowConditions
```

The first targeted execution created:

```text
staging.stg_customers
```

A subsequent full dry run completed successfully after the table existed.

The complete Dataform graph was then executed.

Results:

```text
Table created:
staging.stg_customers

Assertion passed:
staging.staging_stg_customers_assertions_uniqueKey_0

Assertion passed:
staging.staging_stg_customers_assertions_rowConditions
```

The execution was performed using the dedicated transformation identity and the intended `europe-west4` location.

---

## 10. Staging Contract Validation

The resulting staging table was reconciled against the Raw source.

| Validation | Result |
|---|---:|
| Raw row count | 99,441 |
| Staging row count | 99,441 |
| Rows containing required-field nulls | 0 |
| Duplicate `customer_id` values | 0 |
| Non-lowercase customer cities | 0 |
| Non-uppercase customer states | 0 |

The Raw and staging row counts match, confirming that the staging transformation preserved the source grain.

The materialized schema contains exactly:

| Column | Type |
|---|---|
| `customer_id` | `STRING` |
| `customer_unique_id` | `STRING` |
| `customer_zip_code_prefix` | `STRING` |
| `customer_city` | `STRING` |
| `customer_state` | `STRING` |

The schema and transformation results conform to:

```text
docs/analytics/staging/olist_staging_contracts.md
```

---

## 11. Temporary Validation Artifacts

The positive staging-permission test created:

```text
staging.iam_dataform_permission_test
```

The table was removed successfully after validation.

The prohibited Raw table and arbitrary dataset were not created because the corresponding operations were denied.

The GCS and metadata tests did not create or modify resources.

No customer data, credentials, tokens, or service-account keys were persisted as validation artifacts.

---

## 12. Security Properties Established

The implementation establishes the following properties:

### Separate workload responsibilities

Ingestion and analytical transformations use separate service accounts.

### Raw is read-only for transformations

Dataform can query Raw data but cannot create or modify Raw relations.

### Staging writes are explicitly bounded

Dataform can manage analytical relations only inside the approved staging dataset.

### Unrelated resources remain inaccessible

The identity cannot access Raw GCS or the BigQuery metadata control plane.

### Infrastructure provisioning remains separate

The identity cannot create arbitrary datasets or administer IAM.

### Keyless local execution

Local Dataform execution uses short-lived impersonated credentials rather than a downloaded service-account key.

### Reproducible IAM

The service account and its IAM relationships are managed through Terraform.

---

## 13. Acceptance Criteria

- [x] Dedicated Dataform transformation service account created.
- [x] Service account managed through Terraform.
- [x] Project-level BigQuery job execution granted.
- [x] BigQuery Raw read-only access granted.
- [x] BigQuery Staging read/write access granted.
- [x] Human impersonation restricted to the specific Dataform service account.
- [x] No service-account key created.
- [x] BigQuery job execution validated.
- [x] Raw read access validated.
- [x] Staging relation lifecycle validated.
- [x] Raw modification denied.
- [x] Arbitrary dataset creation denied.
- [x] Raw GCS access denied.
- [x] Metadata dataset access denied.
- [x] Dataform compilation completed under impersonated ADC.
- [x] `stg_customers` created through Dataform.
- [x] `stg_customers` assertions passed.
- [x] Raw and staging row counts reconciled.
- [x] Materialized schema validated against the staging contract.
- [x] Temporary validation artifacts removed.
- [x] Terraform configuration verified with no drift.

---

## 14. Conclusion

Mercury’s dedicated Dataform transformation identity has been implemented and experimentally validated.

The final boundary is:

```text
mercury-dataform
│
├── BigQuery project
│   └── execute jobs
│
├── BigQuery raw
│   └── read only
│
├── BigQuery staging
│   └── controlled read/write
│
├── GCS Raw
│   └── denied
│
├── BigQuery metadata
│   └── denied
│
└── infrastructure and IAM administration
    └── denied
```

The identity successfully executed the first Mercury staging transformation and its assertions without receiving permissions outside its analytical responsibility.

**Dataform transformation identity validation status: COMPLETE.**