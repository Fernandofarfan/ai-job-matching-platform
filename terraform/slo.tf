# ── SLOs y presupuesto de errores (Cloud Monitoring) ──────────────────────────
# Disponibilidad: pedidos sin 5xx. Latencia: pedidos que tardan hasta slo_latency_ms.
# Ambos sobre 28 días. Las alertas avisan por velocidad de consumo del presupuesto (burn rate) con dos ventanas,
# como recomienda el SRE Workbook: rápido (14,4× en 1 h y 5 min, se gasta el 2 % del presupuesto en 1 h) y
# lento (6× en 6 h y 30 min, el 5 % en 6 h). La ventana corta hace que la alerta se apague apenas se corrige.
# Las reglas equivalentes para Prometheus están en monitoring/prometheus/alerts.yml.

locals {
  slo_request_filter = "metric.type = \"run.googleapis.com/request_count\" AND ${local.run_filter}"
  slo_burn_alerts = {
    fast = { lookback = "3600s", short = "300s", threshold = 14.4, label = "rápido (2 % del presupuesto en 1 h)" }
    slow = { lookback = "21600s", short = "1800s", threshold = 6, label = "lento (5 % del presupuesto en 6 h)" }
  }
  slos = {
    availability = { slo = google_monitoring_slo.availability, label = "disponibilidad" }
    latency      = { slo = google_monitoring_slo.latency, label = "latencia" }
  }
}

resource "google_monitoring_custom_service" "web" {
  service_id   = "empleoia-web-${local.env}"
  display_name = "EmpleoIA web (${local.env})"
  user_labels  = local.labels
  depends_on   = [google_project_service.apis]
}

resource "google_monitoring_slo" "availability" {
  service             = google_monitoring_custom_service.web.service_id
  slo_id              = "availability"
  display_name        = "${format("%g", var.slo_availability_goal * 100)} % de pedidos sin 5xx (28 días)"
  goal                = var.slo_availability_goal
  rolling_period_days = 28
  user_labels         = local.labels

  request_based_sli {
    good_total_ratio {
      total_service_filter = local.slo_request_filter
      bad_service_filter   = "${local.slo_request_filter} AND metric.labels.response_code_class = \"5xx\""
    }
  }
}

resource "google_monitoring_slo" "latency" {
  service             = google_monitoring_custom_service.web.service_id
  slo_id              = "latency"
  display_name        = "${format("%g", var.slo_latency_goal * 100)} % de pedidos en ${var.slo_latency_ms} ms o menos (28 días)"
  goal                = var.slo_latency_goal
  rolling_period_days = 28
  user_labels         = local.labels

  request_based_sli {
    distribution_cut {
      distribution_filter = "metric.type = \"run.googleapis.com/request_latencies\" AND ${local.run_filter}"
      range {
        min = 0
        max = var.slo_latency_ms
      }
    }
  }
}

resource "google_monitoring_alert_policy" "slo_burn" {
  for_each = { for pair in setproduct(keys(local.slos), keys(local.slo_burn_alerts)) : "${pair[0]}-${pair[1]}" => {
    slo   = local.slos[pair[0]].slo
    label = local.slos[pair[0]].label
    burn  = local.slo_burn_alerts[pair[1]]
  } }

  display_name = "EmpleoIA ${local.env}: SLO de ${each.value.label}, consumo ${each.value.burn.label}"
  combiner     = "AND"

  dynamic "conditions" {
    for_each = [each.value.burn.lookback, each.value.burn.short]
    content {
      display_name = "Burn rate > ${each.value.burn.threshold} en ${conditions.value}"
      condition_threshold {
        filter          = "select_slo_burn_rate(\"${each.value.slo.name}\", \"${conditions.value}\")"
        comparison      = "COMPARISON_GT"
        threshold_value = each.value.burn.threshold
        duration        = "0s"
      }
    }
  }

  documentation {
    content   = "Se está gastando el presupuesto de errores del SLO \"${each.value.slo.display_name}\". Pasos en docs/runbook.md, \"Errores 5xx o latencia alta\"."
    mime_type = "text/markdown"
  }

  notification_channels = local.alert_channels
  user_labels           = local.labels
}
