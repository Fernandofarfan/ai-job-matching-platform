# Valores no secretos de staging. Los secretos van como TF_VAR_* (ver README).
environment            = "staging"
subnet_cidr            = "10.10.0.0/24"
db_tier                = "db-f1-micro"
backup_retention_count = 7
cv_retention_days      = 30
# alert_email          = "alertas@example.com"
