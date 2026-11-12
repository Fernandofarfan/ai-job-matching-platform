"""Puntaje ATS de un CV (0-100) sin IA: legibilidad para filtros automáticos y palabras clave de la oferta."""
import re
import unicodedata
from collections import Counter

SECTIONS = {
    'experience': ('experiencia', 'experience', 'trayectoria', 'antecedentes laborales'),
    'education': ('educacion', 'education', 'formacion', 'estudios'),
    'skills': ('habilidades', 'skills', 'competencias', 'conocimientos', 'tecnologias'),
}
STOPWORDS = set("""
a al algo ante antes como con contra cual cuando de del desde donde durante e el ella ellos en entre era es esa ese
eso esta este esto estos hacia hasta la las le les lo los mas me mi muy no nos o otra otro para pero por que se ser si
sin sobre su sus tambien te tiene tu un una uno unos y ya buscamos busca requisitos experiencia empresa trabajo equipo
puesto deseable excluyente anos años conocimiento conocimientos manejo nivel ofrecemos beneficios modalidad
the and or of to in for with on at by an be is are as from this that you we our your will have has work team
experience years job role skills strong knowledge plus etc
""".split())
WEIGHTS = {'contact': 15, 'sections': 20, 'length': 10, 'achievements': 10, 'dates': 5, 'keywords': 40}
MAX_KEYWORDS = 25


def _norm(text):
    """Minúsculas y sin tildes."""
    return unicodedata.normalize('NFKD', text or '').encode('ascii', 'ignore').decode().lower()


def _tokens(text):
    return re.findall(r'[a-z][a-z0-9+#./-]{1,30}', _norm(text))


def job_keywords(job_description, limit=MAX_KEYWORDS):
    """Términos más repetidos de la oferta, sin palabras vacías."""
    words = [t.strip('.-/') for t in _tokens(job_description)]
    counts = Counter(w for w in words if len(w) > 2 and w not in STOPWORDS and not w.isdigit())
    return [w for w, _ in counts.most_common(limit)]


def _check(check_id, label, ratio, tip):
    ratio = max(0.0, min(1.0, ratio))
    return {'id': check_id, 'label': label, 'passed': ratio >= 0.99, 'ratio': round(ratio, 2), 'tip': tip}


def score_resume(resume_text, job_description=''):
    """Puntaje, chequeos con sugerencias y palabras clave encontradas/faltantes."""
    norm = _norm(resume_text)
    words = len(norm.split())
    lines = [line.strip() for line in norm.splitlines() if line.strip()]

    contact = [
        bool(re.search(r'[\w.+-]+@[\w-]+\.[\w.]+', norm)),
        bool(re.search(r'\+?\d[\d\s().-]{7,}\d', norm)),
        'linkedin.com' in norm or 'github.com' in norm,
    ]
    found_sections = [name for name, titles in SECTIONS.items()
                      if any(any(line.startswith(t) for t in titles) for line in lines)]
    achievements = len(re.findall(r'\d+\s?%|\$\s?\d|\b\d+\s?(?:k|m|mil|millones|usuarios|clientes|personas|servicios|proyectos)\b', norm))
    dates = len(re.findall(r'\b(?:19|20)\d{2}\b', norm))

    checks = [
        _check('contact', 'Datos de contacto', sum(contact) / 3,
               'Incluí email, teléfono y un perfil de LinkedIn o GitHub en texto plano.'),
        _check('sections', 'Secciones estándar', len(found_sections) / len(SECTIONS),
               'Usá títulos reconocibles: "Experiencia", "Educación" y "Habilidades".'),
        _check('length', 'Extensión', 1.0 if 250 <= words <= 1100 else (words / 250 if words < 250 else 1100 / words),
               'Apuntá a 1-2 páginas (entre 250 y 1.100 palabras).'),
        _check('achievements', 'Logros medibles', achievements / 3,
               'Cuantificá logros: porcentajes, montos, usuarios o equipos.'),
        _check('dates', 'Fechas en la experiencia', dates / 2,
               'Indicá mes/año de inicio y fin en cada puesto.'),
    ]

    keywords = job_keywords(job_description)
    matched = [k for k in keywords if re.search(rf'(?<![a-z0-9]){re.escape(k)}(?![a-z0-9])', norm)]
    missing = [k for k in keywords if k not in matched]
    weights = dict(WEIGHTS)
    if keywords:
        checks.append(_check('keywords', 'Palabras clave de la oferta', len(matched) / len(keywords) / 0.7,
                             'Sumá, si son ciertas, las palabras clave que faltan con el mismo término de la oferta.'))
    else:
        weights.pop('keywords')

    total = sum(weights.values())
    score = round(sum(weights[c['id']] * c['ratio'] for c in checks) * 100 / total)
    return {'score': score, 'checks': checks, 'matched_keywords': matched, 'missing_keywords': missing}
