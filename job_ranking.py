"""Ranking personal: aprende del tracker qué ofertas te interesan y reordena las nuevas.

Positivas: las que pasaron a "postulando" o más (entrevista, negociación y aceptada pesan doble).
Negativas: las guardadas que llevan `RANKING_STALE_DAYS` días sin que te postules.
"Me interesa" / "no me interesa" (job_feedback.py) pesan doble de cada lado: es lo que dijiste explícitamente.
Modelo: Naive Bayes con suavizado de Laplace sobre palabras del título, empresa, ubicación y portal.
Con menos de `MIN_EXAMPLES` ejemplos de cada clase no personaliza.
Peso del ranking frente al match: con al menos `MIN_TUNING` ofertas marcadas de cada lado se elige, por cuenta,
el que mejor ordena "me interesa" por encima de "no me interesa" (AUC, con la preferencia de cada oferta
calculada sin esa oferta); si no, `RANKING_WEIGHT`.
"""
import logging
import math
import os
import re
import time
import unicodedata
from collections import Counter
from datetime import date, datetime

logger = logging.getLogger(__name__)

MIN_EXAMPLES = 3
MIN_TUNING = 5
MAX_TUNING_ROWS = 300
WEIGHTS = tuple(i / 10 for i in range(9))
FEEDBACK_WEIGHT = 2
POSITIVE = {'applying': 1, 'applied': 1, 'rejected': 1, 'interviewing': 2, 'negotiating': 2, 'accepted': 2}
_STOPWORDS = {
    'para', 'con', 'por', 'los', 'las', 'del', 'una', 'and', 'the', 'for', 'with', 'sin',
    'sr', 'ssr', 'jr', 'semi', 'senior', 'junior', 'remoto', 'hibrido', 'presencial',
}
_CACHE_SECONDS = 600
_cache: dict = {}


def _weight():
    """Peso del ranking personal frente al match del CV (0 a 1)."""
    try:
        return min(max(float(os.getenv('RANKING_WEIGHT', '0.3')), 0.0), 1.0)
    except ValueError:
        return 0.3


def _stale_days():
    """Días tras los que una oferta guardada sin postular cuenta como descartada."""
    try:
        return max(int(os.getenv('RANKING_STALE_DAYS', '14')), 1)
    except ValueError:
        return 14


def _norm(text):
    """Minúsculas, sin acentos y con espacios simples."""
    text = unicodedata.normalize('NFKD', str(text or '')).encode('ascii', 'ignore').decode().lower()
    return re.sub(r'\s+', ' ', text).strip()


def _get(job, *keys):
    """Primer valor no vacío entre las claves (tracker en minúscula, CSV capitalizado)."""
    for key in keys:
        value = job.get(key)
        if value is not None and str(value).strip() and str(value).lower() != 'nan':
            return str(value)
    return ''


def features(job):
    """Rasgos de una oferta (dict del tracker o fila de un CSV de scraping)."""
    from tracker_stats import portal_of

    feats = {f'w:{w}' for w in re.findall(r'[a-z0-9+#.]{3,}', _norm(_get(job, 'title', 'Title')))
             if w not in _STOPWORDS}
    company = _norm(_get(job, 'company', 'Company'))
    if company:
        feats.add(f'empresa:{company}')
    location = _norm(_get(job, 'location', 'Location')).split(',')[0].strip()
    if location:
        feats.add(f'lugar:{location}')
    feats.add(f'portal:{portal_of(_get(job, "job_link", "Job_Link", "URL", "url")).lower()}')
    return feats


def _as_date(value):
    """Fecha de un valor date/datetime/ISO; None si no se puede leer."""
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return datetime.strptime(str(value)[:10], '%Y-%m-%d').date() if value else None
    except ValueError:
        return None


def label(job, today=None):
    """Peso positivo (>0), negativo (<0) o 0 si la postulación todavía no dice nada."""
    if job.get('interested') is not None:
        return FEEDBACK_WEIGHT if job['interested'] else -FEEDBACK_WEIGHT
    status = job.get('status')
    if status in POSITIVE:
        return POSITIVE[status]
    if status == 'bookmarked':
        saved = _as_date(job.get('created_at') or job.get('applied_date'))
        if saved and ((today or date.today()) - saved).days >= _stale_days():
            return -1
    return 0


def train(applications, today=None):
    """Modelo {'pos', 'neg', 'n_pos', 'n_neg', 'vocab'} o None si no hay ejemplos suficientes."""
    pos, neg = Counter(), Counter()
    n_pos = n_neg = 0
    for job in applications:
        weight = label(job, today)
        if weight == 0:
            continue
        feats = features(job)
        if weight > 0:
            n_pos += weight
            pos.update({f: weight for f in feats})
        else:
            n_neg += -weight
            neg.update({f: -weight for f in feats})
    if n_pos < MIN_EXAMPLES or n_neg < MIN_EXAMPLES:
        return None
    return {'pos': pos, 'neg': neg, 'n_pos': n_pos, 'n_neg': n_neg}


def _log_odds(model, feat):
    """Log-odds suavizado (Laplace) de que el rasgo aparezca en ofertas que te interesan."""
    return math.log((model['pos'][feat] + 1) / (model['n_pos'] + 2)) - math.log((model['neg'][feat] + 1) / (model['n_neg'] + 2))


