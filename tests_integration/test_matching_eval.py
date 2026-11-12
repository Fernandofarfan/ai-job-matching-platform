"""Calidad del matching con TF-IDF real (sin los mocks de sklearn/spaCy de tests/conftest.py)."""
import matching_eval

# Línea base con TF-IDF (scripts/eval_matching.py). Si un cambio en el matching la baja, este test falla.
BASELINE = {'ndcg@5': 0.93, 'precision@3': 0.80, 'mrr': 0.95}


def test_matching_quality_does_not_regress(monkeypatch):
    monkeypatch.setenv('MATCHING_BACKEND', 'tfidf')
    mean = matching_eval.evaluate()['mean']
    for metric, minimum in BASELINE.items():
        assert mean[metric] >= minimum, f'{metric} bajó a {mean[metric]:.3f} (mínimo {minimum})'


def test_script_exit_code(monkeypatch, capsys):
    monkeypatch.setenv('MATCHING_BACKEND', 'tfidf')
    from scripts import eval_matching
    assert eval_matching.main([]) == 0
    assert 'promedio' in capsys.readouterr().out
    assert eval_matching.main(['--min-ndcg', '1.01', '--json']) == 1
