# ── Alertas (Cloud Monitoring) ────────────────────────────────────────────────
# Usan métricas propias de Cloud Run y Cloud SQL: no dependen de que Prometheus raspe /metrics.
# Las reglas equivalentes para Prometheus están en monitoring/prometheus/alerts.yml.

locals {
  alert_channels = google_monitoring_notification_channel.email[*].id
  run_filter     = "resource.type = \"cloud_run_revision\" AND resource.labels.service_name = \"${google_cloud_run_v2_service.empleoia_web.name}\""
}

resource "google_monitoring_notification_channel" "email" {
  count        = var.alert_email == "" ? 0 : 1
  display_name = "EmpleoIA ${local.env}"
  type         = "email"
  labels       = { email_address = var.alert_email }
  depends_on   = [google_project_service.apis]
}

# Solo si el servicio es público: un uptime check no pasa el IAM de Cloud Run.
resource "google_monitoring_uptime_check_config" "health" {
  count        = var.public_access ? 1 : 0
  display_name = "empleoia-web-${local.env} /api/ready"
  timeout      = "10s"
  period       = "300s"

  http_check {
    path         = "/api/ready"
    port         = 443
    use_ssl      = true
    validate_ssl = true
  }

  monitored_resource {
    type = "uptime_url"
    labels = {
      project_id = var.project_id
      host       = trimprefix(google_cloud_run_v2_service.empleoia_web.uri, "https://")
    }
  }

  depends_on = [google_project_service.apis]
}

resource "google_monitoring_alert_policy" "uptime" {
  count        = var.public_access ? 1 : 0
  display_name = "EmpleoIA ${local.env}: /api/ready no responde (app, base o Redis)"
  combiner     = "OR"

  conditions {
    display_name = "Uptime check falla"
    condition_threshold {
      filter          = "metric.type = \"monitoring.googleapis.com/uptime_check/check_passed\" AND resource.type = \"uptime_url\" AND metric.labels.check_id = \"${google_monitoring_uptime_check_config.health[0].uptime_check_id}\""
      comparison      = "COMPARISON_GT"
      threshold_value = 1
      duration        = "600s"
      aggregations {
        alignment_period     = "300s"
        per_series_aligner   = "ALIGN_NEXT_OLDER"
        cross_series_reducer = "REDUCE_COUNT_FALSE"
        group_by_fields      = ["resource.label.project_id"]
      }
    }
  }

  notification_channels = local.alert_channels
  user_labels           = local.labels
}

resource "google_monitoring_alert_policy" "errors_5xx" {
  display_name = "EmpleoIA ${local.env}: más del 5 % de errores 5xx"
  combiner     = "OR"

  conditions {
    display_name = "Cloud Run 5xx / total > 5 %"
    condition_monitoring_query_language {
      query    = <<-MQL
        fetch cloud_run_revision
        | metric 'run.googleapis.com/request_count'
        | filter resource.service_name == '${google_cloud_run_v2_service.empleoia_web.name}'
        | align rate(10m)
        | every 1m
        | group_by [], [errors: sum(if(metric.response_code_class == '5xx', val(), 0)), total: sum(val())]
        | value [ratio: if(total > 0, errors / total, 0)]
        | condition ratio > 0.05
      MQL
      duration = "600s"
    }
  }

  notification_channels = local.alert_channels
  user_labels           = local.labels
}

resource "google_monitoring_alert_policy" "latency" {
  display_name = "EmpleoIA ${local.env}: p95 de latencia mayor a 5 s"
  combiner     = "OR"

  conditions {
    display_name = "Cloud Run p95 > 5 s"
    condition_threshold {
      filter          = "metric.type = \"run.googleapis.com/request_latencies\" AND ${local.run_filter}"
      comparison      = "COMPARISON_GT"
      threshold_value = 5000
      duration        = "900s"
      aggregations {
        alignment_period     = "300s"
        per_series_aligner   = "ALIGN_DELTA"
        cross_series_reducer = "REDUCE_PERCENTILE_95"
      }
    }
  }

  notification_channels = local.alert_channels
  user_labels           = local.labels
}

resource "google_monitoring_alert_policy" "sql_disk" {
  display_name = "EmpleoIA ${local.env}: disco de Cloud SQL por encima del 85 %"
  combiner     = "OR"

  conditions {
    display_name = "Cloud SQL disk utilization > 85 %"
    condition_threshold {
      filter          = "metric.type = \"cloudsql.googleapis.com/database/disk/utilization\" AND resource.type = \"cloudsql_database\" AND resource.labels.database_id = \"${var.project_id}:${google_sql_database_instance.empleoia_mysql.name}\""
      comparison      = "COMPARISON_GT"
      threshold_value = 0.85
      duration        = "900s"
      aggregations {
        alignment_period   = "300s"
        per_series_aligner = "ALIGN_MEAN"
      }
    }
  }

  notification_channels = local.alert_channels
  user_labels           = local.labels
}
