terraform {
  required_version = ">= 1.5.0"

  backend "gcs" {
    bucket = "mercury-data-platform-dev-terraform-state-01"
    prefix = "environments/dev"
  }

  required_providers {
    google = {
      source = "hashicorp/google"
    }
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
}