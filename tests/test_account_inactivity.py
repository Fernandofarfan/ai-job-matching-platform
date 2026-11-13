"""Borrado de cuentas inactivas: aviso por email, entrar lo anula y la primera cuenta no se borra."""
from datetime import datetime, timedelta

import pytest

import account_notify
import accounts
import profile_store
import user_sessions
from tasks import privacy_tasks


@pytest.fixture
def three_accounts(_accounts_sqlite, monkeypatch):
    """Admin + 2 cuentas que no entran hace 400 días; emails capturados."""
    monkeypatch.setenv('ALLOW_SIGNUP', 'true')
    monkeypatch.setenv('ADMIN_EMAIL', 'u0@example.com')
    ids = [accounts.register(f'u{i}@example.com', 'Clave-segura-123') for i in range(3)]
    old = datetime.now() - timedelta(days=400)
    with accounts._sessions()() as session:
        session.execute(accounts.update(accounts.User).values(created_at=old, last_active_at=old))
        session.commit()
    sent = []
    monkeypatch.setattr(account_notify, 'deliver', lambda to, subject, body, link, cta: sent.append(to) or True)
    monkeypatch.setattr(profile_store, 'primary_available', lambda: True)
    monkeypatch.setenv('PUBLIC_BASE_URL', 'https://empleoia.example')
    monkeypatch.setenv('ACCOUNT_INACTIVITY_DAYS', '365')
    monkeypatch.setenv('ACCOUNT_INACTIVITY_NOTICE_DAYS', '30')
    return ids, sent


def _age_notices(days):
    """Corre los avisos ya enviados `days` días hacia atrás."""
    with accounts._sessions()() as session:
        for user in session.query(accounts.User).filter(accounts.User.inactivity_notice_at.isnot(None)):
            user.inactivity_notice_at -= timedelta(days=days)
        session.commit()


def test_off_by_default(three_accounts, monkeypatch):
    """Sin ACCOUNT_INACTIVITY_DAYS no avisa ni borra."""
    _, sent = three_accounts
    monkeypatch.delenv('ACCOUNT_INACTIVITY_DAYS')
    assert privacy_tasks.enforce_account_inactivity.run() == {'notified': 0, 'deleted': 0}
    assert sent == [] and accounts.count_users() == 3


def test_notice_then_delete_except_first_account(three_accounts):
    """Primero avisa (una sola vez); al vencer el aviso borra; la primera cuenta no se toca."""
    (admin, a, b), sent = three_accounts
    assert privacy_tasks.enforce_account_inactivity.run() == {'notified': 2, 'deleted': 0}
    assert sent == ['u1@example.com', 'u2@example.com']
    assert privacy_tasks.enforce_account_inactivity.run() == {'notified': 0, 'deleted': 0}
    _age_notices(29)
    assert privacy_tasks.enforce_account_inactivity.run()['deleted'] == 0
    _age_notices(1)
    assert privacy_tasks.enforce_account_inactivity.run() == {'notified': 0, 'deleted': 2}
    assert accounts.user_ids() == [admin] and len(sent) == 2


def test_signing_in_cancels_the_notice(three_accounts):
    """Una cuenta avisada que entra no se borra y vuelve a contar desde cero."""
    (_, a, b), _ = three_accounts
    privacy_tasks.enforce_account_inactivity.run()
    user_sessions.create(a)
    _age_notices(30)
    assert privacy_tasks.enforce_account_inactivity.run()['deleted'] == 1
    assert accounts.get_user(a) is not None and accounts.get_user(b) is None


def test_session_activity_counts(three_accounts):
    """Seguir usando una sesión abierta también cuenta como actividad."""
    (_, a, _), _ = three_accounts
    sid = user_sessions.create(a)
    with accounts._sessions()() as session:
        session.execute(accounts.update(accounts.User).where(accounts.User.id == a)
                        .values(last_active_at=datetime.now() - timedelta(days=400)))
        session.execute(user_sessions.update(user_sessions.UserSession)
                        .values(last_seen_at=datetime.now() - timedelta(minutes=10)))
        session.commit()
    assert user_sessions.is_active(a, sid)
    inactive = [u['id'] for u in accounts.inactive_accounts(datetime.now() - timedelta(days=1))]
    assert a not in inactive and len(inactive) == 2


def test_no_email_no_deletion(three_accounts, monkeypatch):
    """Si el aviso no sale (sin email o sin PUBLIC_BASE_URL) no se marca, y nunca se borra sin aviso."""
    monkeypatch.setattr(account_notify, 'deliver', lambda *a: False)
    assert privacy_tasks.enforce_account_inactivity.run() == {'notified': 0, 'deleted': 0}
    monkeypatch.delenv('PUBLIC_BASE_URL')
    assert privacy_tasks.enforce_account_inactivity.run() == {'notified': 0, 'deleted': 0}
    _age_notices(400)
    assert privacy_tasks.enforce_account_inactivity.run()['deleted'] == 0
    assert accounts.count_users() == 3


