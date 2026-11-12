"""Persistencia real: perfiles, alertas y tracker en MySQL; contador de IA en Redis."""
import os
import uuid

import pytest


@pytest.fixture
def mysql(migrated_db, monkeypatch):
    """Sesión SQLAlchemy contra la base migrada, con la misma clave de cifrado que la app levantada."""
    import job_alerts
    import profile_store
    from tests_integration.conftest import CV_ENCRYPTION_KEY
    monkeypatch.setenv('CV_ENCRYPTION_KEY', CV_ENCRYPTION_KEY)
    profile_store.configure(None)
    job_alerts.configure(None)
    yield
    profile_store.configure(None)
    job_alerts.configure(None)


def test_profile_round_trip(mysql, monkeypatch, tmp_path):
    """Guardar, leer y borrar un perfil pasa por la tabla user_profiles, no por el JSON."""
    import profile_store
    monkeypatch.setattr(profile_store, 'JSON_PATH', str(tmp_path / 'profiles.json'))
    role = f'it_{uuid.uuid4().hex[:8]}'
    profile_store.save_profile(role, {'name': 'Ana', 'skills': ['python', 'sql'], 'experience_years': 4})
    assert profile_store._sessions() is not None
    assert profile_store.get_profile(role)['skills'] == ['python', 'sql']
    assert not os.path.exists(profile_store.JSON_PATH)
    from sqlalchemy import text
    with profile_store._sessions()() as session:
        raw = session.execute(text('SELECT data FROM user_profiles WHERE role_type = :r'), {'r': role}).scalar()
    assert 'python' not in raw and profile_store.ENC_KEY in raw
    assert profile_store.delete_profile(role)
    assert profile_store.get_profile(role) is None


def test_alert_dedupe_persists(mysql):
    """Una oferta avisada no se repite en otra corrida aunque venga de otro portal."""
    import job_alerts
    search = job_alerts.create_search({'position': 'Python', 'portals': ['computrabajo'], 'channels': []})
    tag = uuid.uuid4().hex[:8]
    first = [{'Title': f'Dev {tag}', 'Company': 'Acme', 'source': 'computrabajo'}]
    again = [{'title': f'DEV {tag}', 'company': 'ACME', 'source': 'bumeran'},
             {'title': f'QA {tag}', 'company': 'Acme', 'source': 'bumeran'}]
    assert len(job_alerts.filter_new(first, search['id'])) == 1
    assert [j['title'] for j in job_alerts.filter_new(again, search['id'])] == [f'QA {tag}']
    job_alerts.delete_search(search['id'])
    assert job_alerts.get_search(search['id']) is None


def test_tracker_rejects_duplicates(migrated_db):
    """El tracker guarda el empleo y detecta el duplicado por título y empresa."""
    from db_config import DatabaseManager
    db = DatabaseManager()
    db.create_job_tracker_table()
    job = {'title': f'Data Engineer {uuid.uuid4().hex[:8]}', 'company': 'Globant', 'status': 'bookmarked'}
    job_id = db.add_job_to_tracker(job)
    assert isinstance(job_id, int)
    assert db.add_job_to_tracker(job) == {'exists': True, 'job_id': job_id, 'message': 'Job already in tracker'}
    assert any(j['title'] == job['title'] for j in db.get_all_tracked_jobs())


def test_ai_usage_shared_in_redis(monkeypatch):
    """Con RATELIMIT_STORAGE_URI=redis:// el consumo de IA se comparte entre instancias."""
    import ai_usage
    monkeypatch.setenv('RATELIMIT_STORAGE_URI', os.getenv('REDIS_URL', 'redis://127.0.0.1:6379/0'))
    ai_usage.reset()
    before = ai_usage.summary()
    ai_usage.record(120, 30)
    ai_usage.reset()  # otra instancia: storage nuevo, mismo Redis
    after = ai_usage.summary()
    assert after['input_tokens'] - before['input_tokens'] == 120
    assert after['output_tokens'] - before['output_tokens'] == 30
    assert after['calls'] - before['calls'] == 1
    ai_usage.reset()


def test_tracker_reminder_dates_and_marks(migrated_db):
    """Fechas de seguimiento en MySQL: se guardan, entran en los candidatos y se marca el aviso."""
    from datetime import date

    from db_config import DatabaseManager
    from tasks.notification_tasks import due_followups
    db = DatabaseManager()
    job_id = db.add_job_to_tracker({'title': f'SRE {uuid.uuid4().hex[:8]}', 'company': 'Mercado', 'status': 'applied'})
    assert db.update_tracker_dates(job_id, date(2000, 1, 2), None, 'Escribir a RR. HH.')
    job = db.get_tracked_job_by_id(job_id)
    assert (job['follow_up'], job['notes']) == (date(2000, 1, 2), 'Escribir a RR. HH.')
    due = [j for j in due_followups(db.get_followup_candidates(), date.today()) if j['id'] == job_id]
    assert len(due) == 1
    assert db.mark_reminded([job_id])
    assert not [j for j in due_followups(db.get_followup_candidates(), date.today()) if j['id'] == job_id]
    db.delete_tracked_job(job_id)


