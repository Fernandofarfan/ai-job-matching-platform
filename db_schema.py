"""Metadata de todos los modelos y comparación con el esquema real (Alembic y CI)."""
import importlib

# Módulos con su propia Base declarativa
BASE_MODULES = ('models', 'accounts', 'job_alerts', 'profile_store')
# Módulos cuyos modelos heredan de accounts.Base: se importan para registrarlos
ACCOUNT_MODULES = ('integrations', 'push', 'security_events', 'two_factor', 'user_sessions')
# Módulos cuyos modelos heredan de job_alerts.Base
ALERT_MODULES = ('job_feedback',)
# Tablas sin modelo: el historial se usa con SQL directo (db_config.py) y `job_tracker` es la
# tabla heredada que la app ya no usa (no se borra sola por si tiene datos)
UNMODELED_TABLES = {'application_status_history', 'job_tracker', 'alembic_version'}


def metadata_list():
    """MetaData de cada Base declarativa, con todos sus modelos registrados."""
    for name in ACCOUNT_MODULES + ALERT_MODULES:
        importlib.import_module(name)
    return [importlib.import_module(name).Base.metadata for name in BASE_MODULES]


def include_object(obj, name, type_, reflected, compare_to):
    """Deja afuera de la comparación las tablas sin modelo."""
    return not (type_ == 'table' and name in UNMODELED_TABLES)


def schema_diff(connection):
    """Diferencias entre la base y los modelos (lista vacía = sin drift)."""
    from alembic.autogenerate import compare_metadata
    from alembic.migration import MigrationContext
    context = MigrationContext.configure(connection, opts={
        'compare_type': True, 'include_object': include_object, 'target_metadata': metadata_list(),
    })
    return compare_metadata(context, metadata_list())
