"""scripts/verify_backup_restore.sh con gcloud falso: orden de pasos, chequeo de tablas y limpieza."""
import gzip
import os
import shutil
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parent.parent / 'scripts' / 'verify_backup_restore.sh'

FAKE_GCLOUD = r'''#!/usr/bin/env bash
echo "$*" >> "$CALLS"
case "$*" in
  *"backups list"*) echo "${BACKUP_ID-1700000000000}" ;;
  *"instances describe"*) echo "sa@example.iam.gserviceaccount.com" ;;
  *"storage cat"*) cat "$DUMP" ;;
  *"get-iam-policy"*) echo "${IAM_POLICY-}" ;;
esac
exit 0
'''


def _run(tmp_path, tables, **env):
    """Corre el script con un gcloud falso que registra cada llamada."""
    bindir = tmp_path / 'bin'
    bindir.mkdir()
    gcloud = bindir / 'gcloud'
    gcloud.write_text(FAKE_GCLOUD)
    gcloud.chmod(0o755)
    dump = tmp_path / 'dump.sql.gz'
    dump.write_bytes(gzip.compress(''.join(f'CREATE TABLE `{t}` (id int);\n' for t in tables).encode()))
    calls = tmp_path / 'calls.log'
    full_env = {
        **os.environ, 'PATH': f'{bindir}:{os.environ["PATH"]}', 'CALLS': str(calls), 'DUMP': str(dump),
        'PROJECT_ID': 'demo', 'INSTANCE': 'empleoia-mysql-staging', 'BUCKET': 'demo-bucket', **env,
    }
    proc = subprocess.run(['bash', str(SCRIPT)], env=full_env, capture_output=True, text=True, timeout=30)
    return proc, calls.read_text().splitlines() if calls.exists() else []


pytestmark = pytest.mark.skipif(not shutil.which('bash') or not shutil.which('gunzip'), reason='requiere bash y gunzip')


def test_restore_check_passes_and_cleans_up(tmp_path):
    """Clona (PITR), restaura el último backup, exporta, verifica tablas y borra la instancia temporal."""
    proc, calls = _run(tmp_path, ['applications', 'user_profiles', 'alembic_version'])
    assert proc.returncode == 0, proc.stderr
    steps = [next(i for i, c in enumerate(calls) if key in c)
             for key in ('instances clone', 'backups restore 1700000000000', 'export sql', 'instances delete')]
    assert steps == sorted(steps)
    assert '--point-in-time=' in calls[steps[0]] and 'empleoia-mysql-staging-restore-' in calls[steps[0]]
    assert 'OK:' in proc.stdout
    grant = next(i for i, c in enumerate(calls) if 'add-iam-policy-binding' in c)
    revoke = next(i for i, c in enumerate(calls) if 'remove-iam-policy-binding' in c)
    assert steps[2] > grant and revoke > steps[2]


def test_restore_check_keeps_preexisting_bucket_grant(tmp_path):
    """Si la cuenta de la instancia ya tenía acceso al bucket, no lo agrega ni lo quita."""
    proc, calls = _run(tmp_path, ['applications', 'user_profiles', 'alembic_version'],
                       IAM_POLICY='roles/storage.objectAdmin')
    assert proc.returncode == 0, proc.stderr
    assert not any('add-iam-policy-binding' in c or 'remove-iam-policy-binding' in c for c in calls)


def test_restore_check_fails_on_missing_table_and_still_cleans_up(tmp_path):
    """Si falta una tabla, falla con código distinto de 0 y aun así borra la instancia temporal."""
    proc, calls = _run(tmp_path, ['applications'])
    assert proc.returncode != 0 and 'FALTA: user_profiles' in proc.stderr
    assert any('instances delete' in c for c in calls)


def test_restore_check_fails_without_backups(tmp_path):
    """Sin backups automáticos exitosos, falla sin intentar restaurar."""
    proc, calls = _run(tmp_path, ['applications'], BACKUP_ID='')
    assert proc.returncode != 0 and 'no tiene backups' in proc.stderr
    assert not any('backups restore' in c for c in calls)
    assert any('instances delete' in c for c in calls)


def test_restore_check_requires_settings(tmp_path):
    """Sin PROJECT_ID no hace ninguna llamada."""
    proc, calls = _run(tmp_path, [], PROJECT_ID='')
    assert proc.returncode != 0 and 'PROJECT_ID' in proc.stderr and calls == []
