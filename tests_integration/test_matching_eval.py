"""Calidad del matching con TF-IDF real (sin los mocks de sklearn/spaCy de tests/conftest.py)."""
import matching_eval

# Línea base con TF-IDF (scripts/eval_matching.py). Si un cambio en el matching la baja, este test falla.
# P@3 es más baja que con el dataset original: varios CVs tienen una sola oferta buena y P@3 no llega a 1.
BASELINE = {'ndcg@5': 0.93, 'precision@3': 0.70, 'mrr': 0.95}


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


def test_compare_without_gemini_key(monkeypatch, capsys):
    monkeypatch.delenv('GEMINI_API_KEY', raising=False)
    monkeypatch.setenv('MATCHING_BACKEND', 'tfidf')
    from scripts import eval_matching
    assert eval_matching.main(['--compare']) == 0
    out = capsys.readouterr().out
    assert 'tfidf' in out and 'sin GEMINI_API_KEY' in out
    import os
    assert os.environ['MATCHING_BACKEND'] == 'tfidf'
