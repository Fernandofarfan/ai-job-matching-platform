"""Páginas de FastAPI: sesión, CSRF, avisos y URLs compatibles con lo que dejaba Flask (fastapi_web.py)."""
from unittest import mock
import re

from fastapi import Request
from fastapi.routing import APIRoute

import auth
import fastapi_web


def _add_route(client, path, endpoint):
    """Ruta de prueba agregada al principio del router."""
    client.app.router.routes.insert(0, APIRoute(path, endpoint))


def _csrf(html):
    return re.search(r'name="csrf-token" content="([^"]+)"', html).group(1)


def test_csrf_token_from_page_is_valid_in_json_api(client, app, monkeypatch):
    """El token que pone una página sirve para un POST JSON (misma sesión, mismo formato)."""
    monkeypatch.setitem(app.config, 'WTF_CSRF_ENABLED', True)
    token = _csrf(client.get('/').get_data(as_text=True))
    body = {'applied_jobs': {}}
    assert client.post('/api/save_applications', json=body).status_code == 400
    assert client.post('/api/save_applications', json=body, headers={'X-CSRFToken': token}).status_code != 400


def test_fastapi_auth_forms_check_csrf(client, app, monkeypatch):
    """Login y logout en FastAPI rechazan el POST sin token, como CSRFProtect de Flask."""
    monkeypatch.setitem(app.config, 'WTF_CSRF_ENABLED', True)
    token = _csrf(client.get('/').get_data(as_text=True))
    assert client.post('/logout').status_code == 400
    assert client.post('/login', data={'email': 'a@b.c', 'password': 'x'}).status_code == 400
    assert client.post('/logout', data={'csrf_token': token}).status_code == 302
    assert client.post('/logout', data={'csrf_token': 'otro'}).status_code == 400


def test_auth_pages_are_served_by_fastapi(client, app):
    """Login, registro, recuperación, segundo factor y Google ya no son vistas de Flask."""
    moved = {'login', 'register', 'logout', 'forgot_password', 'login_two_factor', 'google_login', 'google_callback'}
    for name in moved:
        assert client.app.url_path_for(name)
    assert client.app.url_path_for('reset_password', token='t') == '/reset_password/t'
    assert client.app.url_path_for('verify_email', token='t') == '/verify_email/t'


def test_logout_clears_session_and_offline_data(client, app):
    """Salir borra la sesión y pide al navegador borrar el caché offline."""
    client._c.cookies.set('session', app.session_serializer().dumps({'uid': 1, 'x': 1}))
    response = client.post('/logout')
    assert response.status_code == 302 and response.headers['location'].endswith('/login')
    assert response.headers['Clear-Site-Data'] == '"cache", "storage"'
    cookie = re.search(r'session=([^;]*)', response.headers.get('set-cookie', ''))
    assert cookie is None or 'uid' not in auth.load_session_cookie(app, cookie.group(1).strip('"'))


def test_safe_next_only_allows_local_pages():
    assert fastapi_web.safe_next('/results?x=1') == '/results?x=1'
    for target in ('//evil.example', 'https://evil.example', '/login', '/logout/', '/register?next=/'):
        assert fastapi_web.safe_next(target) == '/'


def test_flash_is_shown_once(client, app):
    """Los avisos van a `_flashes` de la cookie de sesión y se muestran una sola vez."""
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
    """url_for arma rutas con nombre y estáticos; lo que no es parámetro va en la query."""
    def urls(request: Request):
        return {'lang': fastapi_web.url_for(request, 'set_language', code='en', next='/x'),
                'page': fastapi_web.url_for(request, 'alerts'),
                'static': fastapi_web.url_for(request, 'static', filename='css/app.css')}
    _add_route(client, '/_urls', urls)

    assert client.get('/_urls').get_json() == {'lang': '/lang/en?next=/x', 'page': '/alerts',
                                               'static': '/static/css/app.css'}


def test_url_for_unknown_endpoint_raises(client):
    """Un endpoint que no existe es un error (antes caía en las reglas de Flask)."""
    import pytest
    from starlette.routing import NoMatchFound

    def build(request: Request):
        with pytest.raises(NoMatchFound):
            fastapi_web.url_for(request, 'no_existe')
        return {}
    _add_route(client, '/_unknown', build)
    assert client.get('/_unknown').status_code == 200


def test_session_cookie_format_matches_flask(app):
    """Una cookie firmada por Flask (tuplas en _flashes, sesión permanente) se lee igual sin Flask."""
    from datetime import datetime, timezone
    data = {'_flashes': [('info', 'hola')], '_permanent': True, 'uid': 1, 'when': datetime(2026, 1, 2, tzinfo=timezone.utc),
            ' t': 'clave rara'}
    serializer = app.session_serializer()
    assert serializer.loads(serializer.dumps(data)) == data
    assert serializer.dumps({'_flashes': [('info', 'hola')]}).startswith('eyJfZmxhc2hlcyI6W3siIHQiOlsiaW5mbyIsImhvbGEiXX1dfQ')


def test_unknown_page_renders_error_and_api_stays_json(client):
    """Sin Flask montado, una página inexistente muestra la página de error y /api/* responde JSON."""
    page = client.get('/no-existe')
    assert page.status_code == 404 and 'text/html' in page.content_type
    api = client.get('/api/no-existe')
    assert api.status_code == 404 and api.get_json() == {'detail': 'Not Found'}


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
    cookie = app.session_serializer().dumps({'_permanent': True, 'n': 1})
    client._c.cookies.set('session', cookie)
    renewed = re.search(r'session=([^;]+);.*expires=', client.get('/').headers.get('set-cookie', ''), re.I)
    assert renewed and auth.load_session_cookie(app, renewed.group(1).strip('"'))['n'] == 1


