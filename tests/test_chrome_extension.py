"""Chequeos estáticos de la extensión de Chrome (Manifest V3) y de su empaquetado."""
import json
import os
import re
import sys
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXT = os.path.join(ROOT, 'chrome_extension')
sys.path.insert(0, os.path.join(ROOT, 'scripts'))

import package_extension  # noqa: E402


def _read(name):
    with open(os.path.join(EXT, name), encoding='utf-8') as f:
        return f.read()


def _manifest():
    return json.loads(_read('manifest.json'))


def test_manifest_v3_and_referenced_files_exist():
    """El manifest es V3 y cada ícono, script y CSS que nombra existe (si no, Chrome no la carga)."""
    manifest = _manifest()
    assert manifest['manifest_version'] == 3
    for path in package_extension.manifest_files(manifest):
        assert os.path.isfile(os.path.join(EXT, path)), path


def test_every_chrome_api_used_has_its_permission():
    """Sin el permiso, chrome.<api> es undefined y el service worker falla al registrarse."""
    permissions = set(_manifest()['permissions'])
    code = ''.join(_read(n) for n in ('background.js', 'popup.js', 'content.js'))
    needs = {'contextMenus': 'contextMenus', 'scripting': 'scripting', 'storage': 'storage'}
    for api, permission in needs.items():
        if f'chrome.{api}.' in code:
            assert permission in permissions, api


def test_minimal_host_permissions():
    """Solo localhost fijo; cualquier otro servidor se pide en tiempo de ejecución."""
    manifest = _manifest()
    assert set(manifest['host_permissions']) <= {'http://localhost:5000/*', 'http://127.0.0.1:5000/*'}
    assert manifest['optional_host_permissions'] == ['https://*/*']


def test_no_inline_handlers_or_remote_code():
    """La CSP de MV3 bloquea onclick="..." y los scripts remotos."""
    html = _read('popup.html')
    assert not re.search(r'\son[a-z]+\s*=', html)
    assert not re.search(r'<script[^>]+src=["\']https?:', html)
    for name in ('background.js', 'popup.js', 'content.js'):
        code = _read(name)
        assert 'eval(' not in code and 'new Function' not in code, name


def test_page_text_is_not_injected_as_html():
    """El título de la oferta va con textContent, nunca interpolado en innerHTML."""
    for name in ('popup.js', 'content.js'):
        for assignment in re.findall(r'innerHTML\s*=\s*`[^`]*`', _read(name)):
            assert '${' not in assignment, assignment


def test_package_contains_only_extension_files(tmp_path):
    """El zip lleva el manifest en la raíz y nada fuera de chrome_extension/."""
    path = package_extension.build(str(tmp_path))
    assert path.endswith(f"empleoia-saver-{_manifest()['version']}.zip")
    with zipfile.ZipFile(path) as zf:
        names = zf.namelist()
    assert 'manifest.json' in names and 'icons/icon128.png' in names
    assert all(n.endswith(package_extension.ALLOWED_SUFFIXES) for n in names)
