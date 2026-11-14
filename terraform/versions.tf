terraform {
  required_version = ">= 1.6.0"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 8.11"
    }
  }

  # Estado remoto en GCS, un prefijo por ambiente:
  #   terraform init -backend-config="bucket=<bucket>" -backend-config="prefix=empleoia/staging"
  backend "gcs" {}
}

provider "google" {
  project = var.project_id
  region  = var.region
}
