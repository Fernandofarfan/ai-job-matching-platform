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
    # Las rutas viven en web/; los helpers de perfiles siguen en el módulo app
    helper = app.view_functions['view_profile'].__globals__['save_user_profile_for_role']
    app_module = SimpleNamespace(**helper.__globals__)
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

