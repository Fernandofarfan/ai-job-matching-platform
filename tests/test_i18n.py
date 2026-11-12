"""Interfaz en español, inglés y portugués: catálogos completos, negociación del idioma y selector."""
import glob
import json
import re

import pytest
from jinja2 import Environment, FileSystemLoader

import i18n
import security_events

PLACEHOLDER = re.compile(r'%\((\w+)\)s')


def _ui_texts() -> set:
    """Textos marcados en las plantillas, mensajes flash literales, progreso de búsquedas y eventos de seguridad."""
    texts = set(security_events.LABELS.values())
    for path in glob.glob('templates/*.html'):
        texts |= set(re.findall(r"_\('((?:[^'\\]|\\.)*)'", open(path, encoding='utf-8').read()))
    for path in ['app.py', *glob.glob('web/*.py')]:
        texts |= set(re.findall(r"flash\('((?:[^'\\]|\\.)*)'", open(path, encoding='utf-8').read()))
    for path in ['scraping_jobs.py', 'job_dispatch.py', *glob.glob('services/*.py'), *glob.glob('routers/*.py')]:
        texts |= set(re.findall(r"(?:_m|i18n\.lazy)\('((?:[^'\\]|\\.)*)'", open(path, encoding='utf-8').read()))
    return texts


@pytest.mark.parametrize('lang', ['en', 'pt'])
def test_catalogs_cover_every_text(lang):
    with open(f'translations/{lang}.json', encoding='utf-8') as f:
        catalog = json.load(f)
    texts = _ui_texts()
    assert sorted(texts - set(catalog)) == []
    for es, translated in catalog.items():
        assert translated.strip(), es
        assert sorted(PLACEHOLDER.findall(es)) == sorted(PLACEHOLDER.findall(translated)), es


def test_templates_compile():
    env = Environment(loader=FileSystemLoader('templates'))
    for path in glob.glob('templates/*.html'):
        env.get_template(path.split('/')[-1])


@pytest.mark.parametrize('cookie,header,expected', [
    ('pt', 'en-US', 'pt'),
    (None, 'en-US,en;q=0.9', 'en'),
    (None, 'fr-FR, pt-BR;q=0.8, en;q=0.5', 'pt'),
    (None, 'de', 'es'),
    ('xx', None, 'es'),
    (None, 'en;q=abc', 'es'),
])
def test_negotiate(cookie, header, expected):
    assert i18n.negotiate(cookie, header) == expected


def test_jinja_gettext_escapes():
    i18n.set_locale('en')
    try:
        assert str(i18n.jinja_gettext('Al menos %(n)s caracteres.', n='<b>8</b>')) == 'At least &lt;b&gt;8&lt;/b&gt; characters.'
        assert str(i18n.jinja_gettext('<script>')) == '&lt;script&gt;'
    finally:
        i18n.set_locale('es')


@pytest.fixture
def one_account(client, accounts_db):
    """Con una cuenta creada, /login muestra el formulario en vez de mandar a /register."""
    client.post('/register', data={'accept_terms': 'on', 'email': 'ana@example.com', 'password': 'clave-larga-1', 'confirm': 'clave-larga-1'})
    client.post('/logout')
    client.delete_cookie('lang')


def test_language_switch_and_pages(client, one_account):
    assert 'Ingresar' in client.get('/login').get_data(as_text=True)
    page = client.get('/login', headers={'Accept-Language': 'pt-BR'}).get_data(as_text=True)
    assert '<html lang="pt">' in page and 'Esqueceu sua senha?' in page
    response = client.get('/lang/en?next=/forgot_password')
    assert response.status_code == 302 and response.headers['Location'].endswith('/forgot_password')
    assert 'lang=en' in response.headers['Set-Cookie']
    page = client.get('/login').get_data(as_text=True)
    assert 'Sign in' in page and 'Forgot your password?' in page


def test_language_switch_returns_to_login_and_register(client):
    for target in ('/register', '/login?next=%2Ftracker'):
        response = client.get('/lang/pt', query_string={'next': target})
        assert response.headers['Location'].endswith(target)


def test_language_switch_rejects_external_next(client):
    for target in ('//evil.example', 'https://evil.example', '/\\evil.example'):
        response = client.get('/lang/en', query_string={'next': target})
        assert 'evil.example' not in response.headers['Location']


def test_flash_messages_are_translated(client, one_account):
    client.set_cookie('lang', 'en')
    response = client.post('/login', data={'email': 'ana@example.com', 'password': 'x' * 12}, follow_redirects=True)
    assert 'Wrong email or password' in response.get_data(as_text=True)


@pytest.mark.parametrize('path,english', [
    ('/scraper', 'Start universal search'),
    ('/results', 'Search results'),
    ('/tracker', 'Application board'),
    ('/alerts', 'Job alerts'),
    ('/profile', 'Upload a new resume'),
])
def test_app_pages_are_translated(client, one_account, path, english):
    client.post('/login', data={'email': 'ana@example.com', 'password': 'clave-larga-1'})
    client.set_cookie('lang', 'en')
    page = client.get(path).get_data(as_text=True)
    assert english in page
    client.set_cookie('lang', 'es')
    assert english not in client.get(path).get_data(as_text=True)


def test_progress_messages_are_translated_when_read(client, one_account, monkeypatch):
    """El progreso se guarda en español con sus valores y /status lo devuelve en el idioma de la cuenta."""
    import job_dispatch
    state = {
        'bumeran_scraping': {'status': 'running', 'progress': 40,
                             'message': i18n.lazy('%(count)s ofertas para %(position)s', count=3, position='Python')},
        'universal_scraping': {'status': 'running', 'message': 'texto viejo',
                               'scrapers': {'indeed': {'message': i18n.lazy('Usá la búsqueda individual de este portal')}}},
    }
    monkeypatch.setattr(job_dispatch, 'refresh', lambda job_status: state)
    client.post('/login', data={'email': 'ana@example.com', 'password': 'clave-larga-1'})
    expected = {'en': ('3 jobs for Python', "Use this site's own search"),
                'pt': ('3 vagas para Python', 'Use a busca individual deste portal'),
                'es': ('3 ofertas para Python', 'Usá la búsqueda individual de este portal')}
    for lang, (count, skipped) in expected.items():
        client.set_cookie('lang', lang)
        data = client.get('/status').get_json()
        assert data['bumeran_scraping']['message'] == count
        assert data['universal_scraping']['scrapers']['indeed']['message'] == skipped
        assert data['universal_scraping']['message'] == 'texto viejo'


def test_render_message():
    """Los mensajes viejos (texto suelto) y los valores con % se muestran sin fallar."""
    assert i18n.render_message('texto suelto') == 'texto suelto'
    assert i18n.render_message(i18n.lazy('Error: %(error)s', error='100% roto')) == 'Error: 100% roto'
    assert i18n.render_message(None) is None
