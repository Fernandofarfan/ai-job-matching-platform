"""Unifica la misma oferta publicada en varios portales (búsqueda universal).

Dos ofertas son la misma si tienen la misma URL, o el mismo título y la misma empresa (sin tildes,
mayúsculas, puntuación ni sufijos societarios, con "Senior" igual a "Sr", sin el nombre de la empresa en el título y con
las palabras en inglés traducidas: "Data Analyst" es "Analista de Datos") en ubicaciones compatibles.
La precisión y la cobertura se miden con los pares etiquetados de eval/dedup_pairs.json (scripts/eval_dedup.py). Las empresas
"Confidencial" o vacías no se unifican: sin empresa no hay forma de saber si es la misma oferta.
"""
import re
import unicodedata
from collections.abc import Iterable
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit

Job = dict[str, Any]

PLACEHOLDERS = {'', 'confidencial', 'empresa confidencial', 'reservado', 'no especificado', 'no especificada',
                'n a', 'na', 'nan', 'none', 'confidential', 'not specified', 'unknown'}
COMPANY_SUFFIXES = {'sa', 'srl', 'sas', 'sau', 'sl', 'sacif', 'saic', 'saci', 'sacifi', 'cicsa', 'saicf', 'sca', 'ltda', 'inc', 'llc', 'corp', 'corporation',
                    'ltd', 'limited', 'gmbh', 'cv', 'de'}
GENERIC_PLACES = {'argentina', 'chile', 'uruguay', 'paraguay', 'bolivia', 'peru', 'colombia', 'mexico', 'brasil',
                  'brazil', 'latam', 'remoto', 'remote', 'hibrido', 'presencial', 'reciente', 'provincia', 'de', 'del'}
PLACE_ALIASES = {'ciudad autonoma de buenos aires': 'capital federal', 'caba': 'capital federal'}
PROVINCES = {'buenos aires', 'capital federal', 'catamarca', 'chaco', 'chubut', 'cordoba', 'corrientes', 'entre rios',
             'formosa', 'jujuy', 'la pampa', 'la rioja', 'mendoza', 'misiones', 'neuquen', 'rio negro', 'salta',
             'san juan', 'san luis', 'santa cruz', 'santa fe', 'santiago del estero', 'tierra del fuego', 'tucuman'}
SENIORITY = ((r'\bsemi ?senior\b', 'ssr'), (r'\bsenior\b', 'sr'), (r'\bjunior\b', 'jr'))
# Parámetros de seguimiento: la misma oferta llega con distintos según de dónde se abrió.
TRACKING_PARAMS = {'trk', 'trkinfo', 'refid', 'trackingid', 'position', 'pagenum', 'from', 'src', 'ref', 'origin',
                   'utm', 'fbclid', 'gclid', 'tk', 'vjs', 'advn', 'adid', 'sjdu', 'currentjobid', 'ebp', 'lipi'}


def _norm(value: object) -> str:
    """Minúsculas ASCII, sin puntos y con el resto de la puntuación como espacios, salvo `+` y `#` (C++, C#)."""
    text = unicodedata.normalize('NFKD', str(value or '')).encode('ascii', 'ignore').decode().lower()
    text = re.sub(r'[^a-z0-9+# ]+', ' ', text.replace('.', ''))
    return ' '.join(text.split())


def _known(value: object) -> bool:
    """El campo trae un dato real y no un "Confidencial" / "No especificado"."""
    return _norm(value) not in PLACEHOLDERS


# Palabras de puestos en inglés con su traducción, para que "Data Analyst" y "Analista de Datos" den la misma clave.
TITLE_WORDS = {'analyst': 'analista', 'data': 'datos', 'developer': 'desarrollador', 'engineer': 'ingeniero',
               'manager': 'gerente', 'designer': 'disenador', 'sales': 'ventas', 'accountant': 'contador',
               'cashier': 'cajero', 'support': 'soporte', 'software': 'software', 'business': 'negocio'}
TITLE_STOPWORDS = {'de', 'del', 'la', 'el', 'los', 'las', 'y', 'of', 'and', 'the'}
COMPANY_MARKERS = (' en ', ' at ', ' para ', ' - ', ' | ', ' / ')


