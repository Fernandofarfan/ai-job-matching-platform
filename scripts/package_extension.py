"""Arma el .zip de chrome_extension/ listo para subir al Chrome Web Store.

Uso: python scripts/package_extension.py [--out dist]
"""
import argparse
import json
import os
import sys
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXT_DIR = os.path.join(ROOT, 'chrome_extension')
ALLOWED_SUFFIXES = ('.js', '.json', '.html', '.css', '.png')


def manifest_files(manifest):
    """Archivos que el manifest referencia y tienen que existir dentro del paquete."""
    files = set(manifest.get('icons', {}).values())
    action = manifest.get('action', {})
    files |= set(action.get('default_icon', {}).values())
    if action.get('default_popup'):
        files.add(action['default_popup'])
    if manifest.get('background', {}).get('service_worker'):
        files.add(manifest['background']['service_worker'])
    for script in manifest.get('content_scripts', []):
        files |= set(script.get('js', [])) | set(script.get('css', []))
    return files


def build(out_dir):
    """Valida el manifest y escribe empleoia-saver-<versión>.zip; devuelve la ruta."""
    with open(os.path.join(EXT_DIR, 'manifest.json'), encoding='utf-8') as f:
        manifest = json.load(f)
    if manifest.get('manifest_version') != 3:
        raise SystemExit('La extensión tiene que ser Manifest V3')
    missing = sorted(p for p in manifest_files(manifest) if not os.path.isfile(os.path.join(EXT_DIR, p)))
    if missing:
        raise SystemExit(f'Faltan archivos del manifest: {", ".join(missing)}')

    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, f"empleoia-saver-{manifest['version']}.zip")
    with zipfile.ZipFile(path, 'w', zipfile.ZIP_DEFLATED) as zf:
        for base, _dirs, names in os.walk(EXT_DIR):
            for name in sorted(names):
                if name.endswith(ALLOWED_SUFFIXES):
                    full = os.path.join(base, name)
                    zf.write(full, os.path.relpath(full, EXT_DIR))
    return path


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', default=os.path.join(ROOT, 'dist'))
    print(build(parser.parse_args().out))
    sys.exit(0)
