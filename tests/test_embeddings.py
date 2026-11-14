"""Matching semántico con embeddings y su fallback a TF-IDF."""
from types import SimpleNamespace
from unittest import mock

import pytest

import ai_usage
import embeddings


class FakeClient:
    """Cliente de google-genai que devuelve un vector fijo por texto y cuenta las llamadas."""

    def __init__(self, vectors=None, error=None):
        self.vectors = vectors or {}
        self.error = error
        self.calls = []
        self.models = self

    def embed_content(self, model, contents, config=None):
        self.calls.append(list(contents))
        if self.error:
            raise self.error
        return SimpleNamespace(embeddings=[
            SimpleNamespace(values=self.vectors.get(t, [1.0, 0.0])) for t in contents
        ])


@pytest.fixture(autouse=True)
def _backend(monkeypatch):
    monkeypatch.setenv('MATCHING_BACKEND', 'embeddings')
    monkeypatch.delenv('MATCHING_BACKEND_BY_LANGUAGE', raising=False)
    monkeypatch.setattr(ai_usage, 'budget_exceeded', lambda: False)
    monkeypatch.setattr(ai_usage, 'record', lambda *a: None)
    yield
    embeddings.configure(None)


def test_cosine():
    """Vectores iguales dan 1, ortogonales 0 y un vector nulo no divide por cero."""
    assert embeddings.cosine([1, 2], [2, 4]) == pytest.approx(1.0)
    assert embeddings.cosine([1, 0], [0, 1]) == 0
    assert embeddings.cosine([0, 0], [1, 1]) == 0


def test_similarity_rescales_cosine():
    """El coseno se reescala entre 0.5 y 0.9 a 0-100."""
    embeddings.configure(FakeClient({'cv': [1.0, 0.0], 'oferta': [0.7, 0.714142842854285]}))
    assert embeddings.similarity('cv', 'oferta') == pytest.approx(50.0, abs=0.1)
    embeddings.configure(FakeClient({'cv': [1.0, 0.0], 'oferta': [0.0, 1.0]}))
    assert embeddings.similarity('cv', 'oferta') == 0.0


def test_cache_avoids_repeated_calls():
    """El CV se embebe una vez aunque se compare con muchas ofertas."""
    client = FakeClient()
    embeddings.configure(client)
    embeddings.similarity('mi cv', 'oferta 1')
    embeddings.similarity('mi cv', 'oferta 2')
    assert client.calls == [['mi cv', 'oferta 1'], ['oferta 2']]


def test_records_estimated_tokens(monkeypatch):
    """Se suma al contador mensual una estimación de ~4 caracteres por token."""
    recorded = []
    monkeypatch.setattr(ai_usage, 'record', lambda i, o: recorded.append((i, o)))
    embeddings.configure(FakeClient())
    embeddings.similarity('a' * 40, 'b' * 40)
    assert recorded == [(20, 0)]


def test_disabled_by_default(monkeypatch):
    """Sin MATCHING_BACKEND=embeddings no se llama a la API."""
    monkeypatch.delenv('MATCHING_BACKEND')
    client = FakeClient()
    embeddings.configure(client)
    assert embeddings.similarity('cv', 'oferta') is None
    assert client.calls == []


def test_budget_exceeded_falls_back(monkeypatch):
    """Con el tope de tokens alcanzado no se llama a la API."""
    monkeypatch.setattr(ai_usage, 'budget_exceeded', lambda: True)
    client = FakeClient()
    embeddings.configure(client)
    assert embeddings.similarity('cv', 'oferta') is None
    assert client.calls == []


def test_api_error_falls_back():
    """Un error de la API devuelve None en vez de propagarse."""
    embeddings.configure(FakeClient(error=RuntimeError('quota')))
    assert embeddings.similarity('cv', 'oferta') is None


def test_job_matcher_prefers_embeddings():
    """jobMatcher usa el puntaje semántico y solo cae a TF-IDF si no hay."""
    import job_matcher
    matcher = job_matcher.jobMatcher()
    with mock.patch.object(embeddings, 'similarity', return_value=73.0):
        assert matcher.calculate_text_similarity('cv', 'oferta') == 73.0
    with mock.patch.object(embeddings, 'similarity', return_value=None), \
            mock.patch.object(matcher, 'vectorizer') as vectorizer:
        matcher.calculate_text_similarity('cv', 'oferta')
        vectorizer.fit_transform.assert_called_once()


