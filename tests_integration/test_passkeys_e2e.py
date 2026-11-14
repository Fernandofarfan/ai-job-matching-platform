"""E2E de passkeys con Chromium y un autenticador virtual (CDP WebAuthn): agregar en Mi cuenta y entrar sin contraseña."""
import secrets


def test_add_passkey_and_login_with_it(browser, live_server, credentials):
    # WebAuthn necesita un dominio (no una IP) en un contexto seguro: localhost lo es
    base = live_server.replace('127.0.0.1', 'localhost')
    context = browser.new_context(base_url=base, reduced_motion='reduce')
    page = context.new_page()
    page.set_default_timeout(20000)
    errors = []
    page.on('pageerror', lambda e: errors.append(str(e)))
    cdp = context.new_cdp_session(page)
    cdp.send('WebAuthn.enable')
    cdp.send('WebAuthn.addVirtualAuthenticator', {'options': {
        'protocol': 'ctap2', 'transport': 'internal', 'hasResidentKey': True,
        'hasUserVerification': True, 'isUserVerified': True}})

    email, password = f'passkey-{secrets.token_hex(4)}@example.com', secrets.token_urlsafe(16)
    page.goto('/register')
    page.fill('#email', email)
    page.fill('#password', password)
    page.fill('#confirm', password)
    page.check('#accept_terms')
    page.click('button[type=submit]')
    page.wait_for_load_state('networkidle')

    page.goto('/account')
    page.fill('#passkey-name', 'Chromium E2E')
    page.fill('#passkey-password', password)
    with page.expect_navigation():
        page.click('#addPasskeyBtn')
    assert page.locator('#passkeyList').inner_text().count('Chromium E2E') == 1, page.locator('#passkeyStatus').inner_text()

    page.locator('form[action$="/logout"] button').first.click()
    page.wait_for_load_state('networkidle')
    page.goto('/login?next=/tracker')
    with page.expect_navigation(url='**/tracker'):
        page.click('#passkeyLogin')
    assert '/login' not in page.url
    assert errors == []
    context.close()
