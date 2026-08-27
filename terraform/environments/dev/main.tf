resource "google_bigquery_dataset" "staging" {
  project    = var.project_id
  dataset_id = "staging"
  location   = var.region

  description = "Mercury standardized staging layer managed by Dataform."

  delete_contents_on_destroy = false

  labels = {
    platform    = "mercury"
    environment = "dev"
    layer       = "staging"
    managed_by  = "terraform"
  }
}

resource "google_service_account" "dataform" {
  project      = var.project_id
  account_id   = "mercury-dataform"
  display_name = "Mercury Dataform"
  description  = "Dedicated least-privilege service account for Mercury analytical transformations."
}