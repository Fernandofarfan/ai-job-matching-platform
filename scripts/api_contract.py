"""Prueba la API contra su OpenAPI con Schemathesis, con la sesión de una cuenta sembrada.

Uso: python scripts/api_contract.py <url> <dir-de-reportes> [opciones extra de schemathesis]
Lee el email y la contraseña de API_CONTRACT_EMAIL / API_CONTRACT_PASSWORD. La app tiene que correr con
ENABLE_API_DOCS=1 para publicar /openapi.json.
"""
import os
import re
import subprocess
import sys

import requests

CSRF_INPUT = re.compile(r'name="csrf_token"[^>]*value="([^"]+)"')
CSRF_META = re.compile(r'name="csrf-token" content="([^"]+)"')

# Mandan emails o push reales, o necesitan la firma de SendGrid: no aportan al contrato.
EXCLUDED_PATHS = r'^/(api/notifications/(test|trigger-digest)|api/push/test|webhooks/sendgrid)$'
CHECKS = 'not_a_server_error,status_code_conformance,content_type_conformance,response_schema_conformance'


def login(base: str, email: str, password: str) -> tuple[str, str]:
    """Entra con la cuenta y devuelve el header Cookie y el token CSRF de la sesión."""
    s = requests.Session()
    page = s.get(f'{base}/login', timeout=30)
    token = CSRF_INPUT.search(page.text)
    r = s.post(f'{base}/login', data={'email': email, 'password': password,
                                       'csrf_token': token.group(1) if token else ''},
               allow_redirects=False, timeout=30)
    if r.status_code != 302 or '/login' in r.headers.get('Location', ''):
        sys.exit(f'login rechazado ({r.status_code})')
    meta = CSRF_META.search(s.get(f'{base}/', timeout=30).text)
    if not meta:
        sys.exit('no se encontró el token CSRF de la sesión')
    cookie = '; '.join(f'{k}={v}' for k, v in s.cookies.items())
    return cookie, meta.group(1)


def main() -> int:
    """Corre schemathesis y devuelve su código de salida."""
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    base, report_dir, extra = sys.argv[1].rstrip('/'), sys.argv[2], sys.argv[3:]
    cookie, csrf = login(base, os.environ['API_CONTRACT_EMAIL'], os.environ['API_CONTRACT_PASSWORD'])
    cmd = ['schemathesis', 'run', f'{base}/openapi.json',
           '--checks', CHECKS,
           '--exclude-path-regex', EXCLUDED_PATHS,
           '-H', f'Cookie: {cookie}', '-H', f'X-CSRFToken: {csrf}',
           '--max-examples', os.getenv('API_CONTRACT_MAX_EXAMPLES', '30'),
           '--seed', os.getenv('API_CONTRACT_SEED', '20261113'),
           '--report', 'junit', '--report-dir', report_dir,
           *extra]
    return subprocess.call(cmd)


if __name__ == '__main__':
    sys.exit(main())
