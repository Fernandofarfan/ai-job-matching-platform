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
    import resume_parser
    matcher = resume_parser.jobMatcher()
    with mock.patch.object(embeddings, 'similarity', return_value=73.0):
        assert matcher.calculate_text_similarity('cv', 'oferta') == 73.0
    with mock.patch.object(embeddings, 'similarity', return_value=None), \
            mock.patch.object(matcher, 'vectorizer') as vectorizer:
        matcher.calculate_text_similarity('cv', 'oferta')
        vectorizer.fit_transform.assert_called_once()
