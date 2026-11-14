"""Tests del contador de tokens, el tope mensual y la caché de Gemini."""
from types import SimpleNamespace
from unittest import mock

import pytest

import ai_engine
import ai_usage


@pytest.fixture(autouse=True)
def _clean_usage(monkeypatch):
    for name in ('AI_MONTHLY_TOKEN_LIMIT', 'AI_CACHE_TTL', 'AI_PRICE_INPUT_PER_MTOK', 'AI_PRICE_OUTPUT_PER_MTOK'):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv('RATELIMIT_STORAGE_URI', 'memory://')
    ai_usage.reset()
    yield
    ai_usage.reset()


def _fake_gemini(monkeypatch, text='respuesta', input_tokens=100, output_tokens=50, thoughts=None):
    response = SimpleNamespace(
        text=text,
        usage_metadata=SimpleNamespace(
            prompt_token_count=input_tokens, candidates_token_count=output_tokens, thoughts_token_count=thoughts,
        ),
    )
    client = mock.Mock()
    client.models.generate_content.return_value = response
    monkeypatch.setattr(ai_engine, 'GEMINI_AVAILABLE', True)
    monkeypatch.setattr(ai_engine, '_gemini_client', client, raising=False)
    monkeypatch.setattr(ai_engine, 'genai_types', mock.Mock(), raising=False)
    return client


def test_call_records_tokens_and_cost(monkeypatch):
    monkeypatch.setenv('AI_PRICE_INPUT_PER_MTOK', '1')
    monkeypatch.setenv('AI_PRICE_OUTPUT_PER_MTOK', '2')
    _fake_gemini(monkeypatch)
    assert ai_engine._call_gemini('hola', temperature=0.8) == 'respuesta'
    usage = ai_usage.summary()
    assert (usage['calls'], usage['input_tokens'], usage['output_tokens']) == (1, 100, 50)
    assert usage['estimated_cost_usd'] == pytest.approx(0.0002)


def test_thinking_tokens_count_as_output(monkeypatch):
    _fake_gemini(monkeypatch, output_tokens=50, thoughts=30)
    ai_engine._call_gemini('pensá', temperature=0.8)
    assert ai_usage.summary()['output_tokens'] == 80


def test_low_temperature_responses_are_cached(monkeypatch):
    client = _fake_gemini(monkeypatch)
    ai_engine._call_gemini('analizá esto', temperature=0.3)
    ai_engine._call_gemini('analizá esto', temperature=0.3)
    assert client.models.generate_content.call_count == 1


def test_creative_responses_are_not_cached(monkeypatch):
    client = _fake_gemini(monkeypatch)
    ai_engine._call_gemini('preguntas', temperature=0.7)
    ai_engine._call_gemini('preguntas', temperature=0.7)
    assert client.models.generate_content.call_count == 2


def test_monthly_limit_blocks_calls_with_gemini_error_prefix(monkeypatch):
    monkeypatch.setenv('AI_MONTHLY_TOKEN_LIMIT', '120')
    client = _fake_gemini(monkeypatch)
    ai_engine._call_gemini('primera', temperature=0.8)
    result = ai_engine._call_gemini('segunda', temperature=0.8)
    assert result.startswith('Error al contactar Gemini')
    assert client.models.generate_content.call_count == 1


def test_invalid_limit_means_no_limit(monkeypatch):
    monkeypatch.setenv('AI_MONTHLY_TOKEN_LIMIT', 'mucho')
    assert ai_usage.monthly_limit() == 0
    assert not ai_usage.budget_exceeded()


def test_usage_endpoint(client):
    ai_usage.record(10, 5)
    data = client.get('/api/ai/usage').get_json()
    assert data['success'] and data['usage']['total_tokens'] == 15


def _ai_parser(response):
    """resumeParser con IA activa y un cliente de Gemini simulado."""
    from resume_parser import resumeParser
    parser = resumeParser.__new__(resumeParser)
    parser.use_ai = True
    parser.model_name = 'gemini-test'
    parser.client = mock.Mock()
    parser.client.models.generate_content.return_value = response
    return parser


def test_resume_parser_records_tokens():
    """parse_with_ai suma entrada, salida y razonamiento al contador mensual."""
    response = SimpleNamespace(
        text='```json\n{"skills": ["python"]}\n```',
        usage_metadata=SimpleNamespace(
            prompt_token_count=200, candidates_token_count=30, thoughts_token_count=20,
        ),
    )
    assert _ai_parser(response).parse_with_ai('CV') == {'skills': ['python']}
    usage = ai_usage.summary()
    assert (usage['input_tokens'], usage['output_tokens']) == (200, 50)


def test_resume_parser_skips_ai_over_budget(monkeypatch):
    """Con el tope alcanzado no se llama a Gemini y se usa el parser local."""
    monkeypatch.setenv('AI_MONTHLY_TOKEN_LIMIT', '100')
    ai_usage.record(90, 20)
    parser = _ai_parser(SimpleNamespace(text='{}', usage_metadata=None))
    assert parser.parse_with_ai('CV') is None
    parser.client.models.generate_content.assert_not_called()
