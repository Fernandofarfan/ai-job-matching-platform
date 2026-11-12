# terraform test: valida el plan con un provider simulado (no necesita credenciales de GCP).

mock_provider "google" {
  mock_resource "google_compute_network" {
    defaults = {
      id = "projects/demo/global/networks/empleoia-vpc"
    }
  }
  mock_resource "google_secret_manager_secret" {
    defaults = {
      id = "projects/demo/secrets/demo"
    }
  }
}

variables {
  project_id        = "demo"
  image             = "southamerica-east1-docker.pkg.dev/demo/empleoia-staging/web:test"
  db_password       = "0123456789abcdef0123"
  gemini_api_key    = "test"
  admin_email       = "admin@example.com"
  secret_key        = "0123456789abcdef0123456789abcdef"
  cv_encryption_key = "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA="
}

run "staging" {
  command = plan

  variables {
    environment       = "staging"
    cv_retention_days = 30
  }

  assert {
    condition     = google_sql_database_instance.empleoia_mysql.settings[0].backup_configuration[0].enabled && google_sql_database_instance.empleoia_mysql.settings[0].backup_configuration[0].binary_log_enabled
    error_message = "Cloud SQL debe tener backups y point-in-time recovery"
  }

  assert {
    condition     = google_sql_database_instance.empleoia_mysql.settings[0].ip_configuration[0].ipv4_enabled == false
    error_message = "Cloud SQL no debe tener IP pública"
  }

  assert {
    condition     = google_cloud_run_v2_service.empleoia_web.template[0].vpc_access[0].egress == "PRIVATE_RANGES_ONLY"
    error_message = "Con egress ALL_TRAFFIC y sin Cloud NAT, scrapers y Gemini no tendrían salida a internet"
  }

  assert {
    condition     = google_storage_bucket.uploads.public_access_prevention == "enforced" && google_storage_bucket.uploads.versioning[0].enabled == false
    error_message = "El bucket de CVs debe ser privado y sin versionado (los CVs borrados no deben quedar)"
  }

  assert {
    condition     = google_storage_bucket.uploads.soft_delete_policy[0].retention_duration_seconds == 0
    error_message = "Sin soft delete: un CV borrado no debe poder restaurarse"
  }

  assert {
    condition     = one(google_storage_bucket.uploads.lifecycle_rule[0].condition).age == 31
    error_message = "El bucket debe borrar CVs pasada la retención"
  }

  assert {
    condition     = length(google_secret_manager_secret_iam_member.app) == 4
    error_message = "La cuenta de servicio debe poder leer cada secreto"
  }

  assert {
    condition = (
      contains([for v in google_cloud_run_v2_service.empleoia_web.template[0].volumes : v.name], "results") &&
      contains([for v in google_cloud_run_v2_worker_pool.celery[0].template[0].volumes : v.name], "results")
    )
    error_message = "Web y worker deben compartir results/: el worker escribe los CSV que la web lista"
  }

  assert {
    condition     = google_cloud_run_v2_worker_pool.celery[0].scaling[0].manual_instance_count == 1
    error_message = "El worker con beat embebido debe tener una sola instancia"
  }

  assert {
    condition     = google_sql_database_instance.empleoia_mysql.deletion_protection == false
    error_message = "staging se puede destruir"
  }
}

run "prod" {
  command = plan

  variables {
    environment = "prod"
  }

  assert {
    condition     = google_sql_database_instance.empleoia_mysql.deletion_protection && google_sql_database_instance.empleoia_mysql.settings[0].availability_type == "REGIONAL"
    error_message = "prod debe tener Cloud SQL regional y protegido contra borrado"
  }

  assert {
    condition     = length(google_storage_bucket.uploads.lifecycle_rule) == 0
    error_message = "Sin retención no se borran CVs por antigüedad"
  }
}

run "alerts" {
  command = plan

  variables {
    environment = "staging"
    alert_email = "alertas@example.com"
  }

  assert {
    condition     = length(google_monitoring_notification_channel.email) == 1 && length(google_monitoring_uptime_check_config.health) == 1
    error_message = "Con alert_email y acceso público debe haber canal de email y uptime check de /api/health"
  }

  assert {
    condition     = google_monitoring_uptime_check_config.health[0].http_check[0].path == "/api/health"
    error_message = "El uptime check debe pegarle a /api/health"
  }
}

run "alerts_private_without_email" {
  command = plan

  variables {
    environment   = "staging"
    public_access = false
  }

  assert {
    condition     = length(google_monitoring_notification_channel.email) == 0 && length(google_monitoring_uptime_check_config.health) == 0 && length(google_monitoring_alert_policy.uptime) == 0
    error_message = "Sin email no se crea canal, y con el servicio privado no hay uptime check"
  }
}

run "worker_requires_redis" {
  command = plan

  variables {
    enable_redis = false
  }

  expect_failures = [google_cloud_run_v2_worker_pool.celery]
}

run "rejects_invalid_admin_email" {
  command = plan

  variables {
    admin_email = "no-es-email"
  }

  expect_failures = [var.admin_email]
}
