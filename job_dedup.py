"""Unifica la misma oferta publicada en varios portales (búsqueda universal).

Dos ofertas son la misma si tienen la misma URL, o el mismo título y la misma empresa (sin tildes,
mayúsculas, puntuación ni sufijos societarios) en ubicaciones compatibles. Las empresas
"Confidencial" o vacías no se unifican: sin empresa no hay forma de saber si es la misma oferta.
"""
import re
import unicodedata
from typing import Any, Iterable, Optional
from urllib.parse import urlsplit

Job = dict[str, Any]

PLACEHOLDERS = {'', 'confidencial', 'empresa confidencial', 'reservado', 'no especificado', 'no especificada',
                'n a', 'na', 'nan', 'none', 'confidential', 'not specified', 'unknown'}
COMPANY_SUFFIXES = {'sa', 'srl', 'sas', 'sau', 'sl', 'sacif', 'saic', 'ltda', 'inc', 'llc', 'corp', 'corporation',
                    'ltd', 'limited', 'gmbh', 'cv', 'de'}
GENERIC_PLACES = {'argentina', 'chile', 'uruguay', 'paraguay', 'bolivia', 'peru', 'colombia', 'mexico', 'brasil',
                  'brazil', 'latam', 'remoto', 'remote', 'hibrido', 'presencial', 'reciente', 'provincia', 'de', 'del'}


def _norm(value: object) -> str:
    """Minúsculas ASCII, sin puntos y con el resto de la puntuación como espacios, salvo `+` y `#` (C++, C#)."""
    text = unicodedata.normalize('NFKD', str(value or '')).encode('ascii', 'ignore').decode().lower()
    text = re.sub(r'[^a-z0-9+# ]+', ' ', text.replace('.', ''))
    return ' '.join(text.split())


def _known(value: object) -> bool:
    """El campo trae un dato real y no un "Confidencial" / "No especificado"."""
    return _norm(value) not in PLACEHOLDERS


def company_key(company: object) -> str:
    """Empresa normalizada sin sufijos societarios: "Acme S.A." y "ACME" dan "acme"; vacía si es confidencial."""
    if not _known(company):
        return ''
    words = _norm(company).split()
    while len(words) > 1 and words[-1] in COMPANY_SUFFIXES:
        words.pop()
    return ' '.join(words)


def _places(location: object) -> set[str]:
    """Palabras de la ubicación que identifican un lugar (sin países ni "Remoto")."""
    return set(_norm(location).split()) - GENERIC_PLACES if _known(location) else set()


def _url_key(url: object) -> str:
    """URL sin query, fragmento ni barra final; vacía si no es http(s)."""
    text = str(url or '').strip()
    if not text.startswith(('http://', 'https://')):
        return ''
    parts = urlsplit(text)
    return f"{parts.netloc.lower()}{parts.path.rstrip('/')}"


def _source(job: Job) -> str:
    """Portal de la oferta."""
    return str(job.get('Fuente') or job.get('Source') or '')


def _compatible(a: Job, b: Job) -> bool:
    """Ubicaciones que pueden ser la misma: alguna es genérica o comparten una palabra de lugar."""
    places_a, places_b = _places(a.get('Location')), _places(b.get('Location'))
    return not places_a or not places_b or bool(places_a & places_b)


def _description_length(job: Job) -> int:
    """Largo de la descripción: la copia más completa queda como base."""
    return len(str(job.get('Description') or ''))


def _merge(group: list[Job]) -> Job:
    """La oferta con la descripción más larga, completada con los datos que falten de las demás."""
    richest: Job = max(group, key=_description_length)
    base = dict(richest)
    for other in group:
        for field, value in other.items():
            if not _known(base.get(field)) and _known(value):
                base[field] = value
    base['Portales'] = ', '.join(dict.fromkeys(s for s in map(_source, group) if s))
    urls = dict.fromkeys(str(job.get('URL')) for job in group if _url_key(job.get('URL')))
    urls.pop(str(base.get('URL')), None)
    base['Otros_enlaces'] = ' '.join(urls)
    return base


def unify(jobs: Iterable[Job]) -> list[Job]:
    """Ofertas sin repetidas, en el orden en que apareció cada una. Cada oferta trae `Portales`
    ("Bumeran, Computrabajo") y `Otros_enlaces` (las URLs de las copias)."""
    groups: list[list[Job]] = []
    by_url: dict[str, int] = {}
    by_key: dict[tuple[str, str], list[int]] = {}
    for job in jobs:
        url = _url_key(job.get('URL'))
        key = (_norm(job.get('Title')), company_key(job.get('Company')))
        index: Optional[int] = by_url.get(url) if url else None
        if index is None and all(key):
            index = next((i for i in by_key.get(key, []) if all(_compatible(job, other) for other in groups[i])), None)
        if index is None:
            index = len(groups)
            groups.append([])
        groups[index].append(job)
        if all(key) and index not in by_key.setdefault(key, []):
            by_key[key].append(index)
        if url:
            by_url.setdefault(url, index)
    return [_merge(group) for group in groups]
