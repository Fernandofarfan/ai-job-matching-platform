"""Interfaz en español, inglés y portugués.

Los textos se escriben en español en las plantillas (`{{ _('Texto') }}`) y los catálogos
`translations/<idioma>.json` los traducen; lo que falta en un catálogo se muestra en español.
El idioma sale de la cookie `lang` (selector de la barra) o, sin ella, de `Accept-Language`.
"""
import json
import os
from contextvars import ContextVar
from functools import cache
from typing import Any

from markupsafe import Markup, escape

DEFAULT = 'es'
LANGUAGES = {'es': 'Español', 'en': 'English', 'pt': 'Português'}
COOKIE = 'lang'
_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'translations')
_current: ContextVar[str] = ContextVar('lang', default=DEFAULT)


@cache
def catalog(lang: str) -> dict[str, Any]:
    """Traducciones de un idioma, con el texto en español como clave."""
    if lang == DEFAULT or lang not in LANGUAGES:
        return {}
    with open(os.path.join(_DIR, f'{lang}.json'), encoding='utf-8') as f:
        data: dict[str, Any] = json.load(f)
    return data


def negotiate(cookie: str | None, accept_language: str | None) -> str:
    """Idioma elegido en la cookie o, si no, el primero soportado de `Accept-Language` (por calidad)."""
    if cookie in LANGUAGES:
        return cookie
    ranked = []
    for i, part in enumerate((accept_language or '').split(',')):
        tag, _, params = part.strip().partition(';')
        try:
            q = float(params.strip()[2:]) if params.strip().startswith('q=') else 1.0
        except ValueError:
            q = 0.0
        if q > 0:
            ranked.append((-q, i, tag.strip().lower()[:2]))
    for _q, _i, lang in sorted(ranked):
        if lang in LANGUAGES:
            return lang
    return DEFAULT


def set_locale(lang: str) -> None:
    """Idioma del pedido en curso."""
    _current.set(lang if lang in LANGUAGES else DEFAULT)


def get_locale() -> str:
    """Idioma del pedido en curso."""
    return _current.get()


def gettext(text: str, **values: Any) -> str:
    """Texto traducido al idioma actual; `%(nombre)s` se completa con `values`."""
    translated = catalog(get_locale()).get(text, text) if text else text
    return translated % values if values else translated


def lazy(text: str, **values: Any) -> dict[str, Any]:
    """Mensaje para traducir al mostrarlo (progreso de búsquedas que arman threads y el worker)."""
    return {'text': text, 'values': values}


def render_message(message: Any) -> str:
    """Texto de un mensaje de `lazy()` (o un texto suelto) en el idioma actual."""
    if isinstance(message, dict) and isinstance(message.get('text'), str):
        return gettext(message['text'], **(message.get('values') or {}))
    return gettext(message) if isinstance(message, str) else message


def jinja_gettext(text: str, **values: Any) -> Markup:
    """`_()` de las plantillas: el texto se escapa y los valores también, salvo los marcados como seguros."""
    if not isinstance(text, str):
        return escape(text)
    translated = Markup(escape(  # noqa: S704 - el texto ya está escapado
        catalog(get_locale()).get(text, text)))
    return translated % values if values else translated
