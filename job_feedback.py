""""Me interesa / no me interesa" por oferta.

Ordena los resultados (entra al ranking personal como ejemplo explícito), saca de las alertas las ofertas
descartadas y mide el matching contra lo que eligen los usuarios: qué tan seguido una oferta marcada
"me interesa" tiene más match que una marcada "no me interesa" (AUC; 0,5 = al azar, 1 = siempre).
"""
import logging
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, Integer, String, UniqueConstraint, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Mapped, mapped_column

import job_alerts
from job_alerts import Base, fingerprint

logger = logging.getLogger(__name__)


class JobFeedback(Base):
    """Lo que una cuenta dijo de una oferta; la huella es la de las alertas (título y empresa, sin portal)."""
    __tablename__ = 'job_feedback'
    __table_args__ = (UniqueConstraint('user_id', 'fingerprint', name='uq_job_feedback_user_fingerprint'),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int | None] = mapped_column(Integer, index=True)
    fingerprint: Mapped[str] = mapped_column(String(40), nullable=False)
    interested: Mapped[bool] = mapped_column(Boolean, nullable=False)
    title: Mapped[str | None] = mapped_column(String(300))
    company: Mapped[str | None] = mapped_column(String(200))
    location: Mapped[str | None] = mapped_column(String(200))
    url: Mapped[str | None] = mapped_column(String(1000))
    match_score: Mapped[float | None] = mapped_column(Float)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)


def _text(job, name, limit):
    """Campo de la oferta (mayúscula de los scrapers o minúscula), recortado al largo de la columna."""
    value = job.get(name.capitalize()) or job.get(name) or ''
    return str(value).strip()[:limit] or None


def _url(job):
    """Enlace de la oferta, solo http(s)."""
    for key in ('job_link', 'Job_Link', 'URL', 'url'):
        value = str(job.get(key) or '').strip()
        if value.startswith(('http://', 'https://')):
            return value[:1000]
    return None


def _score(value):
    """Match 0-100 o None si no viene o no es un número."""
    try:
        score = float(value)
    except (TypeError, ValueError):
        return None
    return score if 0 <= score <= 100 else None


def set_feedback(job, interested, match_score=None):
    """Guarda "me interesa" (True), "no me interesa" (False) o lo borra (None) para la cuenta actual."""
    if not _text(job, 'title', 300):
        raise ValueError('La oferta no tiene título')
    fp = fingerprint(job)
    for attempt in range(2):  # dos pedidos a la vez para la misma oferta: el segundo actualiza
        try:
            with job_alerts._sessions()() as session:
                row = session.scalars(select(JobFeedback).where(
                    job_alerts._mine(JobFeedback), JobFeedback.fingerprint == fp)).first()
                if interested is None:
                    if row is not None:
                        session.delete(row)
                else:
                    if row is None:
                        import accounts
                        row = JobFeedback(user_id=accounts.current_user_id(), fingerprint=fp)
                        session.add(row)
                    row.interested = bool(interested)
                    row.title, row.company = _text(job, 'title', 300), _text(job, 'company', 200)
                    row.location, row.url = _text(job, 'location', 200), _url(job)
                    row.match_score = _score(match_score)
                session.commit()
                return
        except IntegrityError:
            if attempt:
                raise


def _rows(fingerprints=None):
    """Filas de la cuenta actual, opcionalmente solo las de esas huellas."""
    query = select(JobFeedback).where(job_alerts._mine(JobFeedback))
    if fingerprints is not None:
        query = query.where(JobFeedback.fingerprint.in_(list(fingerprints)))
    with job_alerts._sessions()() as session:
        return list(session.scalars(query))


def states(jobs):
    """True / False / None por oferta, en el mismo orden."""
    fps = [fingerprint(job) for job in jobs]
    if not fps:
        return []
    known = {row.fingerprint: row.interested for row in _rows(set(fps))}
    return [known.get(fp) for fp in fps]


def drop_rejected(jobs):
    """Las ofertas sin "no me interesa" de la cuenta actual."""
    if not jobs:
        return jobs
    rejected = {row.fingerprint for row in _rows({fingerprint(job) for job in jobs}) if not row.interested}
    return [job for job in jobs if fingerprint(job) not in rejected]


def examples():
    """Ofertas marcadas, con los campos del ranking personal y `interested`."""
    return [{'title': r.title, 'company': r.company, 'location': r.location, 'job_link': r.url,
             'interested': r.interested, 'match_score': r.match_score} for r in _rows()]


def agreement(rows):
    """Cuántas ofertas se marcaron de cada lado y AUC del match: probabilidad de que una "me interesa"
    tenga más match que una "no me interesa" (empates cuentan medio). None si falta un lado."""
    pos = [r['match_score'] for r in rows if r['interested'] and r.get('match_score') is not None]
    neg = [r['match_score'] for r in rows if not r['interested'] and r.get('match_score') is not None]
    auc = None
    if pos and neg:
        wins = sum(1.0 if p > n else 0.5 if p == n else 0.0 for p in pos for n in neg)
        auc = round(wins / (len(pos) * len(neg)), 3)
    return {'interested': sum(1 for r in rows if r['interested']),
            'not_interested': sum(1 for r in rows if not r['interested']), 'match_auc': auc}


def my_agreement():
    """`agreement` de la cuenta actual."""
    return agreement([{'interested': r.interested, 'match_score': r.match_score} for r in _rows()])


def all_agreement():
    """`agreement` de todas las cuentas juntas (sin datos de quién marcó qué), para medir el matching."""
    with job_alerts._sessions()() as session:
        rows = session.execute(select(JobFeedback.interested, JobFeedback.match_score)).all()
    return agreement([{'interested': i, 'match_score': s} for i, s in rows])
