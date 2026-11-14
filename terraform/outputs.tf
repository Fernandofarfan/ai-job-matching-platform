output "web_url" {
  description = "URL de EmpleoIA"
  value       = google_cloud_run_v2_service.empleoia_web.uri
}

output "docker_registry" {
  description = "Repositorio de Artifact Registry para las imágenes"
  value       = "${var.region}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.empleoia.repository_id}"
}

output "migrate_job" {
  description = "Job de Cloud Run que corre `alembic upgrade head`"
  value       = google_cloud_run_v2_job.migrate.name
}

output "mysql_private_ip" {
  description = "IP privada de Cloud SQL"
  value       = google_sql_database_instance.empleoia_mysql.private_ip_address
}

output "redis_host" {
  description = "Host de Memorystore"
  value       = var.enable_redis ? google_redis_instance.empleoia_redis[0].host : null
}

output "uploads_bucket" {
  description = "Bucket privado montado en /app/uploads"
  value       = google_storage_bucket.uploads.name
}

output "results_bucket" {
  description = "Bucket privado montado en /app/results (CSV de búsquedas compartidos entre worker y web)"
  value       = google_storage_bucket.results.name
}

output "public_access" {
  description = "true si la web acepta tráfico sin IAM de Google"
  value       = var.public_access
}
