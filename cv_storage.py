"""CVs subidos: cifrado en reposo (Fernet), lectura transparente, retención y borrado.

Con `CV_ENCRYPTION_KEY` (clave de `Fernet.generate_key()`) los archivos de `uploads/` se
guardan cifrados. Los CVs viejos en texto plano se siguen leyendo y `encrypt_existing()`
los cifra. `CV_RETENTION_DAYS` > 0 habilita el borrado automático por antigüedad.
"""
import glob
import logging
import os
import tempfile
import time
from collections.abc import Iterator
from contextlib import contextmanager

from cryptography.fernet import Fernet, InvalidToken

logger = logging.getLogger(__name__)

UPLOADS_DIR = 'uploads'
_FERNET_PREFIX = b'gAAAAA'


def generated_dirs() -> tuple[str, ...]:
    """CVs adaptados y cartas; GENERATED_DIR es la carpeta compartida entre web y worker."""
    root = os.getenv('GENERATED_DIR', 'temp')
    kinds = ('resumes', 'cover_letters')
    shared = tuple(os.path.join(root, kind) for kind in kinds)
    per_account = tuple(sorted(d for kind in kinds for d in glob.glob(os.path.join(root, 'u*', kind))))
    return shared + per_account


def _fernet() -> Fernet | None:
    key = os.getenv('CV_ENCRYPTION_KEY', '').strip()
    return Fernet(key.encode()) if key else None


def get_fernet() -> Fernet | None:
    """Fernet de CV_ENCRYPTION_KEY (también cifra los perfiles) o None si no hay clave."""
    return _fernet()


def _path(filename: str) -> str:
    """Ruta dentro de uploads/; rechaza nombres con directorios."""
    if not filename or os.path.basename(filename) != filename:
        raise ValueError(f'Nombre de CV inválido: {filename!r}')
    return os.path.join(UPLOADS_DIR, filename)


def _is_encrypted(data: bytes) -> bool:
    return data.startswith(_FERNET_PREFIX)


def save(data: bytes, filename: str) -> str:
    """Guarda el CV (cifrado si hay clave) y devuelve su ruta."""
    os.makedirs(UPLOADS_DIR, exist_ok=True)
    fernet = _fernet()
    path = _path(filename)
    with open(path, 'wb') as fh:
        fh.write(fernet.encrypt(data) if fernet else data)
    return path


def read_bytes(filename: str) -> bytes:
    """Contenido original del CV, esté cifrado o no."""
    with open(_path(filename), 'rb') as fh:
        data = fh.read()
    if not _is_encrypted(data):
        return data
    fernet = _fernet()
    if fernet is None:
        raise RuntimeError('El CV está cifrado y falta CV_ENCRYPTION_KEY')
    try:
        return fernet.decrypt(data)
    except InvalidToken:
        raise RuntimeError('No se pudo descifrar el CV: CV_ENCRYPTION_KEY no es la clave con que se cifró') from None


def exists(filename: str) -> bool:
    """True si el CV existe en uploads/."""
    try:
        return os.path.isfile(_path(filename))
    except ValueError:
        return False


@contextmanager
def plaintext_path(filename: str) -> Iterator[str]:
    """Ruta a una copia descifrada (misma extensión) para los parsers; se borra al salir."""
    path = _path(filename)
    with open(path, 'rb') as fh:
        if not _is_encrypted(fh.read(len(_FERNET_PREFIX))):
            yield path
            return
    fd, tmp = tempfile.mkstemp(suffix=os.path.splitext(filename)[1])
    try:
        with os.fdopen(fd, 'wb') as fh:
            fh.write(read_bytes(filename))
        yield tmp
    finally:
        os.remove(tmp)


def delete(filename: str) -> bool:
    """Borra un CV; False si no existía o el nombre es inválido."""
    try:
        os.remove(_path(filename))
        return True
    except (OSError, ValueError):
        return False


def delete_all() -> int:
    """Borra todos los CVs y los documentos generados a partir de ellos."""
    removed = 0
    for directory in (UPLOADS_DIR, *generated_dirs()):
        for path in glob.glob(os.path.join(directory, '*')):
            if os.path.isfile(path):
                os.remove(path)
                removed += 1
    return removed


def expired(days: int, now: float | None = None) -> list[str]:
    """Nombres de los CVs con más de `days` días."""
    cutoff = (now or time.time()) - days * 86400
    return [
        os.path.basename(p) for p in glob.glob(os.path.join(UPLOADS_DIR, '*'))
        if os.path.isfile(p) and os.path.getmtime(p) < cutoff
    ]


def purge_generated(days: int, now: float | None = None) -> int:
    """Borra CVs adaptados y cartas generados hace más de `days` días."""
    cutoff = (now or time.time()) - days * 86400
    removed = 0
    for directory in generated_dirs():
        for path in glob.glob(os.path.join(directory, '*')):
            if os.path.isfile(path) and os.path.getmtime(path) < cutoff:
                try:
                    os.remove(path)
                    removed += 1
                except OSError as e:
                    logger.warning(f"No se pudo borrar el documento generado {path}: {e}")
    return removed


def encrypt_existing() -> int:
    """Cifra los CVs que siguen en texto plano (manteniendo su fecha). Sin clave no hace nada."""
    fernet = _fernet()
    if fernet is None:
        return 0
    done = 0
    for path in glob.glob(os.path.join(UPLOADS_DIR, '*')):
        if not os.path.isfile(path):
            continue
        with open(path, 'rb') as fh:
            data = fh.read()
        if _is_encrypted(data):
            continue
        stat = os.stat(path)
        with open(path, 'wb') as fh:
            fh.write(fernet.encrypt(data))
        os.utime(path, (stat.st_atime, stat.st_mtime))
        done += 1
    return done
