/**
 * terraform/variables.tf — Variables de configuración de EmpleoIA en GCP.
 * Los valores no secretos van en envs/<ambiente>.tfvars; los secretos, como TF_VAR_* (nunca en el repo).
 */

variable "project_id" {
  description = "ID del proyecto de Google Cloud"
  type        = string
}

variable "region" {
  description = "Región de GCP donde se despliegan los recursos"
  type        = string
  default     = "southamerica-east1" # São Paulo, la más cercana a Argentina
}

variable "environment" {
  description = "Ambiente de despliegue: dev, staging o prod"
  type        = string
  default     = "staging"

  validation {
    condition     = contains(["dev", "staging", "prod"], var.environment)
    error_message = "environment debe ser dev, staging o prod."
  }
}

variable "image" {
  description = "Imagen completa a desplegar (p. ej. <región>-docker.pkg.dev/<proyecto>/empleoia-staging/web:<sha>)"
  type        = string
}

variable "subnet_cidr" {
  description = "Rango de la subred de Cloud Run (distinto por ambiente si comparten proyecto)"
  type        = string
  default     = "10.0.0.0/24"
}

variable "db_tier" {
  description = "Tipo de máquina de Cloud SQL"
  type        = string
  default     = "db-f1-micro"
}

variable "backup_retention_count" {
  description = "Cantidad de backups diarios de Cloud SQL que se conservan"
  type        = number
  default     = 7

  validation {
    condition     = var.backup_retention_count >= 1 && var.backup_retention_count <= 365
    error_message = "backup_retention_count debe estar entre 1 y 365."
  }
}

variable "enable_redis" {
  description = "Crear Memorystore Redis (rate limit compartido, caché y broker de Celery)"
  type        = bool
  default     = true
}

variable "enable_worker" {
  description = "Crear el worker de Celery (scraping, alertas y retención de CVs); requiere enable_redis"
  type        = bool
  default     = true
}

variable "public_access" {
  description = "Permitir el acceso sin IAM de Google (la app igual pide login con cuenta)"
  type        = bool
  default     = true
}

variable "cv_retention_days" {
  description = "Días que se conservan los CVs subidos; 0 = sin borrado automático"
  type        = number
  default     = 0

  validation {
    condition     = var.cv_retention_days >= 0
    error_message = "cv_retention_days no puede ser negativo."
  }
}

variable "extra_env" {
  description = "Variables de entorno adicionales no secretas (MATCHING_BACKEND, SMTP_HOST, APP_BASE_URL, ...)"
  type        = map(string)
  default     = {}
}

# ── Secretos (pasarlos como TF_VAR_*) ─────────────────────────────────────────

variable "db_password" {
  description = "Contraseña del usuario de MySQL"
  type        = string
  sensitive   = true

  validation {
    condition     = length(var.db_password) >= 16
    error_message = "db_password debe tener al menos 16 caracteres."
  }
}

variable "gemini_api_key" {
  description = "API key de Google Gemini"
  type        = string
  sensitive   = true
}

variable "admin_email" {
  description = "Email de la primera cuenta (ADMIN_EMAIL). Obligatorio porque el servicio es público: nadie más puede reclamar la instancia."
  type        = string

  validation {
    condition     = can(regex("^[^@\\s]+@[^@\\s]+\\.[^@\\s]+$", var.admin_email))
    error_message = "admin_email debe ser un email válido."
  }
}

variable "secret_key" {
  description = "SECRET_KEY de Flask compartida por todas las instancias (python -c \"import secrets; print(secrets.token_hex(32))\")"
  type        = string
  sensitive   = true

  validation {
    condition     = length(var.secret_key) >= 32
    error_message = "secret_key debe tener al menos 32 caracteres."
  }
}

variable "cv_encryption_key" {
  description = "Clave Fernet para cifrar los CVs (python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\")"
  type        = string
  sensitive   = true

  validation {
    condition     = length(var.cv_encryption_key) == 44
    error_message = "cv_encryption_key debe ser una clave Fernet (44 caracteres base64)."
  }
}

variable "extra_secrets" {
  description = "Secretos adicionales como variables de entorno (TELEGRAM_BOT_TOKEN, SMTP_PASSWORD, SENTRY_DSN, ...)"
  type        = map(string)
  sensitive   = true
  default     = {}
}
