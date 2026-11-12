#!/usr/bin/env bash
# Verifica que los backups de Cloud SQL se pueden restaurar, sin tocar la instancia de producción:
#   1. clona la instancia a un punto en el tiempo (prueba PITR) en una instancia temporal,
#   2. restaura sobre esa copia el último backup automático exitoso,
#   3. exporta la base a GCS y comprueba que estén las tablas esperadas,
#   4. borra la instancia temporal y el export (también si algo falla).
# Uso: PROJECT_ID=... INSTANCE=empleoia-mysql-staging BUCKET=<bucket> scripts/verify_backup_restore.sh
# Opcionales: DATABASE (job_tracker), PITR_MINUTES_AGO (10), EXPECTED_TABLES ("applications user_profiles alembic_version").
set -euo pipefail

: "${PROJECT_ID:?Falta PROJECT_ID}"
: "${INSTANCE:?Falta INSTANCE (instancia de Cloud SQL a verificar)}"
: "${BUCKET:?Falta BUCKET (bucket GCS donde exportar la copia)}"
DATABASE="${DATABASE:-job_tracker}"
PITR_MINUTES_AGO="${PITR_MINUTES_AGO:-10}"
EXPECTED_TABLES="${EXPECTED_TABLES:-applications user_profiles alembic_version}"
STAMP="$(date -u +%Y%m%d%H%M%S)"
TEMP_INSTANCE="${INSTANCE}-restore-${STAMP}"
EXPORT_URI="gs://${BUCKET}/restore-checks/${TEMP_INSTANCE}.sql.gz"
GCLOUD=(gcloud --project "$PROJECT_ID" --quiet)

cleanup() {
  echo "Limpiando ${TEMP_INSTANCE} y ${EXPORT_URI}"
  "${GCLOUD[@]}" sql instances delete "$TEMP_INSTANCE" >/dev/null 2>&1 || true
  gcloud storage rm "$EXPORT_URI" >/dev/null 2>&1 || true
}
trap cleanup EXIT

PITR_TIME="$(date -u -d "-${PITR_MINUTES_AGO} minutes" +%Y-%m-%dT%H:%M:%SZ)"
echo "1/4 Clonando ${INSTANCE} al ${PITR_TIME} (PITR) en ${TEMP_INSTANCE}"
"${GCLOUD[@]}" sql instances clone "$INSTANCE" "$TEMP_INSTANCE" --point-in-time="$PITR_TIME"

BACKUP_ID="$("${GCLOUD[@]}" sql backups list --instance="$INSTANCE" \
  --filter="status=SUCCESSFUL AND type=AUTOMATED" --sort-by=~windowStartTime --limit=1 --format='value(id)')"
if [[ -z "$BACKUP_ID" ]]; then
  echo "ERROR: ${INSTANCE} no tiene backups automáticos exitosos" >&2
  exit 1
fi
echo "2/4 Restaurando el backup ${BACKUP_ID} sobre ${TEMP_INSTANCE}"
"${GCLOUD[@]}" sql backups restore "$BACKUP_ID" --backup-instance="$INSTANCE" --restore-instance="$TEMP_INSTANCE"

echo "3/4 Exportando ${DATABASE} a ${EXPORT_URI}"
SA="$("${GCLOUD[@]}" sql instances describe "$TEMP_INSTANCE" --format='value(serviceAccountEmailAddress)')"
gcloud storage buckets add-iam-policy-binding "gs://${BUCKET}" --member="serviceAccount:${SA}" \
  --role=roles/storage.objectAdmin >/dev/null
"${GCLOUD[@]}" sql export sql "$TEMP_INSTANCE" "$EXPORT_URI" --database="$DATABASE"

echo "4/4 Comprobando tablas: ${EXPECTED_TABLES}"
DUMP_TABLES="$(gcloud storage cat "$EXPORT_URI" | gunzip | grep -oE 'CREATE TABLE `[^`]+`' | sort -u)"
missing=0
for table in $EXPECTED_TABLES; do
  if grep -q "\`${table}\`" <<<"$DUMP_TABLES"; then
    echo "  ok: ${table}"
  else
    echo "  FALTA: ${table}" >&2
    missing=1
  fi
done
if [[ "$missing" -ne 0 ]]; then
  echo "ERROR: la copia restaurada no tiene todas las tablas esperadas" >&2
  exit 1
fi
echo "OK: el backup ${BACKUP_ID} y la recuperación al ${PITR_TIME} de ${INSTANCE} se restauran bien"
