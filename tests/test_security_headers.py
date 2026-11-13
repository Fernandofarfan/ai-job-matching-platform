"""Cabeceras de seguridad: CSP con nonce, HSTS, anti-framing y plantillas sin handlers inline."""
import json
import pathlib
import re

TEMPLATES = pathlib.Path(__file__).resolve().parent.parent / 'templates'
INLINE_HANDLER = re.compile(r'\son[a-z]+\s*=\s*["\']', re.I)


def _csp(response):
    return response.headers['content-security-policy']


def test_html_page_has_csp_with_matching_nonce(client):
    response = client.get('/tracker')  # trae un bloque de datos JSON en línea
    csp = _csp(response)
    nonce = re.search(r"'nonce-([^']+)'", csp).group(1)
    scripts = re.findall(r'<script(?![^>]*\bsrc=)([^>]*)>', response.get_data(as_text=True))
    assert scripts and all(f'nonce="{nonce}"' in attrs for attrs in scripts)
    assert "'unsafe-inline'" not in csp.split('script-src')[1].split(';')[0]
    assert "frame-ancestors 'none'" in csp and "object-src 'none'" in csp


def test_nonce_changes_per_request(client):
    first = re.search(r"'nonce-([^']+)'", _csp(client.get('/login'))).group(1)
    second = re.search(r"'nonce-([^']+)'", _csp(client.get('/login'))).group(1)
    assert first != second


def test_common_headers_on_api_and_errors(client):
    for response in (client.get('/api/health'), client.get('/no-existe')):
        assert response.headers['x-content-type-options'] == 'nosniff'
        assert response.headers['x-frame-options'] == 'DENY'
        assert response.headers['referrer-policy'] == 'strict-origin-when-cross-origin'
        assert 'microphone=(self)' in response.headers['permissions-policy']
        assert 'content-security-policy' in response.headers


def test_hsts_only_over_https(client, monkeypatch):
    monkeypatch.delenv('SESSION_COOKIE_SECURE', raising=False)
    assert 'strict-transport-security' not in client.get('/api/health').headers
    proxied = client.get('/api/health', headers={'X-Forwarded-Proto': 'https'})
    assert proxied.headers['strict-transport-security'].startswith('max-age=31536000')
    monkeypatch.setenv('SESSION_COOKIE_SECURE', '1')
    assert 'strict-transport-security' in client.get('/api/health').headers


def test_report_only_and_report_uri(client, monkeypatch):
    monkeypatch.setenv('CSP_REPORT_ONLY', '1')
    monkeypatch.setenv('CSP_REPORT_URI', 'https://example.test/csp')
    response = client.get('/login')
    assert 'content-security-policy' not in response.headers
    assert 'report-uri https://example.test/csp' in response.headers['content-security-policy-report-only']


def test_route_headers_are_not_overwritten(client):
    """El reset de contraseña ya pone no-referrer para no filtrar el token."""
    response = client.get('/reset_password/token-invalido')
    if 'referrer-policy' in response.headers and response.status_code == 200:
        assert response.headers['referrer-policy'] == 'no-referrer'


def test_api_docs_disabled_by_default(app, monkeypatch):
    from tests.conftest import WebClient
    assert WebClient(app).get('/docs').status_code == 404
    assert WebClient(app).get('/openapi.json').status_code == 404
    monkeypatch.setenv('ENABLE_API_DOCS', '1')
    assert WebClient(app).get('/openapi.json').status_code == 200


def test_templates_have_no_inline_handlers_or_javascript_urls():
    files = [*TEMPLATES.glob('*.html'), *(TEMPLATES.parent / 'static' / 'js').rglob('*.js')]
    offenders = [f'{p.name}:{n}' for p in files
                 for n, line in enumerate(p.read_text(encoding='utf-8').splitlines(), 1)
                 if INLINE_HANDLER.search(line) or 'javascript:' in line]
    assert offenders == []


def test_inline_scripts_carry_the_nonce():
    missing = [p.name for p in TEMPLATES.glob('*.html')
               for attrs in re.findall(r'<script(?![^>]*\bsrc=)([^>]*)>', p.read_text(encoding='utf-8'))
               if 'csp_nonce()' not in attrs]
    assert missing == []


