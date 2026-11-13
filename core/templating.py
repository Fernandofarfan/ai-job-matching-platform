"""
core/templating.py — Templates Jinja2 compartidos + helpers de URL y flash.
Reemplaza render_template/flash/url_for de Flask en FastAPI.
"""
from fastapi import Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from jinja2 import pass_context

templates = Jinja2Templates(directory="templates")


@pass_context
def custom_url_for(context, name: str, **kwargs):
    """url_for compatible con Flask para templates (static y rutas con nombre)."""
    request = context.get('request')
    if not request:
        return ""
    if name == 'static':
        kwargs['path'] = kwargs.pop('filename')
    try:
        return request.url_for(name, **kwargs)
    except Exception:
        # Fallback para rutas sin nombre registrado
        fallback = {'results': '/results', 'index': '/', 'scraper': '/scraper',
                    'profile': '/profile', 'tracker': '/tracker', 'analytics': '/analytics'}
        return fallback.get(name, '/')


templates.env.globals['url_for'] = custom_url_for


# ── Flash messages (reemplazo del flash() de Flask vía session) ───────────────

def flash(request: Request, message: str, category: str = "info") -> None:
    """Guarda un mensaje flash en la sesión (requiere SessionMiddleware)."""
    flashes = request.session.setdefault("_flashes", [])
    flashes.append((category, message))


@pass_context
def get_flashed_messages(context, with_categories: bool = False):
    """Lee y limpia los mensajes flash de la sesión. Se usa en templates."""
    request = context.get('request')
    if request is None:
        return []
    flashes = request.session.pop("_flashes", None)
    if not flashes:
        return []
    if with_categories:
        return flashes
    return [msg for _cat, msg in flashes]


templates.env.globals['get_flashed_messages'] = get_flashed_messages


def redirect(url: str, status_code: int = 303) -> RedirectResponse:
    """Helper equivalente a Flask redirect()."""
    return RedirectResponse(url=url, status_code=status_code)
