"""Cliente de OpenCode: proveedor elegido, pedido compatible con OpenAI, tokens y errores."""
from unittest import mock

import httpx
import pytest

import ai_engine
import ai_usage
import opencode_client


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    for name in ('AI_PROVIDER', 'OPENCODE_API_KEY', 'OPENCODE_BASE_URL', 'OPENCODE_MODEL', 'OPENCODE_LIGHT_MODEL',
                 'OPENCODE_MAX_TOKENS', 'AI_MONTHLY_TOKEN_LIMIT', 'AI_CACHE_TTL'):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv('RATELIMIT_STORAGE_URI', 'memory://')
    ai_usage.reset()
    yield
    ai_usage.reset()


def _response(status=200, payload=None):
    return httpx.Response(status, json=payload if payload is not None else {
        'choices': [{'message': {'content': ' hola '}}],
        'usage': {'prompt_tokens': 12, 'completion_tokens': 30},
    }, request=httpx.Request('POST', 'https://opencode.ai/zen/go/v1/chat/completions'))


def test_provider_follows_key_and_explicit_choice(monkeypatch):
    assert opencode_client.provider() == 'gemini' and not opencode_client.enabled()
    monkeypatch.setenv('OPENCODE_API_KEY', 'k')
    assert opencode_client.provider() == 'opencode' and opencode_client.enabled()
    monkeypatch.setenv('AI_PROVIDER', 'gemini')
    assert opencode_client.provider() == 'gemini' and not opencode_client.enabled()
    monkeypatch.setenv('AI_PROVIDER', 'opencode')
    monkeypatch.delenv('OPENCODE_API_KEY')
    assert opencode_client.provider() == 'opencode' and not opencode_client.enabled()


def test_models_default_and_override(monkeypatch):
    assert (opencode_client.model(), opencode_client.light_model()) == ('glm-5.3', 'glm-5.3-flash')
    monkeypatch.setenv('OPENCODE_MODEL', 'kimi-k3')
    monkeypatch.setenv('OPENCODE_LIGHT_MODEL', 'qwen3.8-flash')
    assert (opencode_client.model(), opencode_client.light_model()) == ('kimi-k3', 'qwen3.8-flash')


def test_chat_sends_openai_request_with_session(monkeypatch):
    monkeypatch.setenv('OPENCODE_API_KEY', 'clave')
    monkeypatch.setenv('OPENCODE_BASE_URL', 'https://opencode.ai/zen/v1/')
    with mock.patch('httpx.post', return_value=_response()) as post:
        reply = opencode_client.chat('prompt', 'glm-5.3', temperature=0.2)
    assert reply == ('hola', 12, 30)
    url = post.call_args.args[0]
    kwargs = post.call_args.kwargs
    assert url == 'https://opencode.ai/zen/v1/chat/completions'
    assert kwargs['headers']['Authorization'] == 'Bearer clave'
    assert kwargs['headers']['x-opencode-session'].startswith('empleoia-')
    assert kwargs['json']['model'] == 'glm-5.3' and kwargs['json']['temperature'] == 0.2
    assert kwargs['json']['messages'] == [{'role': 'user', 'content': 'prompt'}]
    assert kwargs['json']['max_tokens'] == 4096


def test_chat_errors_do_not_include_the_key(monkeypatch):
    monkeypatch.setenv('OPENCODE_API_KEY', 'secreta')
    error = _response(401, {'error': {'type': 'auth', 'message': 'Invalid API key'}})
    with mock.patch('httpx.post', return_value=error), pytest.raises(opencode_client.OpenCodeError) as exc:
        opencode_client.chat('p', 'glm-5.3')
    assert 'HTTP 401' in str(exc.value) and 'secreta' not in str(exc.value)
    with mock.patch('httpx.post', side_effect=httpx.ConnectTimeout('x')), \
            pytest.raises(opencode_client.OpenCodeError, match='ConnectTimeout'):
        opencode_client.chat('p', 'glm-5.3')
    with mock.patch('httpx.post', return_value=_response(200, {'choices': []})), \
            pytest.raises(opencode_client.OpenCodeError):
        opencode_client.chat('p', 'glm-5.3')


def test_ai_engine_uses_opencode_and_records_tokens(monkeypatch):
    monkeypatch.setattr(ai_engine, 'AI_PROVIDER', 'opencode')
    monkeypatch.setattr(ai_engine, 'GEMINI_AVAILABLE', True)
    monkeypatch.setattr(ai_engine, 'AI_MODEL', 'glm-5.3')
    with mock.patch('accounts.ai_consent_missing', return_value=False), \
            mock.patch.object(opencode_client, 'chat', return_value=opencode_client.Reply('texto', 7, 9)) as chat:
        assert ai_engine._call_gemini('carta', temperature=0.7) == 'texto'
    chat.assert_called_once_with('carta', 'glm-5.3', 0.7)
    usage = ai_usage.summary()
    assert (usage['input_tokens'], usage['output_tokens']) == (7, 9)


def test_ai_engine_reports_opencode_failures(monkeypatch):
    monkeypatch.setattr(ai_engine, 'AI_PROVIDER', 'opencode')
    monkeypatch.setattr(ai_engine, 'GEMINI_AVAILABLE', True)
    with mock.patch('accounts.ai_consent_missing', return_value=False):
        with mock.patch.object(opencode_client, 'chat', side_effect=opencode_client.OpenCodeError('HTTP 429: x')):
            assert ai_engine._call_gemini('a', temperature=0.7).startswith(ai_engine.GEMINI_ERROR_PREFIX)
        with mock.patch.object(opencode_client, 'chat', return_value=opencode_client.Reply('', 1, 1)):
            assert ai_engine._call_gemini('b', temperature=0.7) == f'{ai_engine.GEMINI_ERROR_PREFIX}: respuesta vacía'


def test_resume_parser_uses_opencode(monkeypatch):
    from resume_parser import resumeParser
    monkeypatch.setenv('OPENCODE_API_KEY', 'k')
    parser = resumeParser.__new__(resumeParser)
    parser.configure_genai()
    assert parser.use_ai and parser.provider == 'opencode' and parser.model_name == 'glm-5.3-flash'
    reply = opencode_client.Reply('```json\n{"skills": ["python"]}\n```', 100, 20)
    with mock.patch('accounts.ai_consent_missing', return_value=False), \
            mock.patch.object(opencode_client, 'chat', return_value=reply) as chat:
        assert parser.parse_with_ai('CV') == {'skills': ['python']}
    assert chat.call_args.args[1] == 'glm-5.3-flash'
    usage = ai_usage.summary()
    assert (usage['input_tokens'], usage['output_tokens']) == (100, 20)


def test_pages_name_the_configured_provider(monkeypatch):
    import fastapi_web
    assert fastapi_web.ai_provider_name() == 'Google Gemini'
    monkeypatch.setenv('OPENCODE_API_KEY', 'k')
    assert fastapi_web.ai_provider_name() == 'OpenCode'
