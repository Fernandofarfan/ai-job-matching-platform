/**
 * terraform/main.tf — Infraestructura de EmpleoIA en Google Cloud Platform.
 * Un ambiente (staging o prod) por estado: Cloud Run (web, worker Celery y job de migraciones),
 * Cloud SQL MySQL con backups y PITR, Memorystore Redis, Secret Manager y bucket privado para CVs.
 */

locals {
  env    = var.environment
  prod   = var.environment == "prod"
  labels = { app = "empleoia", environment = var.environment }

  apis = [
    "artifactregistry.googleapis.com",
    "compute.googleapis.com",
    "redis.googleapis.com",
    "run.googleapis.com",
    "secretmanager.googleapis.com",
    "servicenetworking.googleapis.com",
    "sqladmin.googleapis.com",
    "storage.googleapis.com",
  ]

  redis_url = var.enable_redis ? "redis://${google_redis_instance.empleoia_redis[0].host}:${google_redis_instance.empleoia_redis[0].port}/0" : ""

  # Variables en texto plano comunes a web, worker y migraciones.
  plain_env = merge(
    {
      DB_HOST               = google_sql_database_instance.empleoia_mysql.private_ip_address
      DB_USER               = google_sql_user.empleoia_user.name
      DB_NAME               = google_sql_database.job_tracker.name
      PROFILE_STORAGE       = "mysql"
      SESSION_COOKIE_SECURE = "1"
      CV_RETENTION_DAYS     = tostring(var.cv_retention_days)
      SCRAPER_BACKEND       = var.enable_worker ? "celery" : "thread"
      LOG_LEVEL             = "INFO"
    },
    var.enable_redis ? { REDIS_URL = local.redis_url, RATELIMIT_STORAGE_URI = local.redis_url } : {},
    var.extra_env,
  )

  # Nombre de variable de entorno -> valor del secreto.
  secret_values = merge(
    {
      DB_PASSWORD       = var.db_password
      SECRET_KEY        = var.secret_key
      APP_PASSWORD      = var.app_password
      GEMINI_API_KEY    = var.gemini_api_key
      CV_ENCRYPTION_KEY = var.cv_encryption_key
    },
    var.extra_secrets,
  )
  secret_names = nonsensitive(toset(keys(local.secret_values)))

  uploads_mount = "/app/uploads"
}

resource "google_project_service" "apis" {
  for_each           = toset(local.apis)
  service            = each.key
  disable_on_destroy = false
}

# ── Artifact Registry ─────────────────────────────────────────────────────────
resource "google_artifact_registry_repository" "empleoia" {
  location      = var.region
  repository_id = "empleoia-${local.env}"
  format        = "DOCKER"
  description   = "Imágenes de EmpleoIA (${local.env})"
  labels        = local.labels

  cleanup_policies {
    id     = "conservar-ultimas-20"
    action = "KEEP"
    most_recent_versions {
      keep_count = 20
    }
  }

  depends_on = [google_project_service.apis]
}

# ── Red privada ───────────────────────────────────────────────────────────────
resource "google_compute_network" "empleoia_vpc" {
  name                    = "empleoia-vpc-${local.env}"
  auto_create_subnetworks = false
  depends_on              = [google_project_service.apis]
}

resource "google_compute_subnetwork" "empleoia_subnet" {
  name          = "empleoia-subnet-${local.env}"
  ip_cidr_range = var.subnet_cidr
  region        = var.region
  network       = google_compute_network.empleoia_vpc.id
}

# Private Services Access: necesario para la IP privada de Cloud SQL y Memorystore.
resource "google_compute_global_address" "private_services" {
  name          = "empleoia-psa-${local.env}"
  purpose       = "VPC_PEERING"
  address_type  = "INTERNAL"
  prefix_length = 16
  network       = google_compute_network.empleoia_vpc.id
}

resource "google_service_networking_connection" "private_services" {
  network                 = google_compute_network.empleoia_vpc.id
  service                 = "servicenetworking.googleapis.com"
  reserved_peering_ranges = [google_compute_global_address.private_services.name]
}

# ── Cloud SQL (MySQL 8.0) con backups diarios y point-in-time recovery ───────
resource "google_sql_database_instance" "empleoia_mysql" {
  name                = "empleoia-mysql-${local.env}"
  database_version    = "MYSQL_8_0"
  region              = var.region
  deletion_protection = local.prod

  settings {
    edition                     = "ENTERPRISE"
    tier                        = var.db_tier
    availability_type           = local.prod ? "REGIONAL" : "ZONAL"
    disk_autoresize             = true
    disk_size                   = 20
    deletion_protection_enabled = local.prod
    user_labels                 = local.labels

    backup_configuration {
      enabled                        = true
      binary_log_enabled             = true
      start_time                     = "06:00" # 03:00 en Argentina
      transaction_log_retention_days = 7
      backup_retention_settings {
        retained_backups = var.backup_retention_count
      }
    }

    maintenance_window {
      day          = 7
      hour         = 7
      update_track = "stable"
    }

    ip_configuration {
      ipv4_enabled    = false
      private_network = google_compute_network.empleoia_vpc.id
    }

    insights_config {
      query_insights_enabled = true
    }

    database_flags {
      name  = "character_set_server"
      value = "utf8mb4"
    }
  }

  depends_on = [google_service_networking_connection.private_services]
}

