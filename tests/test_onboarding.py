"""Primer uso guiado (CV → búsqueda → alerta) en la portada y embudo de activación en Administración."""
import os

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import accounts
import job_alerts
import onboarding
import profile_store

PASSWORD = 'clave-larga-1'


@pytest.fixture(autouse=True)
def signup_open(monkeypatch):
    monkeypatch.setenv('ALLOW_SIGNUP', 'true')


@pytest.fixture
def alerts_sqlite():
    engine = create_engine('sqlite://', poolclass=StaticPool, connect_args={'check_same_thread': False})
    job_alerts.Base.metadata.create_all(engine)
    job_alerts.configure(sessionmaker(bind=engine))
    yield
    job_alerts.configure(None)


@pytest.fixture
def results_root(tmp_path, monkeypatch):
    monkeypatch.setattr(accounts, 'RESULTS_ROOT', str(tmp_path / 'results'))
    return tmp_path / 'results'


def _search(user_id, root):
    folder = root / f'u{user_id}'
    os.makedirs(folder, exist_ok=True)
    (folder / 'python.csv').write_text('title\nDev\n')


def _alert(user_id):
    with accounts.as_user(user_id):
        job_alerts.create_search({'name': 'Python', 'position': 'Python', 'location': '',
                                  'portals': ['computrabajo'], 'channels': ['email']})


def _cv(user_id):
    with accounts.as_user(user_id):
        profile_store.save_profile('general', {'skills': ['python']})


def test_status_follows_the_steps(alerts_sqlite, results_root):
    uid = accounts.register('ana@example.com', PASSWORD, terms_accepted=True)
    first = onboarding.status(uid)
    assert first['completed'] == 0 and first['next']['key'] == 'cv' and not first['finished']
    _cv(uid)
    assert onboarding.status(uid)['next']['key'] == 'search'
    _search(uid, results_root)
    assert onboarding.status(uid)['next']['key'] == 'alert'
    _alert(uid)
    done = onboarding.status(uid)
    assert done['finished'] and done['next'] is None and done['completed'] == 3


def test_status_is_per_account(alerts_sqlite, results_root):
    ana = accounts.register('ana@example.com', PASSWORD, terms_accepted=True)
    bob = accounts.register('bob@example.com', PASSWORD, terms_accepted=True)
    _cv(ana)
    _search(ana, results_root)
    _alert(ana)
    assert onboarding.status(ana)['finished']
    assert onboarding.status(bob)['completed'] == 0


def test_funnel_counts_steps_in_order(alerts_sqlite, results_root):
    ids = [accounts.register(f'u{i}@example.com', PASSWORD, terms_accepted=True) for i in range(4)]
    for uid in ids[:3]:
        _cv(uid)
    for uid in ids[:2]:
        _search(uid, results_root)
    _alert(ids[0])
    _alert(ids[3])  # alerta sin CV: no cuenta, porque se salteó pasos
    rows = {row['key']: row for row in onboarding.funnel()}
    assert [rows[k]['count'] for k in ('registered', 'cv', 'search', 'alert')] == [4, 3, 2, 1]
    assert rows['registered']['conversion'] is None
    assert [rows[k]['conversion'] for k in ('cv', 'search', 'alert')] == [75, 67, 50]


def test_failing_source_counts_as_pending(alerts_sqlite, results_root, monkeypatch):
    uid = accounts.register('ana@example.com', PASSWORD, terms_accepted=True)

    def broken():
        raise RuntimeError('MySQL caído')
    monkeypatch.setattr(profile_store, 'get_all_profiles', broken)
    assert onboarding.status(uid)['next']['key'] == 'cv'


def test_home_shows_guide_until_finished(client, accounts_db, alerts_sqlite, results_root, monkeypatch):
    monkeypatch.setenv('ALLOW_SIGNUP', 'true')
    client.post('/register', data={'accept_terms': 'on', 'email': 'ana@example.com', 'password': PASSWORD, 'confirm': PASSWORD})
    uid = accounts.find_user_id('ana@example.com')
    page = client.get('/').get_data(as_text=True)
    assert 'id="onboarding"' in page and '0 de 3 listos' in page and 'href="/view_profile"' in page
    _cv(uid)
    _search(uid, results_root)
    page = client.get('/').get_data(as_text=True)
    assert '2 de 3 listos' in page and 'href="/alerts"' in page
    _alert(uid)
    assert 'id="onboarding"' not in client.get('/').get_data(as_text=True)


def test_admin_sees_activation_funnel(client, accounts_db, alerts_sqlite, results_root, monkeypatch):
    monkeypatch.setenv('ALLOW_SIGNUP', 'true')
    client.post('/register', data={'accept_terms': 'on', 'email': 'ana@example.com', 'password': PASSWORD, 'confirm': PASSWORD})
    _cv(accounts.find_user_id('ana@example.com'))
    page = client.get('/admin').get_data(as_text=True)
    assert 'id="admin-activation"' in page and 'Se registraron' in page and '100%' in page
