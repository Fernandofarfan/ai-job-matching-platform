"""Cliente de OpenCode (API compatible con OpenAI) para las funciones de IA generativa.

Se usa en lugar de Gemini con AI_PROVIDER=opencode, o sin AI_PROVIDER cuando hay OPENCODE_API_KEY.
Por defecto apunta al plan OpenCode Go; OPENCODE_BASE_URL=https://opencode.ai/zen/v1 usa los créditos de Zen.
"""
import os
import uuid
from typing import Any, NamedTuple

import httpx

DEFAULT_BASE_URL = 'https://opencode.ai/zen/go/v1'
# Modelos con retención cero según https://opencode.ai/docs/go/ (el texto del CV no queda guardado)
DEFAULT_MODEL = 'glm-5.3'
DEFAULT_LIGHT_MODEL = 'glm-5.3-flash'
TIMEOUT = 180.0


class Reply(NamedTuple):
    """Texto de la respuesta y tokens de entrada y de salida (razonamiento incluido)."""

    text: str
    input_tokens: int
    output_tokens: int


class OpenCodeError(Exception):
    """La API respondió con error o sin texto; el mensaje no incluye la clave."""


def provider() -> str:
    """'opencode' o 'gemini': AI_PROVIDER si está; si no, OpenCode cuando hay OPENCODE_API_KEY."""
    explicit = os.getenv('AI_PROVIDER', '').strip().lower()
    if explicit in ('opencode', 'gemini'):
        return explicit
    return 'opencode' if os.getenv('OPENCODE_API_KEY') else 'gemini'


def enabled() -> bool:
    """True si las funciones de IA generativa usan OpenCode y hay clave."""
    return provider() == 'opencode' and bool(os.getenv('OPENCODE_API_KEY'))


def model() -> str:
    """Modelo para cartas, CVs, Copilot y análisis."""
    return os.getenv('OPENCODE_MODEL', '').strip() or DEFAULT_MODEL


def light_model() -> str:
    """Modelo barato para extraer datos o clasificar (salarios, correos, CVs)."""
    return os.getenv('OPENCODE_LIGHT_MODEL', '').strip() or DEFAULT_LIGHT_MODEL


def _max_tokens() -> int:
    """Tope de salida; incluye el razonamiento de los modelos que piensan antes de responder."""
    try:
        return max(256, int(os.getenv('OPENCODE_MAX_TOKENS', '4096')))
    except ValueError:
        return 4096


def chat(prompt: str, model_name: str, temperature: float = 0.7) -> Reply:
    """Manda el prompt como un único mensaje de usuario y devuelve el texto y los tokens usados."""
    base_url = (os.getenv('OPENCODE_BASE_URL', '').strip() or DEFAULT_BASE_URL).rstrip('/')
    body: dict[str, Any] = {
        'model': model_name,
        'messages': [{'role': 'user', 'content': prompt}],
        'temperature': temperature,
        'max_tokens': _max_tokens(),
        'reasoning_effort': 'low',  # sin esto el razonamiento puede gastar todo max_tokens
    }
    headers = {
        'Authorization': f"Bearer {os.getenv('OPENCODE_API_KEY', '')}",
        # OpenCode Go rechaza pedidos sin sesión; cada llamada es una conversación nueva
        'x-opencode-session': f'empleoia-{uuid.uuid4().hex}',
    }
    try:
        response = httpx.post(f'{base_url}/chat/completions', json=body, headers=headers, timeout=TIMEOUT)
    except httpx.HTTPError as e:
        raise OpenCodeError(f'{type(e).__name__}') from e
    try:
        data = response.json()
    except ValueError:
        data = {}
    if response.status_code >= 400 or not isinstance(data, dict) or 'error' in data:
        error = data.get('error') if isinstance(data, dict) else None
        detail = error.get('message') if isinstance(error, dict) else None
        raise OpenCodeError(f'HTTP {response.status_code}: {detail or "respuesta inválida"}')
    try:
        text = data['choices'][0]['message'].get('content') or ''
    except (KeyError, IndexError, TypeError, AttributeError) as e:
        raise OpenCodeError('respuesta sin choices') from e
    usage = data.get('usage') or {}
    return Reply(str(text).strip(), int(usage.get('prompt_tokens') or 0), int(usage.get('completion_tokens') or 0))
