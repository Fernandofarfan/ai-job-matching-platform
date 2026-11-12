# Valores no secretos de producción. Los secretos van como TF_VAR_* (ver README).
environment            = "prod"
subnet_cidr            = "10.20.0.0/24"
db_tier                = "db-custom-2-7680"
backup_retention_count = 30
cv_retention_days      = 180
