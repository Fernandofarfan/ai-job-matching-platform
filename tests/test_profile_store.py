"""Perfiles en base de datos (SQLite en memoria como stand-in de MySQL) y fallback JSON."""
import json

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import profile_store


@pytest.fixture
def db():
    engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
    profile_store.Base.metadata.create_all(engine)
    profile_store.configure(sessionmaker(bind=engine))
    yield
    profile_store.configure(None)


def test_save_get_delete_in_db(db):
    profile_store.save_profile('backend', {'skills': ['python'], 'resume_filename': 'cv.pdf'})
    profile_store.save_profile('data', {'skills': ['sql']})
    profile_store.save_profile('backend', {'skills': ['go']})
    assert profile_store.get_all_profiles() == {
        'backend': {'skills': ['go']}, 'data': {'skills': ['sql']}}
    assert profile_store.get_profile('data') == {'skills': ['sql']}
    assert profile_store.get_first_profile() == {'skills': ['go']}
    assert profile_store.delete_profile('backend') == {'skills': ['go']}
    assert profile_store.delete_profile('backend') is None
    assert list(profile_store.get_all_profiles()) == ['data']


def test_json_fallback():
    profile_store.save_profile('backend', {'skills': ['python']})
    with open(profile_store.JSON_PATH, encoding='utf-8') as f:
        stored = json.load(f)
    assert stored.pop(profile_store.WRITTEN_KEY) > 0
    assert stored == {'backend': {'skills': ['python']}}
    assert profile_store.delete_profile('backend') == {'skills': ['python']}
    assert profile_store.get_all_profiles() == {}


def test_legacy_json_is_imported_once(db, tmp_path):
    with open(profile_store.JSON_PATH, 'w', encoding='utf-8') as f:
        json.dump({'backend': {'skills': ['python']}, 'roto': 'no es un dict'}, f)
    profile_store._import_legacy_json()
    assert profile_store.get_all_profiles() == {'backend': {'skills': ['python']}}
    assert (tmp_path / 'user_profiles.json.migrated').exists()


def test_upload_creates_profile_and_view_profile_reads_it(app, client):
    """El alta y la lectura de la app usan el mismo store."""
    from types import SimpleNamespace
    # Las rutas viven en routers/content_pages.py; los helpers de perfiles siguen en el módulo app
    app_module = SimpleNamespace(**app.extensions['empleoia_app_globals'])
    assert app_module.profile_store is profile_store
    assert app_module.save_user_profile_for_role({'skills': ['python']}, 'cv.pdf', 'backend')
    assert app_module.get_user_profile_by_role('backend')['resume_filename'] == 'cv.pdf'
    assert client.get('/view_profile', follow_redirects=False).headers['Location'].endswith('/view_profile/backend')
    assert app_module.delete_user_profile_by_role('backend')
    assert app_module.get_all_user_profiles() == {}


def test_db_outage_falls_back_to_json_and_syncs_on_recovery(db, monkeypatch):
    """Si MySQL se cae, los perfiles siguen en el JSON y esos cambios se aplican al volver."""
    from sqlalchemy.exc import OperationalError
    profile_store.save_profile('backend', {'skills': ['python']})
    profile_store.save_profile('data', {'skills': ['sql']})
    working = profile_store._session_factory

    def broken():
        raise OperationalError('SELECT 1', {}, Exception('MySQL caído'))
    profile_store.configure(broken)
    profile_store.save_profile('backend', {'skills': ['go']})
    profile_store.save_profile('nuevo', {'skills': ['rust']})
    profile_store.delete_profile('nuevo')
    assert profile_store.delete_profile('data') is None  # solo está en MySQL: no se puede borrar
    assert profile_store._session_factory is None
    assert profile_store.get_all_profiles() == {'backend': {'skills': ['go']}}

    profile_store.configure(working)
    profile_store._import_legacy_json()
    assert profile_store.get_all_profiles() == {
        'backend': {'skills': ['go']}, 'data': {'skills': ['sql']}}


