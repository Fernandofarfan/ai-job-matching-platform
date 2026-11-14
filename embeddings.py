"""Similitud semántica CV-oferta con embeddings de Gemini (MATCHING_BACKEND=embeddings).

TF-IDF solo cuenta palabras en común: "desarrollador backend" y "programador de APIs"
dan 0. Los embeddings comparan significado. Si la IA no está disponible, falla o se
llegó al tope mensual de tokens, `similarity` devuelve None y se usa TF-IDF.

MATCHING_BACKEND_BY_LANGUAGE elige el backend según el idioma del CV, por encima de
MATCHING_BACKEND (ej. "es=embeddings,pt=embeddings": TF-IDF compara mal un CV en español
con una oferta en inglés). Vacío por defecto: todo usa MATCHING_BACKEND.
"""
import hashlib
import logging
import math
import os
import re
from collections import OrderedDict
from typing import Optional

logger = logging.getLogger(__name__)

MAX_CHARS = 8000
_CACHE_SIZE = 512
# La similitud coseno entre textos de empleo casi nunca baja de ~0.5 ni pasa de ~0.9;
# se reescala a 0-100 para que pese como el TF-IDF en calculate_overall_match.
_FLOOR = float(os.getenv('EMBEDDING_SIM_FLOOR', '0.5'))
_CEIL = float(os.getenv('EMBEDDING_SIM_CEIL', '0.9'))

BACKENDS = ('tfidf', 'embeddings')
LANGUAGES = ('es', 'pt', 'en')
# Palabras frecuentes y exclusivas de cada idioma en CVs y ofertas.
_STOPWORDS = {
    'es': {'el', 'la', 'los', 'las', 'y', 'del', 'con', 'una', 'años', 'experiencia', 'desarrollo', 'trabajo',
           'conocimientos', 'empresa', 'también', 'sí'},
    'pt': {'o', 'os', 'as', 'e', 'em', 'do', 'da', 'dos', 'das', 'com', 'uma', 'não', 'anos', 'experiência',
           'desenvolvimento', 'trabalho', 'conhecimentos', 'empresa', 'também', 'você'},
    'en': {'the', 'and', 'with', 'of', 'in', 'to', 'on', 'experience', 'years', 'development', 'work',
           'knowledge', 'company', 'also', 'you', 'we'},
}
_WORD = re.compile(r"[^\W\d_]+", re.UNICODE)

_client = None
_cache: "OrderedDict[str, list]" = OrderedDict()


def detect_language(text: str) -> str:
    """'es', 'pt' o 'en' según las palabras frecuentes del texto; 'en' si no hay ninguna."""
    words = _WORD.findall(str(text or '').lower()[:MAX_CHARS])
    hits = {lang: sum(w in stop for w in words) for lang, stop in _STOPWORDS.items()}
    best = max(LANGUAGES, key=lambda lang: hits[lang])
    return best if hits[best] else 'en'


def backends_by_language() -> dict[str, str]:
    """MATCHING_BACKEND_BY_LANGUAGE como {idioma: backend}; ignora idiomas o backends desconocidos."""
    found = {}
    for part in os.getenv('MATCHING_BACKEND_BY_LANGUAGE', '').split(','):
        lang, _, backend = (x.strip().lower() for x in part.partition('='))
        if lang in LANGUAGES and backend in BACKENDS:
            found[lang] = backend
        elif part.strip():
            logger.warning(f'MATCHING_BACKEND_BY_LANGUAGE: se ignora "{part.strip()}"')
    return found


def backend_for(language: Optional[str] = None) -> str:
    """Backend para un CV en ese idioma: el de MATCHING_BACKEND_BY_LANGUAGE o, si no, MATCHING_BACKEND."""
    if language:
        override = backends_by_language().get(language)
        if override:
            return override
    return os.getenv('MATCHING_BACKEND', 'tfidf').strip().lower()


def enabled(language: Optional[str] = None):
    """True si el backend para ese idioma es embeddings y hay GEMINI_API_KEY (o un cliente inyectado)."""
    if backend_for(language) != 'embeddings':
        return False
    return _client is not None or bool(os.getenv('GEMINI_API_KEY'))


def configure(client):
    """Inyecta un cliente de google-genai (tests) o None para crearlo desde GEMINI_API_KEY."""
    global _client
    _client = client
    _cache.clear()


def _get_client():
    global _client
    if _client is None:
        from google import genai
        _client = genai.Client(api_key=os.getenv('GEMINI_API_KEY'))
    return _client


def _model():
    return os.getenv('GEMINI_EMBEDDING_MODEL', 'gemini-embedding-001')


def _key(text):
    return hashlib.sha256(f"{_model()}\0{text}".encode('utf-8')).hexdigest()


def embed(texts):
    """Vectores de cada texto (con caché en memoria), o None si no se pudo."""
    texts = [str(t or '')[:MAX_CHARS] for t in texts]
    found = {}
    for text in dict.fromkeys(texts):
        key = _key(text)
        if key in _cache:
            _cache.move_to_end(key)
            found[text] = _cache[key]
    missing = [t for t in dict.fromkeys(texts) if t not in found]
    if missing:
        import accounts
        import ai_usage
        if accounts.ai_consent_missing():
            logger.info("La cuenta no dio permiso para usar la IA; matching con TF-IDF")
            return None
        if ai_usage.budget_exceeded():
            logger.info("Tope mensual de tokens de IA alcanzado; matching con TF-IDF")
            return None
        try:
            from google.genai import types
            response = _get_client().models.embed_content(
                model=_model(), contents=missing,
                config=types.EmbedContentConfig(task_type='SEMANTIC_SIMILARITY'),
            )
            vectors = [list(e.values) for e in response.embeddings]
        except Exception as e:
            logger.warning(f"Embeddings no disponibles ({type(e).__name__}); matching con TF-IDF")
            return None
        if len(vectors) != len(missing):
            return None
        # La API de embeddings no informa tokens: ~4 caracteres por token
        ai_usage.record(sum(len(t) for t in missing) // 4, 0)
        for text, vector in zip(missing, vectors, strict=True):
            found[text] = vector
            _cache[_key(text)] = vector
            while len(_cache) > _CACHE_SIZE:
                _cache.popitem(last=False)
    return [found[t] for t in texts]


def cosine(a, b):
    """Similitud coseno entre dos vectores (0 si alguno es nulo)."""
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    norm = math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b))
    return dot / norm if norm else 0.0


def similarity(profile_text, job_text):
    """Similitud semántica 0-100 entre CV y oferta, o None para usar TF-IDF."""
    if not str(profile_text or '').strip() or not str(job_text or '').strip():
        return None
    if not enabled(detect_language(profile_text) if backends_by_language() else None):
        return None
    vectors = embed([profile_text, job_text])
    if vectors is None:
        return None
    scaled = (cosine(*vectors) - _FLOOR) / (_CEIL - _FLOOR)
    return round(max(0.0, min(1.0, scaled)) * 100, 1)
