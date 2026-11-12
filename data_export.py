"""Exportar mis datos: un ZIP con todo lo que la app guarda de una cuenta (sin secretos)."""
import io
import json
import logging
import os
import zipfile
from datetime import datetime

import accounts
import cv_storage
import integrations
import profile_store
import push

logger = logging.getLogger(__name__)

# Tablas que se exportan fila por fila; integraciones y push guardan secretos y van resumidas.
EXPORTED_TABLES = tuple(t for t in accounts.OWNED_TABLES if t not in ('user_integrations', 'push_subscriptions', 'user_sessions', 'user_totp'))


def _dump(data) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2, default=str)


def _rows(session, inspector, table: str, user_id: int) -> list:
    from sqlalchemy import text
    if not inspector.has_table(table) or 'user_id' not in {c['name'] for c in inspector.get_columns(table)}:
        return []
    result = session.execute(text(f'SELECT * FROM {table} WHERE user_id = :uid'), {'uid': user_id})
    return [dict(row._mapping) for row in result]


def _add_dir(zf: zipfile.ZipFile, src: str, arc: str):
    if not os.path.isdir(src):
        return
    for root, _dirs, files in os.walk(src):
        for name in sorted(files):
            if not name.startswith('.'):
                path = os.path.join(root, name)
                zf.write(path, os.path.join(arc, os.path.relpath(path, src)))


def build(user_id: int) -> bytes:
    """ZIP con la cuenta, sus tablas, perfiles, CVs originales, resultados y documentos generados."""
    from sqlalchemy import inspect
    user = accounts.get_user(user_id)
    if user is None:
        raise ValueError('La cuenta no existe')
    problems = []
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as zf, accounts.as_user(user_id):
        with accounts._sessions()() as session:
            row = session.get(accounts.User, user_id)
            zf.writestr('cuenta.json', _dump({
                'email': row.email, 'creada': row.created_at, 'email_verificado': row.email_verified_at,
                'integraciones': integrations.status(user_id),
                'dispositivos_push': push.device_count(user_id)}))
            inspector = inspect(session.get_bind())
            for table in EXPORTED_TABLES:
                zf.writestr(f'datos/{table}.json', _dump(_rows(session, inspector, table, user_id)))
        profiles = profile_store.get_all_profiles()
        zf.writestr('perfiles.json', _dump(profiles))
        for name in sorted({p.get('resume_filename') for p in profiles.values()} - {None, ''}):
            try:
                zf.writestr(f'cvs/{name}', cv_storage.read_bytes(name))
            except (OSError, RuntimeError, ValueError) as e:
                logger.warning(f'Exportación de la cuenta {user_id}: CV {name} no incluido: {e}')
                problems.append(f'CV {name}: no se pudo leer')
        _add_dir(zf, os.path.join(accounts.RESULTS_ROOT, f'u{user_id}'), 'resultados')
        generated = os.path.join(os.getenv('GENERATED_DIR', 'temp'), f'u{user_id}')
        for kind in accounts.GENERATED_KINDS:
            _add_dir(zf, os.path.join(generated, kind), f'documentos/{kind}')
        readme = [f'Datos de {user["email"]} exportados de EmpleoIA el {datetime.now():%Y-%m-%d %H:%M}.', '',
                  'cuenta.json: email, fechas e integraciones conectadas (sin tokens ni contraseñas).',
                  'datos/: una lista JSON por tabla (tracker, historial de estados, alertas, etc.).',
                  'perfiles.json y cvs/: perfiles por rol y CVs originales.',
                  'resultados/ y documentos/: CSV de búsquedas, cartas y CVs generados.']
        if problems:
            readme += ['', 'No se pudieron incluir:'] + [f'- {p}' for p in problems]
        zf.writestr('LEEME.txt', '\n'.join(readme) + '\n')
    return buffer.getvalue()