def test_eviction_keeps_vectors_of_current_call(monkeypatch):
    """Con la caché llena, el CV (usado recién) no se desaloja y la llamada no falla."""
    monkeypatch.setattr(embeddings, '_CACHE_SIZE', 2)
    client = FakeClient()
    embeddings.configure(client)
    for i in range(5):
        assert embeddings.similarity('mi cv', f'oferta {i}') is not None
    assert client.calls[1:] == [[f'oferta {i}'] for i in range(1, 5)]


CV_ES = 'Desarrollador con cinco años de experiencia en el desarrollo de APIs y los servicios de la empresa'
CV_PT = 'Desenvolvedor com cinco anos de experiência no desenvolvimento de APIs e os serviços da empresa'
CV_EN = 'Developer with five years of experience in the development of APIs and the company services'


def test_detect_language():
    """Detecta el idioma del CV por sus palabras frecuentes; sin pistas, inglés."""
    assert embeddings.detect_language(CV_ES) == 'es'
    assert embeddings.detect_language(CV_PT) == 'pt'
    assert embeddings.detect_language(CV_EN) == 'en'
    assert embeddings.detect_language('Python SQL Docker 2024') == 'en'
    assert embeddings.detect_language('') == 'en'


def test_backends_by_language_ignores_unknown(monkeypatch):
    """Solo cuentan idiomas y backends conocidos."""
    monkeypatch.setenv('MATCHING_BACKEND_BY_LANGUAGE', ' ES = embeddings , pt=tfidf, fr=embeddings, en=bert,, ')
    assert embeddings.backends_by_language() == {'es': 'embeddings', 'pt': 'tfidf'}


def test_embeddings_only_for_configured_languages(monkeypatch):
    """Con MATCHING_BACKEND=tfidf y es/pt=embeddings, solo los CVs en español y portugués llaman a la API."""
    monkeypatch.setenv('MATCHING_BACKEND', 'tfidf')
    monkeypatch.setenv('MATCHING_BACKEND_BY_LANGUAGE', 'es=embeddings,pt=embeddings')
    client = FakeClient()
    embeddings.configure(client)
    assert embeddings.similarity(CV_EN, 'Backend developer') is None
    assert client.calls == []
    assert embeddings.similarity(CV_ES, 'Backend developer') is not None
    assert embeddings.similarity(CV_PT, 'Backend developer') is not None
    assert len(client.calls) == 2


def test_language_override_can_turn_embeddings_off(monkeypatch):
    """Con MATCHING_BACKEND=embeddings, un idioma puede quedarse en TF-IDF."""
    monkeypatch.setenv('MATCHING_BACKEND_BY_LANGUAGE', 'en=tfidf')
    client = FakeClient()
    embeddings.configure(client)
    assert embeddings.similarity(CV_EN, 'Backend developer') is None
    assert embeddings.similarity(CV_ES, 'Backend developer') is not None


def test_by_language_off_by_default(monkeypatch):
    """Sin MATCHING_BACKEND ni MATCHING_BACKEND_BY_LANGUAGE no se llama a la API en ningún idioma."""
    monkeypatch.delenv('MATCHING_BACKEND')
    monkeypatch.delenv('MATCHING_BACKEND_BY_LANGUAGE', raising=False)
    client = FakeClient()
    embeddings.configure(client)
    for cv in (CV_ES, CV_PT, CV_EN):
        assert embeddings.similarity(cv, 'oferta') is None
    assert client.calls == []


def test_by_language_needs_api_key(monkeypatch):
    """Sin GEMINI_API_KEY ni cliente, el idioma configurado sigue en TF-IDF."""
    monkeypatch.setenv('MATCHING_BACKEND', 'tfidf')
    monkeypatch.setenv('MATCHING_BACKEND_BY_LANGUAGE', 'es=embeddings')
    monkeypatch.delenv('GEMINI_API_KEY', raising=False)
    embeddings.configure(None)
    assert not embeddings.enabled('es')
    assert embeddings.similarity(CV_ES, 'oferta') is None


def test_detect_language_matches_eval_dataset():
    """El idioma detectado coincide con el etiquetado de cada CV del dataset de evaluación."""
    import matching_eval
    for name, profile in matching_eval.load()['profiles'].items():
        assert embeddings.detect_language(profile['raw_text']) == matching_eval.language(name), name
