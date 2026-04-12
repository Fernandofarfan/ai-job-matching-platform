/**
 * terraform/main.tf — Infraestructura de EmpleoIA en Google Cloud Platform
 * Despliega: Cloud Run (Flask + Celery), Cloud SQL (MySQL), Redis (Memorystore)
 */

terraform {
  required_version = ">= 1.6.0"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.0"
    }
  }

  # Backend remoto (descomentá para equipos)
  # backend "gcs" {
  #   bucket = "empleoia-tfstate"
  #   prefix = "terraform/state"
  # }
}

provider "google" {
  project = var.project_id
  region  = var.region
}

# ── APIs a habilitar ──────────────────────────────────────────────────────────
locals {
  apis = [
    "run.googleapis.com",
    "sqladmin.googleapis.com",
    "redis.googleapis.com",
    "secretmanager.googleapis.com",
    "artifactregistry.googleapis.com",
    "cloudbuild.googleapis.com",
  ]
}

resource "google_project_service" "apis" {
  for_each = toset(local.apis)
  project  = var.project_id
  service  = each.key
  disable_on_destroy = false
}

# ── Artifact Registry (Docker images) ────────────────────────────────────────
resource "google_artifact_registry_repository" "empleoia" {
  location      = var.region
  repository_id = "empleoia"
  format        = "DOCKER"
  description   = "EmpleoIA container images"
  depends_on    = [google_project_service.apis]
}

# ── VPC Network ───────────────────────────────────────────────────────────────
resource "google_compute_network" "empleoia_vpc" {
  name                    = "empleoia-vpc"
  auto_create_subnetworks = false
}

resource "google_compute_subnetwork" "empleoia_subnet" {
  name          = "empleoia-subnet"
  ip_cidr_range = "10.0.0.0/24"
  region        = var.region
  network       = google_compute_network.empleoia_vpc.id
}

# ── Cloud SQL (MySQL 8.0) ─────────────────────────────────────────────────────
resource "google_sql_database_instance" "empleoia_mysql" {
  name             = "empleoia-mysql-${var.environment}"
  database_version = "MYSQL_8_0"
  region           = var.region
  deletion_protection = var.environment == "prod" ? true : false

  settings {
    tier              = var.environment == "prod" ? "db-n1-standard-2" : "db-f1-micro"
    availability_type = var.environment == "prod" ? "REGIONAL" : "ZONAL"
    disk_autoresize   = true
    disk_size         = 20

    backup_configuration {
      enabled            = true
      binary_log_enabled = true
      start_time         = "03:00"
      backup_retention_settings {
        retained_backups = 7
      }
    }

    ip_configuration {
      ipv4_enabled    = false
      private_network = google_compute_network.empleoia_vpc.id
      require_ssl     = false
    }

    database_flags {
      name  = "character_set_server"
      value = "utf8mb4"
    }
  }

  depends_on = [google_project_service.apis]
}

resource "google_sql_database" "job_tracker" {
  name     = "job_tracker"
  instance = google_sql_database_instance.empleoia_mysql.name
  charset  = "utf8mb4"
}

resource "google_sql_user" "empleoia_user" {
  name     = "empleoia"
  instance = google_sql_database_instance.empleoia_mysql.name
  password = var.db_password
}

# ── Redis (Memorystore) ───────────────────────────────────────────────────────
resource "google_redis_instance" "empleoia_redis" {
  count          = var.enable_redis ? 1 : 0
  name           = "empleoia-redis-${var.environment}"
  tier           = "BASIC"
  memory_size_gb = 1
  region         = var.region

  authorized_network = google_compute_network.empleoia_vpc.id
  connect_mode       = "PRIVATE_SERVICE_ACCESS"

  redis_version     = "REDIS_7_0"
  display_name      = "EmpleoIA Redis Cache"

  labels = {
    app         = "empleoia"
    environment = var.environment
  }

  depends_on = [google_project_service.apis]
}

