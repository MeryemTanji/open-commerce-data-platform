output "staging_dataset_id" {
  description = "BigQuery dataset used for Mercury staging models."
  value       = google_bigquery_dataset.staging.dataset_id
}

output "staging_dataset_location" {
  description = "Physical BigQuery location of the Mercury staging dataset."
  value       = google_bigquery_dataset.staging.location
}