def test_bookmarked_job_gets_applied_date_when_skipping_applied(migrated_db):
    """Una oferta guardada que pasa directo a entrevista toma la fecha de hoy como postulación."""
    from datetime import date, datetime

    from db_config import DatabaseManager
    db = DatabaseManager()
    job_id = db.add_job_to_tracker({'title': f'QA {uuid.uuid4().hex[:8]}', 'company': 'Despegar',
                                    'status': 'bookmarked', 'date_applied': datetime(2000, 1, 2)})
    assert db.update_job_status(job_id, 'interviewing')
    assert db.get_tracked_job_by_id(job_id)['applied_date'].date() == date.today()
    assert db.update_job_status(job_id, 'accepted')
    assert db.get_tracked_job_by_id(job_id)['applied_date'].date() == date.today()
    db.delete_tracked_job(job_id)


def test_bookmarked_job_rejected_keeps_saved_date(migrated_db):
    """Descartar una oferta guardada no inventa una fecha de postulación."""
    from datetime import datetime

    from db_config import DatabaseManager
    db = DatabaseManager()
    job_id = db.add_job_to_tracker({'title': f'QA {uuid.uuid4().hex[:8]}', 'company': 'Despegar',
                                    'status': 'bookmarked', 'date_applied': datetime(2000, 1, 2)})
    assert db.update_job_status(job_id, 'rejected')
    assert db.get_tracked_job_by_id(job_id)['applied_date'].year == 2000
    db.delete_tracked_job(job_id)


def test_applications_filters_and_connections(migrated_db):
    """Filtros de postulaciones, CSV procesados y empresas excluidas del networking sobre MySQL."""
    from db_config import DatabaseManager
    db = DatabaseManager()
    company = f'Acme {uuid.uuid4().hex[:8]}'
    job_id = db.save_application({'title': 'Backend', 'company': company})
    assert isinstance(job_id, int)
    assert [j['id'] for j in db.get_applications({'company': company, 'status': 'applied'})] == [job_id]
    assert db.save_processed_file(f'{company}.csv', 3, 1)
    assert db.save_processed_file(f'{company}.csv', 4, 2)
    assert company in {c['company'] for c in db.get_companies_for_connections()}
    assert db.exclude_company(company) and db.exclude_company(company)
    assert company not in {c['company'] for c in db.get_companies_for_connections()}
    assert isinstance(db.save_connection_request(company, [job_id]), int)
    assert db.delete_tracked_job(job_id)


def test_accounts_isolate_data(mysql, monkeypatch, tmp_path):
    """Con dos cuentas, cada una ve y modifica solo su tracker, sus perfiles y sus alertas."""
    import accounts
    import job_alerts
    import profile_store
    from db_config import DatabaseManager
    from sqlalchemy import text
    monkeypatch.setattr(profile_store, 'JSON_PATH', str(tmp_path / 'profiles.json'))
    tag = uuid.uuid4().hex[:8]
    ana = accounts.register(f'ana-{tag}@example.com', 'clave-larga-1')
    beto = accounts.register(f'beto-{tag}@example.com', 'clave-larga-2')
    db = DatabaseManager()
    role = f'it_{tag}'
    job = {'title': 'Dev', 'company': f'Iso {tag}', 'job_link': f'https://example.com/{tag}', 'status': 'applied'}
    try:
        with accounts.as_user(ana):
            job_id = db.add_job_to_tracker(job)
            profile_store.save_profile(role, {'name': 'Ana', 'skills': ['python']})
            search_id = job_alerts.create_search({'position': f'python {tag}', 'portals': ['computrabajo']})['id']
        with accounts.as_user(beto):
            assert all(j['id'] != job_id for j in db.get_all_tracked_jobs())
            assert db.get_tracked_job_by_id(job_id) is None
            assert not db.update_job_status(job_id, 'rejected')
            assert not db.delete_tracked_job(job_id)
            assert profile_store.get_profile(role) is None
            assert job_alerts.get_search(search_id) is None
            assert not job_alerts.delete_search(search_id)
            other = db.add_job_to_tracker(job)
            assert isinstance(other, int) and other != job_id, 'el mismo link tiene que poder guardarse en otra cuenta'
            assert db.delete_tracked_job(other)
        with accounts.as_user(ana):
            assert db.get_tracked_job_by_id(job_id)['status'] == 'applied'
            assert profile_store.get_profile(role)['name'] == 'Ana'
            assert job_alerts.delete_search(search_id)
            assert profile_store.delete_profile(role)
            assert db.delete_tracked_job(job_id)
    finally:
        with db.engine.begin() as conn:
            conn.execute(text('DELETE FROM users WHERE id IN (:a, :b)'), {'a': ana, 'b': beto})