def test_templates_have_no_inline_javascript():
    """El JavaScript va en static/js (se cachea, se testea y se lintea); en línea solo quedan datos JSON."""
    inline = [f'{p.name}: {attrs.strip()[:60]}' for p in TEMPLATES.glob('*.html')
              for attrs in re.findall(r'<script(?![^>]*\bsrc=)([^>]*)>', p.read_text(encoding='utf-8'))
              if 'type="application/json"' not in attrs]
    assert inline == []


def test_template_scripts_exist():
    static = TEMPLATES.parent / 'static'
    missing = [f'{p.name}: {name}' for p in TEMPLATES.glob('*.html')
               for name in re.findall(r"url_for\('static', filename='(js/[^']+)'\)", p.read_text(encoding='utf-8'))
               if not (static / name).is_file()]
    assert missing == []


def test_cdn_resources_are_pinned_with_sri():
    unpinned = [f'{p.name}: {tag[:80]}' for p in TEMPLATES.glob('*.html')
                for tag in re.findall(r'<(?:script|link)[^>]*cdn\.jsdelivr\.net[^>]*>', p.read_text(encoding='utf-8'))
                if 'integrity="sha384-' not in tag or 'crossorigin="anonymous"' not in tag or '@' not in tag]
    assert unpinned == []


def test_declared_actions_exist():
    """Cada data-on*="fn" apunta a una función global de un script que carga la plantilla o base.html."""
    def with_scripts(text: str) -> str:
        names = re.findall(r"url_for\('static', filename='(js/[^']+)'\)", text)
        return text + ''.join((TEMPLATES.parent / 'static' / n).read_text(encoding='utf-8') for n in names)

    shared = with_scripts((TEMPLATES / 'base.html').read_text(encoding='utf-8'))
    missing = []
    for p in TEMPLATES.glob('*.html'):
        template = p.read_text(encoding='utf-8')
        text = with_scripts(template)
        for name in set(re.findall(r'data-on(?:click|change|input|keydown)="(\w+)"', template)):
            pattern = rf'(function\s+{name}\s*\(|window\.{name}\s*=)'
            if not re.search(pattern, text) and not re.search(pattern, shared):
                missing.append(f'{p.name}: {name}')
        for args in re.findall(r"data-args='([^']*)'", template):
            if '{{' not in args:
                assert isinstance(json.loads(args), list)
    assert missing == []


def test_app_exports_db_manager_for_legacy_routes():
    """Los routers piden db_manager a los globals de app.py; el conftest lo inyecta, así que se mira la fuente."""
    source = (TEMPLATES.parent / 'app.py').read_text()
    assert re.search(r'^from db_config import db_manager\b', source, re.M)


def test_connections_escapes_company_in_data_args(client, app):
    """La empresa va en data-args como JSON escapado: una comilla no corta el atributo."""
    from unittest import mock
    db = app.extensions['empleoia_services'].db
    with mock.patch.object(db, 'get_companies_for_connections', return_value=[{'company': "O'Hara <SA>"}]):
        body = client.get('/connections').get_data(as_text=True)
    assert "data-args='[\"O\\u0027Hara \\u003cSA\\u003e\", \"$el\"]'" in body


def test_elements_with_several_handlers_use_per_event_args():
    """Un elemento con dos data-on* no puede repetir data-args (el navegador ignora el segundo)."""
    for path in sorted(TEMPLATES.glob('*.html')):
        for tag in re.findall(r'<[a-z][^>]*>', path.read_text(), re.S):
            assert tag.count('data-args=') <= 1, f'{path.name}: {tag[:120]}'


def test_server_error_keeps_security_headers(app):
    """El 500 se arma fuera de los middlewares; igual lleva la CSP y el anti-framing."""
    from fastapi.testclient import TestClient

    import main
    api = main.create_app(app)

    @api.get('/boom')
    @api.get('/api/boom')
    def boom():
        raise RuntimeError('detalle-secreto')

    client = TestClient(api, raise_server_exceptions=False)
    for path in ('/boom', '/api/boom'):
        response = client.get(path)
        assert response.status_code == 500
        assert 'detalle-secreto' not in response.text
        assert "frame-ancestors 'none'" in response.headers['content-security-policy']
        assert response.headers['x-frame-options'] == 'DENY'
