"""
core/security.py — Utilidades de seguridad (sin dependencias de Flask/Werkzeug).
"""
import os
import re
import unicodedata

_WINDOWS_ILLEGAL = '<>:"/\\|?*'
_CONTROL_CHARS = ''.join(chr(i) for i in range(32) if i not in (9, 10, 13))


def secure_filename(filename: str) -> str:
    """
    Versión propia del secure_filename de Werkzeug:
    normaliza, quita caracteres peligrosos y path traversal.
    """
    if not filename:
        return ""

    filename = unicodedata.normalize('NFKD', filename)
    filename = filename.encode('ascii', 'ignore').decode('ascii')

    for sep in os.sep, os.path.altsep:
        if sep:
            filename = filename.replace(sep, ' ')

    filename = str.strip(filename.strip('._'))
    filename = re.sub(r'(?u)^[-]+', '', filename)
    filename = re.sub(r'[^\w\s.-]', '', filename)
    filename = re.sub(r'\s+', '_', filename)
    filename = filename.strip('_')

    # Sanear caracteres ilegales en Windows
    for ch in _WINDOWS_ILLEGAL + _CONTROL_CHARS:
        filename = filename.replace(ch, '')

    return filename


def is_safe_results_path(filename: str, results_dir: str = 'results') -> str | None:
    """
    Devuelve la ruta absoluta si `filename` queda dentro de results_dir,
    o None si hay path traversal / nombre inválido.
    """
    safe = secure_filename(filename)
    if not safe:
        return None
    base = os.path.abspath(results_dir)
    path = os.path.abspath(os.path.join(base, safe))
    if not path.startswith(base + os.sep):
        return None
    return path
