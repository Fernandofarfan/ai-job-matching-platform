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
    """Textos marcados en las plantillas, mensajes flash literales y etiquetas de eventos de seguridad."""
    texts = set(security_events.LABELS.values())
    for path in glob.glob('templates/*.html'):
        texts |= set(re.findall(r"_\('((?:[^'\\]|\\.)*)'", open(path, encoding='utf-8').read()))
    for path in ['app.py', *glob.glob('web/*.py')]:
        texts |= set(re.findall(r"flash\('((?:[^'\\]|\\.)*)'", open(path, encoding='utf-8').read()))
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
    client.post('/register', data={'email': 'ana@example.com', 'password': 'clave-larga-1', 'confirm': 'clave-larga-1'})
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
