"""La cuenta de ADMIN_EMAIL administra recién al verificar el email; el aviso push abre la oferta si es una sola."""
import io

import pytest

import accounts
import push
from scripts import create_admin
from tasks import notification_tasks

PASSWORD = 'clave-larga-1'


@pytest.fixture
def admin_env(accounts_db, monkeypatch):
    """Base vacía con ADMIN_EMAIL; anota a quién se asignan los datos previos."""
    monkeypatch.setenv('ADMIN_EMAIL', 'Admin@Example.com')
    monkeypatch.delenv('K_SERVICE', raising=False)
    claimed = []
    monkeypatch.setattr(accounts, 'claim_orphans', claimed.append)
    return claimed


def test_admin_email_needs_verification(admin_env):
    """Quien solo conoce ADMIN_EMAIL crea una cuenta sin permisos ni datos previos hasta verificar."""
    uid = accounts.register('admin@example.com', PASSWORD)
    assert not accounts.get_user(uid)['email_verified']
    assert not accounts.is_admin(uid) and admin_env == []
    accounts.mark_verified(uid)
    accounts.mark_verified(uid)  # ya verificada no reclama de nuevo (lo nuevo sin dueño puede ser de invitados)
    assert accounts.is_admin(uid) and admin_env == [uid]


def test_failed_claim_leaves_account_unverified(admin_env, monkeypatch):
    """Si el reclamo falla, la cuenta queda sin verificar y la próxima verificación lo reintenta."""
    uid = accounts.register('admin@example.com', PASSWORD)

    def boom(user_id):
        raise RuntimeError('MySQL no responde')
    monkeypatch.setattr(accounts, 'claim_orphans', boom)
    with pytest.raises(RuntimeError):
        accounts.mark_verified(uid)
    assert not accounts.get_user(uid)['email_verified']


def test_legacy_owner_needs_verified_admin(admin_env, monkeypatch):
    """Telegram, Gmail, la extensión y los archivos previos no van a la cuenta de ADMIN_EMAIL sin verificar."""
    uid = accounts.register('admin@example.com', PASSWORD)
    assert accounts.legacy_owner_id() is None
    accounts.mark_verified(uid)
    assert accounts.legacy_owner_id() == uid
    monkeypatch.delenv('ADMIN_EMAIL')
    assert accounts.legacy_owner_id() == uid


def test_second_account_verifying_claims_nothing(admin_env, monkeypatch):
    """Verificar otra cuenta no le asigna los datos previos."""
    monkeypatch.setenv('ALLOW_SIGNUP', 'true')
    first = accounts.register('admin@example.com', PASSWORD, verified=True)
    other = accounts.register('beto@example.com', PASSWORD)
    accounts.mark_verified(other)
    assert admin_env == [first] and not accounts.is_admin(other)


def test_create_admin_script(admin_env, monkeypatch):
    """scripts/create_admin.py crea la cuenta verificada y no se puede usar dos veces."""
    monkeypatch.setattr('sys.stdin', io.StringIO(PASSWORD + '\n'))
    assert create_admin.main(['--password-stdin']) == 0
    uid = accounts.find_user_id('admin@example.com')
    assert accounts.is_admin(uid) and admin_env == [uid]
    monkeypatch.setattr('sys.stdin', io.StringIO(PASSWORD + '\n'))
    assert create_admin.main(['--password-stdin']) == 1


def test_create_admin_takes_over_unverified_first_account(admin_env, monkeypatch):
    """Si la cuenta de ADMIN_EMAIL quedó sin verificar, el script le pone otra contraseña y la verifica."""
    uid = accounts.register('admin@example.com', 'clave-del-intruso')
    monkeypatch.setattr('sys.stdin', io.StringIO(PASSWORD + '\n'))
    assert create_admin.main(['--password-stdin']) == 0
    assert accounts.is_admin(uid) and admin_env == [uid]
    assert accounts.authenticate('admin@example.com', PASSWORD) == uid
    assert accounts.authenticate('admin@example.com', 'clave-del-intruso') is None


@pytest.mark.parametrize(('url', 'expected'), [
    ('/alerts', '/alerts'),
    ('https://www.bumeran.com.ar/empleos/1', 'https://www.bumeran.com.ar/empleos/1'),
    ('//evil.example/x', '/'),
    ('javascript:alert(1)', '/'),
    ('https:///sin-host', '/'),
])
def test_push_click_url(url, expected):
    """El aviso abre rutas de la app o links http(s); el resto, la portada."""
    assert push._click_url(url) == expected


@pytest.mark.parametrize(('jobs', 'expected'), [
    ([{'Title': 'Data Analyst', 'Url': 'https://x.example/1'}], 'https://x.example/1'),
    ([{'Title': 'A', 'Url': 'https://x.example/1'}, {'Title': 'B', 'Url': 'https://x.example/2'}], '/alerts'),
    ([{'Title': 'Sin link'}], '/alerts'),
])
def test_push_alert_opens_single_offer(monkeypatch, jobs, expected):
    """Con una oferta el aviso la abre; con varias o sin link, la página de alertas."""
    calls = []
    monkeypatch.setattr(push, 'send_to_current', lambda title, body, url='/': calls.append(url) or True)
    notification_tasks.notify_alert({'name': 'x', 'channels': ['push']}, jobs)
    assert calls == [expected]
