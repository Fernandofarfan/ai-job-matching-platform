"""Cifrado en reposo, retención y borrado de CVs."""
import os
import time

import pytest
from cryptography.fernet import Fernet

import cv_storage


@pytest.fixture
def workdir(tmp_path, monkeypatch):
    """Directorio de trabajo vacío con una clave de cifrado."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv('CV_ENCRYPTION_KEY', Fernet.generate_key().decode())
    return tmp_path


def test_saved_cv_is_encrypted_and_readable(workdir):
    """El archivo en disco no contiene el texto, pero se lee igual."""
    path = cv_storage.save(b'Ana Perez, Python', 'cv.txt')
    assert b'Ana Perez' not in open(path, 'rb').read()
    assert cv_storage.read_bytes('cv.txt') == b'Ana Perez, Python'


def test_plaintext_path_is_temporary_copy(workdir):
    """Los parsers reciben una copia descifrada con la misma extensión que se borra al salir."""
    cv_storage.save(b'texto', 'cv.txt')
    with cv_storage.plaintext_path('cv.txt') as path:
        assert path.endswith('.txt')
        assert open(path, 'rb').read() == b'texto'
    assert not os.path.exists(path)


def test_legacy_plaintext_cv_and_encrypt_existing(workdir, monkeypatch):
    """Un CV viejo sin cifrar se lee directo y encrypt_existing lo cifra conservando la fecha."""
    monkeypatch.delenv('CV_ENCRYPTION_KEY')
    path = cv_storage.save(b'viejo', 'old.txt')
    os.utime(path, (1_000_000, 1_000_000))
    with cv_storage.plaintext_path('old.txt') as p:
        assert p == path
    monkeypatch.setenv('CV_ENCRYPTION_KEY', Fernet.generate_key().decode())
    assert cv_storage.encrypt_existing() == 1
    assert cv_storage.encrypt_existing() == 0
    assert cv_storage.read_bytes('old.txt') == b'viejo'
    assert os.path.getmtime(path) == 1_000_000


def test_encrypted_cv_without_key_fails_clearly(workdir, monkeypatch):
    """Sin la clave no se devuelve el contenido cifrado como si fuera el CV."""
    cv_storage.save(b'x', 'cv.txt')
    monkeypatch.delenv('CV_ENCRYPTION_KEY')
    with pytest.raises(RuntimeError):
        cv_storage.read_bytes('cv.txt')


def test_rejects_paths_outside_uploads(workdir):
    """Nombres con directorios no salen de uploads/."""
    with pytest.raises(ValueError):
        cv_storage.read_bytes('../app.py')
    assert cv_storage.delete('../app.py') is False
    assert cv_storage.exists('../app.py') is False


def test_expired_delete_all_and_purge_generated(workdir):
    """Retención por antigüedad y borrado total incluyen los documentos generados."""
    old = cv_storage.save(b'a', 'old.pdf')
    cv_storage.save(b'b', 'new.pdf')
    os.utime(old, (time.time() - 40 * 86400,) * 2)
    os.makedirs(os.path.join('temp', 'resumes'))
    gen = os.path.join('temp', 'resumes', 'cv_adaptado.docx')
    open(gen, 'w').close()
    os.utime(gen, (time.time() - 40 * 86400,) * 2)
    assert cv_storage.expired(30) == ['old.pdf']
    assert cv_storage.purge_generated(30) == 1
    assert cv_storage.delete_all() == 2
    assert os.listdir('uploads') == []


def test_retention_task_deletes_old_cv_and_profile(workdir, monkeypatch):
    """La tarea diaria borra el CV vencido y el perfil que lo usa, y deja los recientes."""
    import profile_store
    from tasks import privacy_tasks

    old = cv_storage.save(b'a', 'old.pdf')
    cv_storage.save(b'b', 'new.pdf')
    os.utime(old, (time.time() - 40 * 86400,) * 2)
    profiles = {'data': {'resume_filename': 'old.pdf'}, 'dev': {'resume_filename': 'new.pdf'}}
    monkeypatch.setattr(profile_store, 'get_all_profiles', lambda: dict(profiles))
    monkeypatch.setattr(profile_store, 'delete_profile', lambda role: profiles.pop(role))
    monkeypatch.setenv('CV_RETENTION_DAYS', '30')
    result = privacy_tasks.enforce_cv_retention.run()
    assert result['deleted_cvs'] == 1 and result['deleted_profiles'] == 1
    assert list(profiles) == ['dev']
    assert sorted(os.listdir('uploads')) == ['new.pdf']


def test_wrong_key_fails_instead_of_returning_ciphertext(workdir, monkeypatch):
    """Con otra clave no se le pasa el texto cifrado al parser como si fuera el CV."""
    cv_storage.save(b'x', 'cv.txt')
    monkeypatch.setenv('CV_ENCRYPTION_KEY', Fernet.generate_key().decode())
    with pytest.raises(RuntimeError):
        cv_storage.read_bytes('cv.txt')