def test_recovery_keeps_rows_updated_after_the_json(db):
    """Un JSON más viejo que la fila de MySQL (otra instancia la actualizó) no la pisa."""
    import os
    import time
    profile_store._write_json({'backend': {'skills': ['viejo']}}, {'data'})
    old = time.time() - 3600
    os.utime(profile_store.JSON_PATH, (old, old))
    with profile_store._session_factory() as session:
        session.add_all([
            profile_store.UserProfile(role_type='backend', data={'skills': ['nuevo']}),
            profile_store.UserProfile(role_type='data', data={'skills': ['sql']}),
        ])
        session.commit()
    profile_store._import_legacy_json()
    assert profile_store.get_all_profiles() == {
        'backend': {'skills': ['nuevo']}, 'data': {'skills': ['sql']}}


def test_delete_all_clears_db_and_json_copies(db, tmp_path, monkeypatch):
    """Borra las filas, el JSON de respaldo y la copia .migrated."""
    monkeypatch.setattr(profile_store, 'JSON_PATH', str(tmp_path / 'p.json'))
    (tmp_path / 'p.json.migrated').write_text('{}')
    profile_store.save_profile('backend', {'raw_text': 'CV'})
    profile_store.delete_all()
    assert profile_store.get_all_profiles() == {}
    assert not (tmp_path / 'p.json.migrated').exists()


def test_delete_all_fails_while_mysql_is_down(monkeypatch):
    """Con MySQL caído no informa éxito borrando solo el JSON."""
    monkeypatch.setenv('PROFILE_STORAGE', 'mysql')
    monkeypatch.setattr(profile_store, '_sessions', lambda: None)
    with pytest.raises(RuntimeError):
        profile_store.delete_all()



@pytest.fixture
def cv_key(monkeypatch):
    """CV_ENCRYPTION_KEY temporal."""
    from cryptography.fernet import Fernet
    monkeypatch.setenv('CV_ENCRYPTION_KEY', Fernet.generate_key().decode())


def test_profiles_are_encrypted_in_db_and_json(db, cv_key):
    """Con clave, el texto del CV no queda legible en MySQL ni en el JSON de respaldo."""
    from sqlalchemy import text
    profile_store.save_profile('backend', {'raw_text': 'Ana Pérez, Python'})
    with profile_store._session_factory() as session:
        raw = session.execute(text('SELECT data FROM user_profiles')).scalar()
    assert 'Ana' not in raw and profile_store.ENC_KEY in raw
    assert profile_store.get_profile('backend') == {'raw_text': 'Ana Pérez, Python'}

    profile_store.configure(None)
    profile_store._write_json({'data': {'raw_text': 'Ana SQL'}}, set())
    assert 'Ana' not in open(profile_store.JSON_PATH, encoding='utf-8').read()
    assert profile_store._read_json() == {'data': {'raw_text': 'Ana SQL'}}


def test_encrypt_existing_profiles(db, monkeypatch, tmp_path):
    """Los perfiles guardados antes de configurar la clave se cifran y se siguen leyendo."""
    from cryptography.fernet import Fernet
    from sqlalchemy import text
    profile_store.save_profile('backend', {'raw_text': 'Ana Python'})
    (tmp_path / 'user_profiles.json.migrated').write_text(json.dumps({'old': {'raw_text': 'Ana vieja'}}))
    assert profile_store.encrypt_existing() == 0
    monkeypatch.setenv('CV_ENCRYPTION_KEY', Fernet.generate_key().decode())
    assert profile_store.encrypt_existing() == 2
    assert profile_store.encrypt_existing() == 0
    with profile_store._session_factory() as session:
        assert 'Ana' not in session.execute(text('SELECT data FROM user_profiles')).scalar()
    assert 'Ana' not in (tmp_path / 'user_profiles.json.migrated').read_text()
    assert profile_store.get_profile('backend') == {'raw_text': 'Ana Python'}


def test_wrong_key_gives_clear_error(db, cv_key, monkeypatch):
    """Con otra clave, leer un perfil cifrado da un error claro."""
    from cryptography.fernet import Fernet
    profile_store.save_profile('backend', {'raw_text': 'x'})
    monkeypatch.setenv('CV_ENCRYPTION_KEY', Fernet.generate_key().decode())
    with pytest.raises(RuntimeError, match='CV_ENCRYPTION_KEY'):
        profile_store.get_profile('backend')
