"""Entorno de Alembic: usa las mismas variables DB_* que la app."""
import os
import sys
from logging.config import fileConfig

from sqlalchemy import create_engine

from alembic import context

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

config = context.config
if config.config_file_name:
    fileConfig(config.config_file_name)



def run_migrations_offline():
    """--sql: solo genera SQL, sin importar models (que intenta conectarse a MySQL al importarse)."""
    context.configure(url='mysql+mysqlconnector://', literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online():
    """Migra la base de DB_* comparando contra la metadata de todos los modelos."""
    import db_schema
    import models
    engine = create_engine(models.get_database_url())
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=db_schema.metadata_list(),
                          compare_type=True, include_object=db_schema.include_object)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
