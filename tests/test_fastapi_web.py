"""Páginas de FastAPI con la misma sesión, CSRF, avisos y URLs que Flask (fastapi_web.py)."""
import re

from fastapi import Request
from fastapi.routing import APIRoute

import auth
import fastapi_web


def _add_route(client, path, endpoint):
    """Ruta de prueba antes del montaje de Flask en `/` (que atrapa todo lo demás)."""
    client.app.router.routes.insert(0, APIRoute(path, endpoint))


def _csrf(html):
    return re.search(r'name="csrf-token" content="([^"]+)"', html).group(1)


def test_csrf_token_from_fastapi_page_is_valid_in_flask(client, app, monkeypatch):
    """El token que pone una página de FastAPI sirve para un POST de Flask (misma sesión, mismo formato)."""
    monkeypatch.setitem(app.config, 'WTF_CSRF_ENABLED', True)
    token = _csrf(client.get('/').get_data(as_text=True))
    assert client.post('/logout').status_code == 400
    assert client.post('/logout', data={'csrf_token': token}).status_code == 302


def test_flash_from_fastapi_is_shown_once_and_readable_by_flask(client, app):
    """Los avisos van a `_flashes` de la cookie de Flask y se muestran una sola vez."""
    def flash_and_redirect(request: Request):
        fastapi_web.flash(request, 'Aviso de prueba', 'info')
        return fastapi_web.redirect(request, '/')
    _add_route(client, '/_flash', flash_and_redirect)

    assert client.get('/_flash').status_code == 302
    data = auth.load_session_cookie(app, client._c.cookies.get('session'))
    assert data['_flashes'] == [('info', 'Aviso de prueba')]
    assert 'Aviso de prueba' in client.get('/').get_data(as_text=True)
    assert 'Aviso de prueba' not in client.get('/').get_data(as_text=True)


def test_url_for_covers_fastapi_flask_and_static(client):
    """url_for arma rutas de FastAPI y de Flask; lo que no es parámetro va en la query."""
    def urls(request: Request):
        return {'lang': fastapi_web.url_for(request, 'set_language', code='en', next='/x'),
                'flask': fastapi_web.url_for(request, 'alerts'),
                'static': fastapi_web.url_for(request, 'static', filename='css/app.css')}
    _add_route(client, '/_urls', urls)

    assert client.get('/_urls').get_json() == {'lang': '/lang/en?next=/x', 'flask': '/alerts',
                                               'static': '/static/css/app.css'}


def test_flask_url_for_still_builds_migrated_pages(app):
    """Flask conserva las URLs de las páginas que ya atiende FastAPI (reglas solo para armar URLs)."""
    urls = app.url_map.bind('localhost')
    assert urls.build('index') == '/'
    assert urls.build('tracker') == '/tracker'
    assert urls.build('set_language', {'code': 'pt', 'next': '/login'}) == '/lang/pt?next=/login'


def test_language_selector_served_by_fastapi(client):
    """/lang guarda la cookie y vuelve solo a rutas locales."""
    response = client.get('/lang/en', query_string={'next': '/login'})
    assert response.status_code == 302 and response.headers['location'] == '/login'
    assert 'lang=en' in response.headers['set-cookie']
    assert client.get('/lang/en', query_string={'next': '//evil.example'}).headers['location'] == '/'


def test_service_worker_from_root(client):
    response = client.get('/sw.js')
    assert response.status_code == 200
    assert response.mimetype == 'application/javascript'
    assert response.headers['cache-control'] == 'no-cache'


def test_language_links_keep_current_fastapi_page(client):
    """El selector de idioma de una página de FastAPI vuelve a esa página (con su query)."""
    html = client.get('/results?x=1').get_data(as_text=True)
    assert '?next=/results%3Fx%3D1' in html


def test_permanent_session_is_renewed_on_fastapi_pages(client, app):
    """Como Flask, una sesión permanente renueva la cookie en cada página aunque no cambie."""
    cookie = app.session_interface.get_signing_serializer(app).dumps({'_permanent': True, 'n': 1})
    client._c.cookies.set('session', cookie)
    renewed = re.search(r'session=([^;]+);.*expires=', client.get('/').headers.get('set-cookie', ''), re.I)
    assert renewed and auth.load_session_cookie(app, renewed.group(1).strip('"'))['n'] == 1
