"""Métricas y dataset del matching; la línea base con TF-IDF real está en tests_integration/test_matching_eval.py."""
import pytest

import matching_eval


def test_metrics():
    assert matching_eval.ndcg([2, 1, 0]) == pytest.approx(1.0)
    assert matching_eval.ndcg([0, 0, 2]) < matching_eval.ndcg([0, 2, 0]) < 1
    assert matching_eval.ndcg([0, 0]) == 0.0
    assert matching_eval.precision([1, 0, 2, 2]) == pytest.approx(2 / 3)
    assert matching_eval.reciprocal_rank([1, 0, 2]) == pytest.approx(1 / 3)
    assert matching_eval.reciprocal_rank([1, 1]) == 0.0


def test_dataset_labels_point_to_existing_jobs():
    dataset = matching_eval.load()
    for name, profile in dataset['profiles'].items():
        assert set(profile['relevance']) <= set(dataset['jobs']), name
        assert 2 in profile['relevance'].values(), name


@pytest.mark.parametrize('text, years', [
    ('Analista. 3 años de experiencia con SQL.', 3),
    ('Cientista de Dados. 2 anos de experiência com Python.', 2),
    ('Suporte. 1 ano de experiência em help desk.', 1),
    ('Mínimo 4 años en puestos similares.', 4),
    ('Pelo menos 5 anos em vendas.', 5),
    ('Empresa con 30 años en el mercado.', 0),
])
def test_required_experience_in_spanish_and_portuguese(text, years):
    from job_matcher import jobMatcher
    assert jobMatcher()._extract_required_experience(text) == years


def test_dataset_covers_three_languages():
    jobs = matching_eval.load()['jobs']
    assert any(j.startswith('es_') for j in jobs) and any(j.startswith('pt_') for j in jobs)


def test_company_age_is_not_required_experience():
    """Los años de la empresa no se toman como experiencia pedida."""
    from job_matcher import jobMatcher
    m = jobMatcher()
    assert m._extract_required_experience('Empresa con 30 años de experiencia en el mercado. Buscamos dev.') == 0
    assert m._extract_required_experience('Empresa com 25 anos de experiência. Pelo menos 2 anos em Java.') == 2


def test_feedback_dataset_and_report(monkeypatch, capsys):
    """Cada cuenta con marcas suficientes ordena sus ofertas con su último CV; el reporte no dice de quién."""
    monkeypatch.delenv('GEMINI_API_KEY', raising=False)  # el CI la define; sin Gemini entran todas las cuentas
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool

    import accounts
    import job_alerts
    import job_feedback
    import profile_store
    engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
    job_alerts.Base.metadata.create_all(engine)
    job_alerts.configure(sessionmaker(bind=engine))
    cvs = {1: {'viejo': {'raw_text': 'Vendedor', 'upload_date': '2025-01-01'},
               'nuevo': {'raw_text': 'Desarrollador backend con experiencia en Python, Django y PostgreSQL para la web',
                         'skills': ['Python', 'Django', 'PostgreSQL'], 'experience_years': 3,
                         'upload_date': '2026-11-01'}},
           2: {'cv': {'raw_text': 'Data', 'skills': ['SQL']}}}
    monkeypatch.setattr(profile_store, 'get_all_profiles', lambda: cvs.get(accounts.current_user_id()))

    class SkillMatcher:
        """Los tests unitarios corren sin scikit-learn: match = habilidades del CV que nombra la oferta."""
        def calculate_overall_match(self, profile, text):
            return {'overall_match': sum(skill in text for skill in profile['skills'])}

    import job_matcher
    monkeypatch.setattr(job_matcher, 'jobMatcher', SkillMatcher)
    try:
        with accounts.as_user(1):
            for i in range(3):
                job_feedback.set_feedback({'title': f'Backend {i}', 'company': 'Acme'}, True, None,
                                          'Backend developer: Python, Django y PostgreSQL. 2 años de experiencia.')
                job_feedback.set_feedback({'title': f'Ventas {i}', 'company': 'Acme'}, False, None,
                                          'Vendedor de seguros con auto propio, atención al cliente.')
        with accounts.as_user(2):  # una sola marca: no alcanza
            job_feedback.set_feedback({'title': 'Data', 'company': 'Acme'}, True, None, 'SQL')
        dataset = matching_eval.feedback_dataset()
        assert list(dataset['profiles']) == ['cuenta_1_es'] and len(dataset['jobs']) == 6
        profile = dataset['profiles']['cuenta_1_es']
        assert profile['skills'] == ['Python', 'Django', 'PostgreSQL'] and sorted(profile['relevance'].values()) == [0] * 3 + [2] * 3
        result = matching_eval.evaluate(dataset)
        assert result['mean']['ndcg@5'] == pytest.approx(1.0) and result['mean']['precision@3'] == 1.0

        import json

        from scripts import eval_matching
        assert eval_matching.main(['--feedback', '--json', '--min-ndcg', '0.9']) == 0
        report = json.loads(capsys.readouterr().out)
        assert report['accounts'] == 1 and 'profiles' not in report and 'es' in report['by_language']
        assert eval_matching.main(['--feedback', '--min-each', '4']) == 0
        assert 'Ninguna cuenta' in capsys.readouterr().out

        with accounts.as_user(2):  # mismas ofertas que la cuenta 1, con la descripción que guardó cada una
            for i in range(3):
                job_feedback.set_feedback({'title': f'Backend {i}', 'company': 'Acme'}, True, None, 'Analista SQL')
                job_feedback.set_feedback({'title': f'Ventas {i}', 'company': 'Acme'}, False, None, 'Ventas')
        dataset = matching_eval.feedback_dataset()
        assert len(dataset['profiles']) == 2 and len(dataset['jobs']) == 13  # + la marca "Data" de antes
        first = dataset['profiles']['cuenta_1_es']['candidates']
        assert all(dataset['jobs'][j].startswith(('Backend developer', 'Vendedor')) for j in first)

        import embeddings  # con Gemini disponible entran solo las cuentas con permiso de IA
        monkeypatch.setattr(embeddings, 'available', lambda: True)
        monkeypatch.setattr(accounts, 'ai_consent_missing', lambda: accounts.current_user_id() == 2)
        assert list(matching_eval.feedback_dataset()['profiles']) == ['cuenta_1_es']
    finally:
        job_alerts.configure(None)


def test_dataset_size_per_language():
    """Bastantes CVs por idioma para que el promedio de cada idioma signifique algo."""
    dataset = matching_eval.load()
    assert len(dataset['jobs']) >= 35 and len(dataset['profiles']) >= 20
    by_language: dict[str, int] = {}
    for name in dataset['profiles']:
        by_language[matching_eval.language(name)] = by_language.get(matching_eval.language(name), 0) + 1
    assert min(by_language.values()) >= 5, by_language