resource "google_sql_database" "job_tracker" {
  name      = "job_tracker"
  instance  = google_sql_database_instance.empleoia_mysql.name
  charset   = "utf8mb4"
  collation = "utf8mb4_unicode_ci"
}

resource "google_sql_user" "empleoia_user" {
  name     = "empleoia"
  instance = google_sql_database_instance.empleoia_mysql.name
  password = var.db_password
}

# ── Redis (Memorystore) ───────────────────────────────────────────────────────
resource "google_redis_instance" "empleoia_redis" {
  count              = var.enable_redis ? 1 : 0
  name               = "empleoia-redis-${local.env}"
  tier               = local.prod ? "STANDARD_HA" : "BASIC"
  memory_size_gb     = 1
  region             = var.region
  authorized_network = google_compute_network.empleoia_vpc.id
  connect_mode       = "PRIVATE_SERVICE_ACCESS"
  redis_version      = "REDIS_7_0"
  display_name       = "EmpleoIA Redis (${local.env})"
  labels             = local.labels

  depends_on = [google_service_networking_connection.private_services]
}

# ── Bucket privado para los CVs (montado en /app/uploads) ────────────────────
resource "google_storage_bucket" "uploads" {
  name                        = "${var.project_id}-empleoia-uploads-${local.env}"
  location                    = var.region
  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"
  force_destroy               = !local.prod
  labels                      = local.labels

  # Sin versionado ni soft delete: un CV borrado ("Borrar mis datos" o retención) no debe poder recuperarse.
  versioning {
    enabled = false
  }
  soft_delete_policy {
    retention_duration_seconds = 0
  }

  # Respaldo de la retención de la app por si el worker no corre.
  dynamic "lifecycle_rule" {
    for_each = var.cv_retention_days > 0 ? [1] : []
    content {
      condition {
        age = var.cv_retention_days + 1
      }
      action {
        type = "Delete"
      }
    }
  }

  depends_on = [google_project_service.apis]
}

# ── Secret Manager ────────────────────────────────────────────────────────────
resource "google_secret_manager_secret" "app" {
  for_each  = local.secret_names
  secret_id = "empleoia-${local.env}-${lower(replace(each.key, "_", "-"))}"
  labels    = local.labels
  replication {
    auto {}
  }
  depends_on = [google_project_service.apis]
}

resource "google_secret_manager_secret_version" "app" {
  for_each    = local.secret_names
  secret      = google_secret_manager_secret.app[each.key].id
  secret_data = local.secret_values[each.key]
}

# ── Cuenta de servicio de la app (mínimo privilegio) ─────────────────────────
resource "google_service_account" "app" {
  account_id   = "empleoia-app-${local.env}"
  display_name = "EmpleoIA app (${local.env})"
}

resource "google_secret_manager_secret_iam_member" "app" {
  for_each  = local.secret_names
  secret_id = google_secret_manager_secret.app[each.key].id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.app.email}"
}

resource "google_storage_bucket_iam_member" "app_uploads" {
  bucket = google_storage_bucket.uploads.name
  role   = "roles/storage.objectUser"
  member = "serviceAccount:${google_service_account.app.email}"
}

# ── Cloud Run: web ────────────────────────────────────────────────────────────
resource "google_cloud_run_v2_service" "empleoia_web" {
  name                = "empleoia-web-${local.env}"
  location            = var.region
  ingress             = "INGRESS_TRAFFIC_ALL"
  deletion_protection = local.prod
  labels              = local.labels

  template {
    service_account       = google_service_account.app.email
    execution_environment = "EXECUTION_ENVIRONMENT_GEN2"
    labels                = local.labels

    scaling {
      min_instance_count = local.prod ? 1 : 0
      max_instance_count = local.prod ? 10 : 3
    }

    # Solo el tráfico a IPs privadas (MySQL, Redis) pasa por la VPC; scrapers y Gemini salen directo.
    vpc_access {
      network_interfaces {
        network    = google_compute_network.empleoia_vpc.id
        subnetwork = google_compute_subnetwork.empleoia_subnet.id
      }
      egress = "PRIVATE_RANGES_ONLY"
    }

    volumes {
      name = "uploads"
      gcs {
        bucket = google_storage_bucket.uploads.name
      }
    }

    containers {
      image = var.image

      resources {
        limits = {
          cpu    = local.prod ? "2" : "1"
          memory = local.prod ? "2Gi" : "1Gi"
        }
      }

      dynamic "env" {
        for_each = local.plain_env
        content {
          name  = env.key
          value = env.value
        }
      }

      dynamic "env" {
        for_each = local.secret_names
        content {
          name = env.key
          value_source {
            secret_key_ref {
              secret  = google_secret_manager_secret.app[env.key].secret_id
              version = "latest"
            }
          }
        }
      }

      volume_mounts {
        name       = "uploads"
        mount_path = local.uploads_mount
      }

      ports {
        container_port = 5000
      }

      startup_probe {
        http_get {
          path = "/api/health"
        }
        initial_delay_seconds = 10
        timeout_seconds       = 5
        period_seconds        = 10
        failure_threshold     = 6
      }

      liveness_probe {
        http_get {
          path = "/api/health"
        }
        period_seconds    = 30
        failure_threshold = 3
      }
    }
  }

  depends_on = [
    google_secret_manager_secret_iam_member.app,
    google_secret_manager_secret_version.app,
    google_storage_bucket_iam_member.app_uploads,
  ]
}

