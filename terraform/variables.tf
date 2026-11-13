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

variable "secret_key" {
  description = "SECRET_KEY de la app (firma de cookies de sesión). Generá con: python -c \"import secrets; print(secrets.token_hex(32))\""
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
