"""Calidad del matching con TF-IDF real (sin los mocks de sklearn de tests/conftest.py)."""
import json

import matching_eval

# Línea base con TF-IDF (scripts/eval_matching.py). Si un cambio en el matching la baja, este test falla.
# P@3 es más baja que con el dataset original: varios CVs tienen una sola oferta buena y P@3 no llega a 1.
# Con 24 CVs y 38 ofertas el promedio baja: los perfiles nuevos tienen ofertas parecidas de otras áreas.
BASELINE = {'ndcg@5': 0.89, 'precision@3': 0.75, 'mrr': 0.95}
# Mínimo por CV: que un perfil empeore aunque el promedio no baje también frena el CI.
MIN_PROFILE = {'ndcg@5': 0.70, 'mrr': 1.0}


def test_matching_quality_does_not_regress(monkeypatch):
    monkeypatch.setenv('MATCHING_BACKEND', 'tfidf')
    mean = matching_eval.evaluate()['mean']
    for metric, minimum in BASELINE.items():
        assert mean[metric] >= minimum, f'{metric} bajó a {mean[metric]:.3f} (mínimo {minimum})'


def test_each_profile_meets_minimum(monkeypatch):
    monkeypatch.setenv('MATCHING_BACKEND', 'tfidf')
    profiles = matching_eval.evaluate()['profiles']
    below = {f'{name} {metric}={m[metric]:.3f}' for name, m in profiles.items()
             for metric, minimum in MIN_PROFILE.items() if m[metric] < minimum}
    assert not below, f'CVs por debajo del mínimo {MIN_PROFILE}: {sorted(below)}'


def test_script_exit_code(monkeypatch, capsys):
    monkeypatch.setenv('MATCHING_BACKEND', 'tfidf')
    from scripts import eval_matching
    assert eval_matching.main([]) == 0
    assert 'promedio' in capsys.readouterr().out
    assert eval_matching.main(['--min-ndcg', '1.01', '--json']) == 1
    assert eval_matching.main(['--min-profile-ndcg', str(MIN_PROFILE['ndcg@5'])]) == 0
    assert eval_matching.main(['--min-profile-ndcg', '0.95']) == 1
    assert 'Por debajo de 0.95' in capsys.readouterr().out


def test_compare_without_gemini_key(monkeypatch, capsys):
    """Sin GEMINI_API_KEY, --compare mide TF-IDF y avisa que no mide embeddings."""
    monkeypatch.delenv('GEMINI_API_KEY', raising=False)
    monkeypatch.setenv('MATCHING_BACKEND', 'tfidf')
    from scripts import eval_matching
    assert eval_matching.main(['--compare']) == 0
    out = capsys.readouterr().out
    assert 'tfidf' in out and 'sin GEMINI_API_KEY' in out
    import os
    assert os.environ['MATCHING_BACKEND'] == 'tfidf'


def test_compare_honors_json_and_threshold(monkeypatch, capsys):
    """--compare respeta --json y --min-ndcg."""
    monkeypatch.delenv('GEMINI_API_KEY', raising=False)
    from scripts import eval_matching
    assert eval_matching.main(['--compare', '--json', '--min-ndcg', '1.01']) == 1
    out = json.loads(capsys.readouterr().out)
    assert 'mean' in out['tfidf'] and 'skipped' in out['embeddings']
    assert eval_matching.main(['--compare', '--min-profile-ndcg', '0.95']) == 1
    assert 'tfidf: por debajo de 0.95' in capsys.readouterr().out
    assert eval_matching.main(['--compare', '--json', '--min-profile-ndcg', '0.95']) == 1
    assert 'seguridad_es' in json.loads(capsys.readouterr().out)['below_min_profile_ndcg']['tfidf']
    assert eval_matching.main(['--compare', '--min-profile-ndcg', str(MIN_PROFILE['ndcg@5'])]) == 0


def test_compare_does_not_report_tfidf_as_embeddings(monkeypatch, capsys):
    """Si embeddings cae a TF-IDF, --compare no lo informa como embeddings."""
    import embeddings
    monkeypatch.setattr(embeddings, 'enabled', lambda language=None: True)
    monkeypatch.setattr(embeddings, 'embed', lambda texts: None)
    from scripts import eval_matching
    assert eval_matching.main(['--compare', '--json']) == 0
    out = json.loads(capsys.readouterr().out)
    assert 'cayeron a TF-IDF' in out['embeddings']['skipped']


class _FakeGemini:
    """Cliente de embeddings determinístico: trigramas de letras en 64 dimensiones (sin red)."""

    def __init__(self):
        """`client.models.embed_content` apunta a este mismo objeto."""
        self.models = self
        self.calls = 0

    def embed_content(self, model, contents, config):
        """Respuesta con la forma de google-genai: `.embeddings[i].values`."""
        from types import SimpleNamespace
        self.calls += 1

        def vector(text):
            """Conteo de trigramas de letras, agrupados en 64 posiciones."""
            values = [0.0] * 64
            text = text.lower()
            for i in range(len(text) - 2):
                values[sum(map(ord, text[i:i + 3])) % 64] += 1
            return SimpleNamespace(values=values)
        return SimpleNamespace(embeddings=[vector(t) for t in contents])


def test_compare_measures_embeddings_by_language(monkeypatch, capsys):
    """Con un cliente de embeddings, --compare mide los dos backends por idioma y su diferencia."""
    import embeddings
    fake = _FakeGemini()
    embeddings.configure(fake)
    monkeypatch.setenv('GEMINI_API_KEY', 'prueba')
    try:
        from scripts import eval_matching
        assert eval_matching.main(['--compare', '--json']) == 0
        out = json.loads(capsys.readouterr().out)
        assert fake.calls > 0
        assert set(out['tfidf']['by_language']) == set(out['embeddings']['by_language']) == {'en', 'es', 'pt'}
        delta = out['delta']['mean']['ndcg@5']
        assert abs(delta - (out['embeddings']['mean']['ndcg@5'] - out['tfidf']['mean']['ndcg@5'])) < 1e-9
        assert eval_matching.main(['--compare']) == 0
        assert 'delta' in capsys.readouterr().out
    finally:
        embeddings.configure(None)


def test_language_of_ids():
    """El idioma sale del prefijo o sufijo del id."""
    ids = ('qa_es', 'es_qa', 'frontend_pt', 'pt_fe', 'ux')
    assert [matching_eval.language(n) for n in ids] == ['es', 'es', 'pt', 'pt', 'en']


def test_compare_ignores_backend_by_language(monkeypatch, capsys):
    """--compare mide cada backend puro aunque haya MATCHING_BACKEND_BY_LANGUAGE, y después lo restaura."""
    import os

    import embeddings
    fake = _FakeGemini()
    embeddings.configure(fake)
    monkeypatch.setenv('GEMINI_API_KEY', 'prueba')
    monkeypatch.setenv('MATCHING_BACKEND_BY_LANGUAGE', 'es=embeddings,pt=embeddings')
    try:
        from scripts import eval_matching
        assert eval_matching.main(['--compare', '--json']) == 0
        out = json.loads(capsys.readouterr().out)
        monkeypatch.setenv('MATCHING_BACKEND', 'tfidf')
        monkeypatch.delenv('MATCHING_BACKEND_BY_LANGUAGE')
        assert out['tfidf']['mean'] == json.loads(json.dumps(matching_eval.evaluate()['mean']))
    finally:
        embeddings.configure(None)
    assert os.environ.get('MATCHING_BACKEND_BY_LANGUAGE') is None
