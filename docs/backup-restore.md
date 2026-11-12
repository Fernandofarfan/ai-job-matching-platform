# Runbook: verificar y restaurar backups de Cloud SQL

Terraform deja Cloud SQL con backups automáticos diarios y recuperación a un punto en el tiempo (PITR) de los últimos 7 días (`backup_retention_count`, `terraform/main.tf`). Un backup que nunca se restauró no está probado: este runbook lo verifica sin tocar la instancia real.

## Verificación automática (mensual)

`.github/workflows/backup-restore-check.yml` corre el día 1 de cada mes y a mano desde *Actions → Run workflow*. Ejecuta `scripts/verify_backup_restore.sh`, que:

1. Clona la instancia al estado de hace `PITR_MINUTES_AGO` minutos (por defecto, 10) en `<instancia>-restore-<fecha>` (prueba PITR).
2. Restaura sobre esa copia el último backup automático exitoso (prueba de backup).
3. Exporta la base a `gs://<BUCKET>/restore-checks/` y comprueba que estén `applications`, `user_profiles` y `alembic_version`.
4. Borra la instancia temporal y el export, aunque algún paso falle.

### Qué hay que configurar

| Dónde | Nombre | Valor |
|---|---|---|
| Variable del repo | `GCP_DEPLOY_ENABLED` | `true` (igual que el deploy) |
| Variables del Environment | `GCP_PROJECT_ID`, `GCP_WORKLOAD_IDENTITY_PROVIDER`, `GCP_DEPLOY_SA` | Las mismas del deploy |
| Variable del Environment | `BACKUP_CHECK_BUCKET` | Bucket privado para el export temporal (puede ser el de resultados) |

La cuenta de servicio necesita `roles/cloudsql.admin` (clonar, restaurar, exportar y borrar) y `roles/storage.admin` sobre el bucket (dar acceso a la cuenta de la instancia temporal y borrar el export). La instancia temporal se factura mientras existe, normalmente menos de una hora.

## Verificación a mano

```bash
gcloud auth login
PROJECT_ID=mi-proyecto INSTANCE=empleoia-mysql-staging BUCKET=mi-bucket scripts/verify_backup_restore.sh
```

## Restaurar de verdad (incidente)

1. Elegí el backup o el momento: `gcloud sql backups list --instance=empleoia-mysql-prod`.
2. Restaurá en una instancia nueva y validá los datos antes de tocar prod:
   `gcloud sql instances clone empleoia-mysql-prod empleoia-mysql-prod-recover --point-in-time=2026-11-10T12:00:00Z`.
3. Si los datos están bien, restaurá el backup sobre prod (`gcloud sql backups restore <ID> --restore-instance=empleoia-mysql-prod`) o apuntá `DB_HOST` a la instancia recuperada y alineá Terraform.
4. Corré `python -m alembic upgrade head` y revisá `/api/health`.
5. Los perfiles siguen cifrados con `CV_ENCRYPTION_KEY`: restaurá también la misma clave desde Secret Manager.
