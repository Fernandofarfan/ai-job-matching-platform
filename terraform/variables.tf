/**
 * terraform/variables.tf — Variables de configuración de EmpleoIA en GCP
 */

variable "project_id" {
  description = "ID del proyecto de Google Cloud"
  type        = string
}

variable "region" {
  description = "Región de GCP donde se despliegan los recursos"
  type        = string
  default     = "southamerica-east1"  # São Paulo — más cercano a Argentina
}

variable "environment" {
  description = "Ambiente de despliegue: dev, staging, prod"
  type        = string
  default     = "dev"

  validation {
    condition     = contains(["dev", "staging", "prod"], var.environment)
    error_message = "environment debe ser dev, staging o prod"
  }
}

variable "db_password" {
  description = "Contraseña para el usuario de MySQL"
  type        = string
  sensitive   = true
}

variable "gemini_api_key" {
  description = "API Key de Google Gemini"
  type        = string
  sensitive   = true
}

variable "enable_redis" {
  description = "Si se debe crear una instancia de Redis (Memorystore). Desactivar para ahorrar costos en dev."
  type        = bool
  default     = true
}

variable "smtp_user" {
  description = "Email SMTP para notificaciones"
  type        = string
  default     = ""
}

variable "smtp_password" {
  description = "Contraseña SMTP para notificaciones"
  type        = string
  sensitive   = true
  default     = ""
}