# La app tiene login propio (APP_PASSWORD); public_access=false exige IAM de Cloud Run para entrar.
resource "google_cloud_run_v2_service_iam_member" "public_access" {
  count    = var.public_access ? 1 : 0
  location = var.region
  name     = google_cloud_run_v2_service.empleoia_web.name
  role     = "roles/run.invoker"
  member   = "allUsers"
}

# ── Cloud Run worker pool: Celery worker + beat (scraping, alertas, retención) ──
resource "google_cloud_run_v2_worker_pool" "celery" {
  count               = var.enable_worker ? 1 : 0
  name                = "empleoia-worker-${local.env}"
  location            = var.region
  launch_stage        = "BETA"
  deletion_protection = false
  labels              = local.labels

  scaling {
    scaling_mode          = "MANUAL"
    manual_instance_count = 1 # beat corre embebido: una sola instancia evita tareas duplicadas
  }

  template {
    service_account = google_service_account.app.email
    labels          = local.labels

    vpc_access {
      network_interfaces {
        network    = google_compute_network.empleoia_vpc.id
        subnetwork = google_compute_subnetwork.empleoia_subnet.id
      }
      egress = "PRIVATE_RANGES_ONLY"
    }

    volumes {
      name = "uploads"
      gcs {
        bucket = google_storage_bucket.uploads.name
      }
    }

    containers {
      image   = var.image
      command = ["celery"]
      args = [
        "-A", "celery_app", "worker", "--beat",
        "--queues", "scraping,ai_processing,notifications",
        "--concurrency", "2", "--loglevel", "info",
      ]

      resources {
        limits = {
          cpu    = "1"
          memory = "2Gi"
        }
      }

      dynamic "env" {
        for_each = local.plain_env
        content {
          name  = env.key
          value = env.value
        }
      }

      dynamic "env" {
        for_each = local.secret_names
        content {
          name = env.key
          value_source {
            secret_key_ref {
              secret  = google_secret_manager_secret.app[env.key].secret_id
              version = "latest"
            }
          }
        }
      }

      volume_mounts {
        name       = "uploads"
        mount_path = local.uploads_mount
      }
    }
  }

  lifecycle {
    precondition {
      condition     = var.enable_redis
      error_message = "enable_worker requiere enable_redis: Celery usa Redis como broker."
    }
  }

  depends_on = [
    google_secret_manager_secret_iam_member.app,
    google_secret_manager_secret_version.app,
    google_storage_bucket_iam_member.app_uploads,
  ]
}

# ── Cloud Run job: migraciones de Alembic (el deploy lo ejecuta antes de actualizar la web) ──
resource "google_cloud_run_v2_job" "migrate" {
  name                = "empleoia-migrate-${local.env}"
  location            = var.region
  deletion_protection = false
  labels              = local.labels

  template {
    task_count = 1
    template {
      service_account = google_service_account.app.email
      max_retries     = 0
      timeout         = "600s"

      vpc_access {
        network_interfaces {
          network    = google_compute_network.empleoia_vpc.id
          subnetwork = google_compute_subnetwork.empleoia_subnet.id
        }
        egress = "PRIVATE_RANGES_ONLY"
      }

      containers {
        image   = var.image
        command = ["alembic"]
        args    = ["upgrade", "head"]

        dynamic "env" {
          for_each = { for k, v in local.plain_env : k => v if startswith(k, "DB_") }
          content {
            name  = env.key
            value = env.value
          }
        }

        env {
          name = "DB_PASSWORD"
          value_source {
            secret_key_ref {
              secret  = google_secret_manager_secret.app["DB_PASSWORD"].secret_id
              version = "latest"
            }
          }
        }
      }
    }
  }

  depends_on = [
    google_secret_manager_secret_iam_member.app,
    google_secret_manager_secret_version.app,
  ]
}
