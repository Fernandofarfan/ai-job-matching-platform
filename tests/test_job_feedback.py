""""Me interesa / no me interesa": guardado por cuenta, alertas, ranking y medición del matching."""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import accounts
import job_alerts
import job_feedback
import job_ranking


@pytest.fixture
def db():
    """Marcas sobre SQLite en memoria."""
    engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
    job_alerts.Base.metadata.create_all(engine)
    job_alerts.configure(sessionmaker(bind=engine))
    yield
    job_alerts.configure(None)


def _job(title, company='Acme', **extra):
    return {'Title': title, 'Company': company, 'Location': 'CABA', 'Job_Link': f'https://x/{title}', **extra}


def test_set_change_and_clear(db):
    """Se guarda, se cambia de lado y con None se borra; la misma oferta en otro portal es la misma."""
    with accounts.as_user(1):
        job_feedback.set_feedback(_job('Backend Python'), True, 87)
        assert job_feedback.states([_job('Backend Python'), _job('Otra')]) == [True, None]
        job_feedback.set_feedback({'title': 'backend python', 'company': 'ACME'}, False)
        assert job_feedback.states([_job('Backend Python')]) == [False]
        job_feedback.set_feedback(_job('Backend Python'), None)
        assert job_feedback.states([_job('Backend Python')]) == [None]


def test_marks_are_per_account(db):
    """Lo que marca una cuenta no aparece en otra."""
    with accounts.as_user(1):
        job_feedback.set_feedback(_job('Backend Python'), False)
    with accounts.as_user(2):
        assert job_feedback.states([_job('Backend Python')]) == [None]
        assert job_feedback.drop_rejected([_job('Backend Python')]) == [_job('Backend Python')]
        assert job_feedback.examples() == []


def test_drop_rejected_keeps_interested_and_unmarked(db):
    """Las alertas no vuelven a mandar lo marcado "no me interesa"."""
    with accounts.as_user(1):
        job_feedback.set_feedback(_job('Vendedor'), False)
        job_feedback.set_feedback(_job('Backend Python'), True)
        kept = job_feedback.drop_rejected([_job('Vendedor'), _job('Backend Python'), _job('Data')])
    assert [j['Title'] for j in kept] == ['Backend Python', 'Data']


def test_rejects_job_without_title_and_bad_scores(db):
    """Sin título no se guarda; un match fuera de 0-100 queda vacío."""
    with accounts.as_user(1):
        with pytest.raises(ValueError):
            job_feedback.set_feedback({'company': 'Acme'}, True)
        job_feedback.set_feedback(_job('Data'), True, 'abc')
        job_feedback.set_feedback(_job('QA'), True, 250)
        assert job_feedback.my_agreement() == {'interested': 2, 'not_interested': 0, 'match_auc': None}


def test_agreement_auc():
    """AUC: 1 si todo "me interesa" tiene más match, 0,5 con empates, None si falta un lado."""
    rows = [{'interested': True, 'match_score': 90}, {'interested': True, 'match_score': 70},
            {'interested': False, 'match_score': 60}, {'interested': False, 'match_score': None}]
    assert job_feedback.agreement(rows) == {'interested': 2, 'not_interested': 2, 'match_auc': 1.0}
    tie = [{'interested': True, 'match_score': 50}, {'interested': False, 'match_score': 50}]
    assert job_feedback.agreement(tie)['match_auc'] == 0.5
    assert job_feedback.agreement(rows[:2])['match_auc'] is None


def test_all_agreement_mixes_accounts(db):
    """La medición global junta todas las cuentas."""
    with accounts.as_user(1):
        job_feedback.set_feedback(_job('A'), True, 80)
    with accounts.as_user(2):
        job_feedback.set_feedback(_job('B'), False, 40)
    assert job_feedback.all_agreement() == {'interested': 1, 'not_interested': 1, 'match_auc': 1.0}


def test_feedback_trains_ranking():
    """3 "me interesa" y 3 "no me interesa" alcanzan para personalizar, con peso doble."""
    jobs = [{'title': f'Backend Python {i}', 'company': 'Acme', 'interested': True} for i in range(2)]
    jobs += [{'title': f'Vendedor {i}', 'company': 'Tienda', 'interested': False} for i in range(2)]
    assert job_ranking.label(jobs[0]) == 2 and job_ranking.label(jobs[-1]) == -2
    model = job_ranking.train(jobs)
    assert model is not None and model['n_pos'] == 4 and model['n_neg'] == 4
    assert job_ranking.preference(model, {'title': 'Python Developer'}) > 50
    assert job_ranking.preference(model, {'title': 'Vendedor de salón'}) < 50


def test_ranking_model_is_cached_per_account(monkeypatch):
    """El modelo cacheado de una cuenta no se usa para otra."""
    calls = []
    monkeypatch.setattr(job_ranking, '_cache', {})
    monkeypatch.setattr(job_feedback, 'examples', lambda: calls.append(accounts.current_user_id()) or [])
    import types

    import db_config
    monkeypatch.setattr(db_config, 'db_manager', types.SimpleNamespace(get_applications=lambda *a, **k: []))
    with accounts.as_user(1):
        job_ranking.load_model()
        job_ranking.load_model()
    with accounts.as_user(2):
        job_ranking.load_model()
        job_ranking.invalidate()
        job_ranking.load_model()
    assert calls == [1, 2, 2]


def test_api_job_feedback(client, monkeypatch):
    """La API guarda la marca, valida los datos y descarta el ranking cacheado."""
    saved, invalidated = [], []
    monkeypatch.setattr(job_feedback, 'set_feedback', lambda job, value, score=None: saved.append((job, value, score)))
    monkeypatch.setattr(job_ranking, 'invalidate', lambda: invalidated.append(True))
    body = {'job': {'title': 'Backend'}, 'interested': False, 'match_score': 42}
    response = client.post('/api/job_feedback', json=body)
    assert response.status_code == 200 and response.get_json() == {'success': True, 'interested': False}
    assert saved == [({'title': 'Backend'}, False, 42)] and invalidated == [True]
    assert client.post('/api/job_feedback', json={'job': {'title': 'x'}, 'interested': 'si'}).status_code == 400
    assert client.post('/api/job_feedback', json={'job': 'x', 'interested': True}).status_code == 400