def test_interrupted_notice_is_sent_again_not_deleted(three_accounts):
    """Si el worker se cortó después de reservar el aviso y antes de mandarlo, se vuelve a mandar; no se borra."""
    (_, a, b), sent = three_accounts
    old = datetime.now().replace(microsecond=0) - timedelta(days=40)
    for uid in (a, b):
        assert accounts.set_inactivity_notice(uid, old)
    assert privacy_tasks.enforce_account_inactivity.run() == {'notified': 2, 'deleted': 0}
    assert sent == ['u1@example.com', 'u2@example.com'] and accounts.count_users() == 3


def test_recent_claim_is_left_to_its_worker(three_accounts):
    """Una reserva reciente sin confirmar es de otro worker que está mandando el email: no se duplica."""
    (_, a, b), sent = three_accounts
    assert accounts.set_inactivity_notice(a, datetime.now().replace(microsecond=0))
    assert privacy_tasks.enforce_account_inactivity.run() == {'notified': 1, 'deleted': 0}
    assert sent == ['u2@example.com']


def test_login_right_before_deletion_keeps_the_account(three_accounts, monkeypatch):
    """Si la cuenta entra entre la lista de inactivas y el borrado, el borrado ve el aviso anulado y no borra."""
    (_, a, b), _ = three_accounts
    privacy_tasks.enforce_account_inactivity.run()
    _age_notices(30)
    listed = accounts.inactive_accounts

    def list_then_login(since):
        users = listed(since)
        user_sessions.create(a)
        return users
    monkeypatch.setattr(accounts, 'inactive_accounts', list_then_login)
    assert privacy_tasks.enforce_account_inactivity.run()['deleted'] == 1
    assert accounts.get_user(a) is not None and accounts.get_user(b) is None


def test_deletes_cvs_and_profiles(three_accounts, monkeypatch):
    """Con la cuenta borra sus perfiles y sus CVs."""
    import cv_storage
    (_, a, b), _ = three_accounts
    profiles = {a: {'data': {'resume_filename': 'a.pdf'}}, b: {'dev': {'resume_filename': 'b.pdf'}}}
    deleted = []
    monkeypatch.setattr(profile_store, 'get_all_profiles', lambda: profiles[accounts.current_user_id()])
    monkeypatch.setattr(profile_store, 'delete_all', lambda: profiles[accounts.current_user_id()].clear())
    monkeypatch.setattr(cv_storage, 'delete', lambda name: deleted.append(name) or True)
    privacy_tasks.enforce_account_inactivity.run()
    _age_notices(30)
    assert privacy_tasks.enforce_account_inactivity.run()['deleted'] == 2
    assert sorted(deleted) == ['a.pdf', 'b.pdf'] and profiles == {a: {}, b: {}}


def test_cvs_are_deleted_even_if_profiles_fail(three_accounts, monkeypatch):
    """Si falla borrar los perfiles, los CVs se borran igual: la cuenta ya no existe y nadie los volvería a buscar."""
    import cv_storage
    (_, a, b), _ = three_accounts
    profiles = {a: {'data': {'resume_filename': 'a.pdf'}}, b: {'dev': {'resume_filename': 'b.pdf'}}}
    deleted = []

    def broken():
        raise RuntimeError('perfiles caídos')
    monkeypatch.setattr(profile_store, 'get_all_profiles', lambda: profiles[accounts.current_user_id()])
    monkeypatch.setattr(profile_store, 'delete_all', broken)
    monkeypatch.setattr(cv_storage, 'delete', lambda name: deleted.append(name) or True)
    privacy_tasks.enforce_account_inactivity.run()
    _age_notices(30)
    assert privacy_tasks.enforce_account_inactivity.run()['deleted'] == 2
    assert sorted(deleted) == ['a.pdf', 'b.pdf']


def test_mysql_down_postpones(three_accounts, monkeypatch):
    """Sin MySQL no avisa ni borra."""
    monkeypatch.setattr(profile_store, 'primary_available', lambda: False)
    assert privacy_tasks.enforce_account_inactivity.run() == {'notified': 0, 'deleted': 0}


def test_notice_is_at_most_half_the_period(monkeypatch):
    """Un aviso más largo que el plazo se recorta a la mitad."""
    monkeypatch.setenv('ACCOUNT_INACTIVITY_DAYS', '20')
    monkeypatch.setenv('ACCOUNT_INACTIVITY_NOTICE_DAYS', '30')
    assert privacy_tasks._inactivity_days() == (20, 10)