def preference(model, job):
    """0-100: qué tan parecida es la oferta a las que elegiste (50 = neutral)."""
    known = [f for f in features(job) if model['pos'][f] or model['neg'][f]]
    if not known:
        return 50.0
    z = sum(_log_odds(model, f) for f in known) / math.sqrt(len(known))
    return round(100 / (1 + math.exp(-z)), 1)


def _auc(pos, neg):
    """Probabilidad de que un puntaje de `pos` supere a uno de `neg` (empates cuentan medio)."""
    wins = sum(1.0 if p > n else 0.5 if p == n else 0.0 for p in pos for n in neg)
    return wins / (len(pos) * len(neg))


def _same_offer(a, b):
    """True si dos ejemplos son la misma oferta (mismo enlace, o mismo título y empresa)."""
    link_a = _get(a, 'job_link', 'Job_Link', 'URL', 'url').strip()
    if link_a and link_a == _get(b, 'job_link', 'Job_Link', 'URL', 'url').strip():
        return True
    title_a, company_a = _norm(_get(a, 'title', 'Title')), _norm(_get(a, 'company', 'Company'))
    return bool(title_a and company_a) and (title_a, company_a) == (
        _norm(_get(b, 'title', 'Title')), _norm(_get(b, 'company', 'Company')))


def learn_weight(examples, today=None):
    """Peso del ranking que mejor separa "me interesa" de "no me interesa" en lo que marcó la cuenta.

    {'weight', 'auc', 'match_auc', 'examples'} o None si no hay `MIN_TUNING` ofertas marcadas con match de cada
    lado. La preferencia de cada oferta marcada sale de un modelo entrenado sin ella ni sus copias (p. ej. la del
    tracker), para no medir con trampa.
    Entre pesos con el mismo AUC gana el más cercano a `RANKING_WEIGHT`.
    """
    marked = [e for e in examples if e.get('interested') is not None and e.get('match_score') is not None]
    marked = marked[-MAX_TUNING_ROWS:]
    if sum(1 for e in marked if e['interested']) < MIN_TUNING or sum(1 for e in marked if not e['interested']) < MIN_TUNING:
        return None
    held_out = []
    for row in marked:
        model = train([e for e in examples if e is not row and not _same_offer(row, e)], today)
        held_out.append((row['interested'], float(row['match_score']), preference(model, row) if model else 50.0))
    default = _weight()

    def auc_at(weight):
        scores = [(interested, (1 - weight) * match + weight * pref) for interested, match, pref in held_out]
        return _auc([s for i, s in scores if i], [s for i, s in scores if not i])
    best = max(WEIGHTS, key=lambda w: (round(auc_at(w), 6), -abs(w - default)))
    return {'weight': best, 'auc': round(auc_at(best), 3), 'match_auc': round(auc_at(0.0), 3),
            'examples': len(held_out)}


def top_signals(model, n=8):
    """Rasgos que más suben y más bajan una oferta, para mostrar qué aprendió."""
    feats = set(model['pos']) | set(model['neg'])
    scored = sorted(((round(_log_odds(model, f), 2), f) for f in feats), reverse=True)
    pretty = [{'feature': f.split(':', 1)[1], 'kind': f.split(':', 1)[0], 'weight': w} for w, f in scored]
    return {'likes': [p for p in pretty if p['weight'] > 0][:n],
            'dislikes': [p for p in reversed(pretty) if p['weight'] < 0][:n]}


def _cache_key():
    """Un modelo por cuenta: el ranking de una no puede mostrar las empresas que eligió otra."""
    import accounts
    return accounts.current_user_id()


def invalidate():
    """Descarta el modelo cacheado de la cuenta actual (p. ej. después de marcar una oferta)."""
    _cache.pop(_cache_key(), None)


def load_model():
    """Entrena con el tracker y lo marcado en las ofertas (cacheado unos minutos por cuenta); None sin datos."""
    key = _cache_key()
    cached = _cache.get(key)
    if cached and time.monotonic() - cached[0] < _CACHE_SECONDS:
        return cached[1]
    examples = []
    try:
        from db_config import db_manager
        examples += db_manager.get_applications() or []
    except Exception as e:
        logger.warning(f"Ranking personal sin datos del tracker: {e}")
    try:
        import job_feedback
        examples += job_feedback.examples()
    except Exception as e:
        logger.warning(f"Ranking personal sin \"me interesa\": {e}")
    model = train(examples) if examples else None
    if model is not None:
        model['tuning'] = learn_weight(examples)
        if model['tuning']:
            model['weight'] = model['tuning']['weight']
    _cache[key] = (time.monotonic(), model)
    return model


def rank(jobs, model=None, match_key='match_percent'):
    """Agrega `preference` y `ranked_score` y ordena de mayor a menor; sin modelo deja el orden por match."""
    model = model if model is not None else load_model()
    weight = model.get('weight', _weight()) if model else _weight()
    for job in jobs:
        match = float(job.get(match_key) or 0)
        if model is None:
            job['ranked_score'] = match
            continue
        job['preference'] = preference(model, job)
        job['ranked_score'] = round((1 - weight) * match + weight * job['preference'], 1)
    return sorted(jobs, key=lambda j: j['ranked_score'], reverse=True)
