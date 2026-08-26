variable "project_id" {
  description = "Google Cloud project hosting the Mercury development environment."
  type        = string
  default     = "mercury-data-platform-dev"
}

variable "region" {
  description = "Primary Google Cloud region for Mercury development resources."
  type        = string
  default     = "europe-west4"
}