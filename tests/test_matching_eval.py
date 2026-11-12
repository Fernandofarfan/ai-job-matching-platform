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
    from resume_parser import jobMatcher
    assert jobMatcher()._extract_required_experience(text) == years


def test_dataset_covers_three_languages():
    jobs = matching_eval.load()['jobs']
    assert any(j.startswith('es_') for j in jobs) and any(j.startswith('pt_') for j in jobs)


def test_company_age_is_not_required_experience():
    from resume_parser import jobMatcher
    m = jobMatcher()
    assert m._extract_required_experience('Empresa con 30 años de experiencia en el mercado. Buscamos dev.') == 0
    assert m._extract_required_experience('Empresa com 25 anos de experiência. Pelo menos 2 anos em Java.') == 2