def title_key(title: object, company: object = '') -> str:
    """Título normalizado: seniority unificado ("Senior" y "Sr." dan "sr"), sin el nombre de la empresa
    ("Cajero - Coto" da "cajero") y con las palabras en inglés traducidas y ordenadas ("Data Analyst" y
    "Analista de Datos" dan lo mismo)."""
    raw = str(title or '')
    company = company_key(company)
    if company:
        for marker in COMPANY_MARKERS:
            head, sep, tail = raw.lower().rpartition(marker)
            if sep and head.strip() and company_key(tail) == company:
                raw = raw[:len(head)]
                break
    text = _norm(raw)
    for pattern, short in SENIORITY:
        text = re.sub(pattern, short, text)
    return ' '.join(sorted(TITLE_WORDS.get(w, w) for w in text.split() if w not in TITLE_STOPWORDS))


def company_key(company: object) -> str:
    """Empresa normalizada sin sufijos societarios: "Acme S.A." y "ACME" dan "acme"; vacía si es confidencial."""
    if not _known(company):
        return ''
    words = _norm(company).split()
    while len(words) > 1 and words[-1] in COMPANY_SUFFIXES:
        words.pop()
    return ' '.join(words)


def _place_text(location: object) -> str:
    """Ubicación normalizada, con "CABA" como "capital federal"."""
    text = f' {_norm(location)} ' if _known(location) else ''
    for alias, name in PLACE_ALIASES.items():
        text = text.replace(f' {alias} ', f' {name} ')
    return text


def _places(location: object) -> set[str]:
    """Palabras de la ubicación que identifican un lugar dentro de la provincia (sin países ni "Remoto"). De la provincia
    se quita solo la última mención: en "Córdoba, Córdoba" la primera es la ciudad. "Capital" junto a una provincia es
    esa ciudad ("Córdoba Capital", "Capital, Córdoba"). La ciudad de Buenos Aires es Capital Federal, que queda: es un
    lugar distinto del resto de la provincia de Buenos Aires."""
    text = _place_text(location)
    for province in PROVINCES - {'capital federal'}:
        matches = list(re.finditer(rf'(?<= ){province}(?= )', text))
        if matches:
            text = re.sub(r'(?<= )capital(?= )(?! federal )', province, text)
            matches = list(re.finditer(rf'(?<= ){province}(?= )', text))
            text = text[:matches[-1].start()] + text[matches[-1].end():]
    words = set(text.split()) - GENERIC_PLACES
    return {'capital', 'federal'} if words == {'buenos', 'aires'} else words


def _provinces(location: object) -> set[str]:
    """Provincias argentinas nombradas en la ubicación; Capital Federal cuenta como Buenos Aires."""
    text = _place_text(location)
    found = {p for p in PROVINCES if f' {p} ' in text}
    return {'buenos aires' if p == 'capital federal' else p for p in found}


def _url_key(url: object) -> str:
    """URL sin parámetros de seguimiento, fragmento ni barra final; vacía si no es http(s). Los demás parámetros
    quedan: en Indeed (`viewjob?jk=...`) son los que distinguen una oferta de otra."""
    text = str(url or '').strip()
    if not text.startswith(('http://', 'https://')):
        return ''
    parts = urlsplit(text)
    query = sorted((k, v) for k, v in parse_qsl(parts.query)
                   if k.lower() not in TRACKING_PARAMS and not k.lower().startswith('utm_'))
    return f"{parts.netloc.lower()}{parts.path.rstrip('/')}" + (f'?{urlencode(query)}' if query else '')


def _source(job: Job) -> str:
    """Portal de la oferta."""
    return str(job.get('Fuente') or job.get('Source') or '')


def _compatible(a: Job, b: Job) -> bool:
    """Ubicaciones que pueden ser la misma: no nombran provincias distintas ("San Justo, Buenos Aires" y "San Justo,
    Santa Fe" no) y alguna solo dice la provincia o el país, o comparten un lugar ("Ciudad Autónoma de Buenos Aires" y
    "Buenos Aires" sí; "CABA" y "La Plata, Buenos Aires" no)."""
    provinces_a, provinces_b = _provinces(a.get('Location')), _provinces(b.get('Location'))
    if provinces_a and provinces_b and not provinces_a & provinces_b:
        return False
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
        key = (title_key(job.get('Title'), job.get('Company')), company_key(job.get('Company')))
        index: int | None = by_url.get(url) if url else None
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