# ── Secret Manager ────────────────────────────────────────────────────────────
resource "google_secret_manager_secret" "gemini_api_key" {
  secret_id = "empleoia-gemini-api-key"
  replication { automatic {} }
  depends_on = [google_project_service.apis]
}

resource "google_secret_manager_secret_version" "gemini_api_key_v1" {
  secret      = google_secret_manager_secret.gemini_api_key.id
  secret_data = var.gemini_api_key
}

resource "google_secret_manager_secret" "db_password" {
  secret_id = "empleoia-db-password"
  replication { automatic {} }
}

resource "google_secret_manager_secret_version" "db_password_v1" {
  secret      = google_secret_manager_secret.db_password.id
  secret_data = var.db_password
}

# ── Cloud Run (Flask Web App) ─────────────────────────────────────────────────
locals {
  redis_url = var.enable_redis && length(google_redis_instance.empleoia_redis) > 0 ? \
    "redis://${google_redis_instance.empleoia_redis[0].host}:${google_redis_instance.empleoia_redis[0].port}/0" : \
    "redis://localhost:6379/0"
}

resource "google_cloud_run_v2_service" "empleoia_web" {
  name     = "empleoia-web-${var.environment}"
  location = var.region

  template {
    scaling {
      min_instance_count = var.environment == "prod" ? 1 : 0
      max_instance_count = var.environment == "prod" ? 10 : 3
    }

    vpc_access {
      network_interfaces {
        network    = google_compute_network.empleoia_vpc.id
        subnetwork = google_compute_subnetwork.empleoia_subnet.id
      }
      egress = "ALL_TRAFFIC"
    }

    containers {
      image = "${var.region}-docker.pkg.dev/${var.project_id}/empleoia/web:latest"

      resources {
        limits = {
          cpu    = var.environment == "prod" ? "2" : "1"
          memory = var.environment == "prod" ? "2Gi" : "512Mi"
        }
      }

      env {
        name  = "DB_HOST"
        value = google_sql_database_instance.empleoia_mysql.private_ip_address
      }
      env {
        name  = "DB_USER"
        value = google_sql_user.empleoia_user.name
      }
      env {
        name = "DB_PASSWORD"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.db_password.secret_id
            version = "latest"
          }
        }
      }
      env {
        name  = "DB_NAME"
        value = "job_tracker"
      }
      env {
        name  = "REDIS_URL"
        value = local.redis_url
      }
      env {
        name = "GEMINI_API_KEY"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.gemini_api_key.secret_id
            version = "latest"
          }
        }
      }

      ports { container_port = 5000 }

      startup_probe {
        http_get { path = "/" }
        initial_delay_seconds = 15
        timeout_seconds       = 5
        period_seconds        = 10
        failure_threshold     = 5
      }

      liveness_probe {
        http_get { path = "/" }
        period_seconds    = 30
        failure_threshold = 3
      }
    }
  }

  depends_on = [
    google_sql_database_instance.empleoia_mysql,
    google_project_service.apis,
  ]
}

# Allow unauthenticated access (public web app)
resource "google_cloud_run_v2_service_iam_member" "public_access" {
  project  = var.project_id
  location = var.region
  name     = google_cloud_run_v2_service.empleoia_web.name
  role     = "roles/run.invoker"
  member   = "allUsers"
}

# ── Outputs ───────────────────────────────────────────────────────────────────
output "web_url" {
  description = "URL pública de EmpleoIA"
  value       = google_cloud_run_v2_service.empleoia_web.uri
}

output "mysql_private_ip" {
  description = "IP privada de MySQL"
  value       = google_sql_database_instance.empleoia_mysql.private_ip_address
}

output "redis_host" {
  description = "Host de Redis"
  value       = var.enable_redis ? google_redis_instance.empleoia_redis[0].host : "N/A"
  sensitive   = false
}

output "docker_registry" {
  description = "URL del Artifact Registry"
  value       = "${var.region}-docker.pkg.dev/${var.project_id}/empleoia"
}