def test_auth_form_rejects_oversized_body(client):
    """Un formulario de login enorme se corta con 413 antes de parsearlo."""
    big = {'email': 'a@b.c', 'password': 'x' * (fastapi_web.FORM_MAX_BYTES + 1)}
    assert client.post('/login', data=big).status_code == 413
    assert client.post('/login', data={'email': 'a@b.c', 'password': 'x'}).status_code != 413


def test_every_template_endpoint_exists(client):
    """Cada url_for('...') de las plantillas apunta a una ruta de FastAPI (ya no hay reglas de Flask de respaldo)."""
    import pathlib
    names = {getattr(r, 'name', None) for r in fastapi_web.all_routes(client.app.router.routes)}
    used = set()
    for path in pathlib.Path(__file__).resolve().parent.parent.joinpath('templates').rglob('*.html'):
        used |= set(re.findall(r"url_for\(\s*'([a-z_]+)'", path.read_text(encoding='utf-8')))
    assert used and used - names - {'static'} == set()


def test_account_forms_require_csrf(client, app, monkeypatch):
    """Los POST de Mi cuenta y Administración validan el token CSRF como Flask-WTF."""
    monkeypatch.setitem(app.config, 'WTF_CSRF_ENABLED', True)
    assert client.post('/account/delete', data={'password': 'x'}).status_code == 400
    assert client.post('/admin/users/1/block').status_code == 400


def test_content_pages_are_served_by_fastapi(client):
    """Resultados, documentos, perfiles y alertas los sirve FastAPI."""
    assert client.app.url_path_for('delete_csv', filename='a.csv') == '/delete_csv/a.csv'


def test_delete_csv_needs_post_with_csrf_and_stays_in_results(client, app, monkeypatch, tmp_path):
    """Borrar un CSV ya no se dispara con un GET y solo toca .csv de la carpeta de la cuenta."""
    import accounts
    monkeypatch.setattr(accounts, 'results_dir', lambda: str(tmp_path))
    (tmp_path / 'a.csv').write_text('x')
    (tmp_path / 'notes.txt').write_text('x')
    assert client.get('/delete_csv/a.csv').status_code in (404, 405)
    monkeypatch.setitem(app.config, 'WTF_CSRF_ENABLED', True)
    assert client.post('/delete_csv/a.csv').status_code == 400
    monkeypatch.setitem(app.config, 'WTF_CSRF_ENABLED', False)
    assert client.post('/delete_csv/notes.txt').status_code == 302
    assert client.post('/delete_csv/a.csv').status_code == 302
    assert not (tmp_path / 'a.csv').exists() and (tmp_path / 'notes.txt').exists()
    (tmp_path / '.env').write_text('x')
    assert client.get('/results/.env').status_code == 404
    assert client.get('/results/notes.txt').status_code == 200


def test_scraper_forms_need_csrf_and_launch_for_the_account(client, app, monkeypatch):
    """Los formularios de búsqueda validan CSRF y lanzan la tarea con las búsquedas cargadas."""
    import job_dispatch
    launched = []
    monkeypatch.setattr(job_dispatch, 'launch', lambda status, key, name, *args: launched.append((key, name, args)))
    monkeypatch.setitem(app.config, 'WTF_CSRF_ENABLED', True)
    assert client.post('/start_bumeran_scraper', data={'position[]': 'python'}).status_code == 400
    monkeypatch.setitem(app.config, 'WTF_CSRF_ENABLED', False)
    response = client.post('/start_bumeran_scraper', data={'position[]': ['python', ''], 'location[]': ['CABA', '']})
    assert response.status_code == 302
    assert launched == [('bumeran_scraping', 'run_bumeran_job', ([{'position': 'python', 'location': 'CABA'}],))]


def test_test_task_status_rejects_paths_and_other_accounts(client, app):
    """task_id debe ser un UUID y la prueba tiene que ser de la cuenta actual."""
    import uuid
    app_globals = app.extensions['empleoia_app_globals']
    assert client.get('/test_task_status?task_id=../../secret').status_code == 404
    mine, other = str(uuid.uuid4()), str(uuid.uuid4())
    app_globals['test_tasks'][mine] = {'status': 'completed', 'result': [{'Title': 'x'}], 'user_id': None}
    app_globals['test_tasks'][other] = {'status': 'completed', 'result': [], 'user_id': 999}
    assert client.get(f'/test_task_status?task_id={mine}').get_json()['count'] == 1
    assert client.get(f'/test_task_status?task_id={other}').status_code == 404


def test_linkedin_test_fails_when_token_login_fails(app):
    """La prueba de LinkedIn inicia sesión con el token y, si no puede, falla en vez de buscar como invitado."""
    from routers import scraper_pages
    fake = mock.Mock()
    fake.return_value.login_with_cookie.return_value = False
    app_globals = {'test_tasks': {'t': {}}, 'save_task_to_disk': lambda tid: None}
    with mock.patch('scrapers.linkedin_pw.linkedinClass', fake):
        scraper_pages._run_linkedin_test(app_globals, 't', 'tok', 'python', '', 5)
    assert app_globals['test_tasks']['t']['status'] == 'failed'
    fake.return_value.search_jobs.assert_not_called()
    fake.return_value.close.assert_called_once()
