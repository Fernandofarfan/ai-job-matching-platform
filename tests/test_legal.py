"""Términos, Privacidad, aceptación al registrarse y permiso para usar la IA."""
from unittest import mock

import pytest

import accounts
import ai_engine
import embeddings

PASSWORD = 'clave-larga-1'


def _register(client, accept=True):
    data = {'email': 'ana@example.com', 'password': PASSWORD, 'confirm': PASSWORD}
    if accept:
        data['accept_terms'] = 'on'
    return client.post('/register', data=data)


@pytest.mark.parametrize('path, title', [('/terms', 'Términos y condiciones'), ('/privacy', 'Política de privacidad')])
def test_legal_pages_are_public_and_translated(client, accounts_db, path, title):
    body = client.get(path).get_data(as_text=True)
    assert title in body and 'login' not in client.get(path).headers.get('Location', '')
    client.set_cookie('lang', 'en')
    assert ('Terms and conditions' if path == '/terms' else 'Privacy policy') in client.get(path).get_data(as_text=True)


def test_legal_contact_comes_from_env(client, accounts_db, monkeypatch):
    monkeypatch.setenv('LEGAL_CONTACT_EMAIL', 'legal@example.com')
    monkeypatch.setenv('LEGAL_OPERATOR_NAME', 'Acme <SA>')
    body = client.get('/privacy').get_data(as_text=True)
    assert 'mailto:legal@example.com' in body
    assert 'Acme &lt;SA&gt;' in body


def test_register_requires_accepting_terms(client, accounts_db):
    body = _register(client, accept=False).get_data(as_text=True)
    assert 'aceptar los Términos' in body
    assert accounts.count_users() == 0
    _register(client)
    user = accounts.get_user(accounts.find_user_id('ana@example.com'))
    assert user['terms_accepted'] and not user['ai_consent']


def test_register_and_login_link_legal_pages(client, accounts_db):
    body = client.get('/register').get_data(as_text=True)
    assert 'href="/terms"' in body and 'href="/privacy"' in body
    assert 'name="accept_terms"' in body


def test_ai_consent_banner_and_toggle(client, accounts_db):
    _register(client)
    assert 'Dar permiso' in client.get('/').get_data(as_text=True)
    response = client.post('/account/ai_consent', data={'granted': '1', 'next': '/tracker'})
    assert response.headers['Location'] == '/tracker'
    assert accounts.get_user(accounts.find_user_id('ana@example.com'))['ai_consent']
    assert 'name="granted" value="1"' not in client.get('/').get_data(as_text=True)
    client.post('/account/ai_consent', data={'granted': '0', 'next': 'https://evil.example'})
    assert not accounts.get_user(accounts.find_user_id('ana@example.com'))['ai_consent']


def test_ai_consent_next_cannot_leave_the_site(client, accounts_db):
    _register(client)
    response = client.post('/account/ai_consent', data={'granted': '1', 'next': 'https://evil.example/x'})
    assert 'evil.example' not in response.headers['Location']


def test_ai_calls_need_consent(accounts_db):
    user_id = accounts.register('ana@example.com', PASSWORD)
    with accounts.as_user(user_id), mock.patch.object(ai_engine, 'GEMINI_AVAILABLE', True), \
            mock.patch.object(ai_engine, '_gemini_client', create=True) as client:
        assert ai_engine._call_gemini('hola') == ai_engine.AI_CONSENT_ERROR
        assert embeddings.embed(['texto']) is None
        client.models.generate_content.assert_not_called()
        accounts.set_ai_consent(user_id, True)
        assert not accounts.ai_consent_missing()


def test_local_mode_without_account_needs_no_consent():
    with accounts.as_user(None):
        assert not accounts.ai_consent_missing()


def test_export_includes_consent_dates(accounts_db):
    import io
    import json
    import zipfile

    import data_export
    user_id = accounts.register('ana@example.com', PASSWORD)
    accounts.accept_terms(user_id)
    with zipfile.ZipFile(io.BytesIO(data_export.build(user_id))) as zf:
        account = json.loads(zf.read('cuenta.json'))
    assert account['terminos_aceptados'] and account['permiso_ia'] is None


def test_interview_evaluation_without_consent_has_no_grade():
    with mock.patch.object(ai_engine, '_call_gemini', return_value=ai_engine.AI_CONSENT_ERROR):
        assert ai_engine.evaluate_interview_answer('q', 'a', 'Dev') == {'error': ai_engine.AI_CONSENT_ERROR}
