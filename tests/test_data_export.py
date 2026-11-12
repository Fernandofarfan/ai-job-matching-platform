"""Tests de "Exportar mis datos"."""
import io
import json
import zipfile

import pytest
from cryptography.fernet import Fernet
from sqlalchemy import text

import accounts
import cv_storage
import data_export
import integrations
import profile_store
import push

PASSWORD = 'clave-larga-1'


@pytest.fixture
def two_accounts(_accounts_sqlite, tmp_path, monkeypatch):
    """Dos cuentas con tracker, perfil con CV cifrado, resultados, documentos e integraciones."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv('CV_ENCRYPTION_KEY', Fernet.generate_key().decode())
    monkeypatch.delenv('GENERATED_DIR', raising=False)
    monkeypatch.setenv('ALLOW_SIGNUP', 'true')
    with _accounts_sqlite.begin() as conn:
        conn.execute(text('CREATE TABLE applications (id INTEGER PRIMARY KEY, user_id INTEGER, title TEXT)'))
    ana = accounts.register('ana@example.com', PASSWORD)
    beto = accounts.register('beto@example.com', PASSWORD)
    with _accounts_sqlite.begin() as conn:
        conn.execute(text("INSERT INTO applications (user_id, title) VALUES (:a, 'Backend'), (:b, 'Secreto')"),
                     {'a': ana, 'b': beto})
    for uid, name in ((ana, 'ana.pdf'), (beto, 'beto.pdf')):
        cv_storage.save(f'CV de {name}'.encode(), name)
        with accounts.as_user(uid):
            profile_store.save_profile('dev', {'name': name, 'resume_filename': name})
    (tmp_path / 'results' / f'u{ana}').mkdir(parents=True)
    (tmp_path / 'results' / f'u{ana}' / 'python.csv').write_text('Title\nBackend\n')
    (tmp_path / 'results' / f'u{beto}').mkdir(parents=True)
    (tmp_path / 'results' / f'u{beto}' / 'ajeno.csv').write_text('Title\nOtro\n')
    (tmp_path / 'temp' / f'u{ana}' / 'cover_letters').mkdir(parents=True)
    (tmp_path / 'temp' / f'u{ana}' / 'cover_letters' / 'carta.docx').write_bytes(b'docx')
    integrations.set_telegram_chat(ana, '12345')
    integrations.new_extension_token(ana)
    push.subscribe(ana, 'https://fcm.googleapis.com/fcm/send/abc', 'k', 'a')
    return ana, beto


def _open(data):
    return zipfile.ZipFile(io.BytesIO(data))


def test_export_contains_only_own_data(two_accounts):
    """El ZIP trae los datos de la cuenta, el CV descifrado y nada de la otra cuenta."""
    ana, _ = two_accounts
    zf = _open(data_export.build(ana))
    names = set(zf.namelist())
    assert {'cuenta.json', 'perfiles.json', 'LEEME.txt', 'cvs/ana.pdf', 'resultados/python.csv',
            'documentos/cover_letters/carta.docx', 'datos/applications.json'} <= names
    assert zf.read('cvs/ana.pdf') == b'CV de ana.pdf'
    assert [r['title'] for r in json.loads(zf.read('datos/applications.json'))] == ['Backend']
    assert 'beto' not in ' '.join(names) and 'ajeno.csv' not in names
    assert list(json.loads(zf.read('perfiles.json'))) == ['dev']


def test_export_has_no_secrets(two_accounts):
    """Ni el hash de la contraseña, ni el token de la extensión, ni las claves push."""
    ana, _ = two_accounts
    data = data_export.build(ana)
    account = json.loads(_open(data).read('cuenta.json'))
    assert account['email'] == 'ana@example.com' and account['dispositivos_push'] == 1
    assert account['integraciones'] == {'telegram_chat_id': '12345', 'extension_token': True, 'gmail': False}
    blob = b''.join(_open(data).read(n) for n in _open(data).namelist())
    assert accounts.get_user(ana)['password_hash'].encode() not in blob
    assert b'fcm.googleapis.com' not in blob and b'extension_token_hash' not in blob


def test_unreadable_cv_is_reported(two_accounts):
    """Si falta un CV, el resto se exporta y el LEEME lo avisa."""
    ana, _ = two_accounts
    cv_storage.delete('ana.pdf')
    zf = _open(data_export.build(ana))
    assert 'cvs/ana.pdf' not in zf.namelist()
    assert 'CV ana.pdf' in zf.read('LEEME.txt').decode()


def test_export_route_needs_password(client, accounts_db, two_accounts):
    """La descarga pide la contraseña y no se guarda en caché."""
    client.post('/login', data={'email': 'ana@example.com', 'password': PASSWORD})
    wrong = client.post('/account/export', data={'password': 'mal'})
    assert wrong.status_code == 302
    response = client.post('/account/export', data={'password': PASSWORD})
    assert response.status_code == 200 and response.mimetype == 'application/zip'
    assert response.headers['Cache-Control'] == 'no-store'
    assert 'attachment' in response.headers['Content-Disposition']
    assert 'cvs/ana.pdf' in _open(response.data).namelist()
