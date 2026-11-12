"""Alertas de empleo: búsquedas guardadas que corren solas y avisan solo por ofertas nuevas.

Una oferta se identifica por título + empresa normalizados, así la misma publicación en
varios portales se avisa una sola vez (tabla seen_jobs).
"""
import hashlib
import logging
import re
import unicodedata
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, Float, Integer, String, UniqueConstraint, select

import accounts
import scraper_stats
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.exc import IntegrityError

logger = logging.getLogger(__name__)


class Base(DeclarativeBase):
    """Base declarativa de los modelos de este módulo."""


PORTALS = ('computrabajo', 'bumeran', 'zonajobs', 'getonboard')
CHANNELS = ('email', 'telegram', 'push')
MAX_JOBS_PER_PORTAL = 30
# Las que no entran en un aviso quedan sin marcar y salen en el siguiente
MAX_JOBS_PER_ALERT = 15
_ANONYMOUS = {'', 'confidential', 'confidencial', 'empresa confidencial', 'importante empresa'}

_session_factory = None


class SavedSearch(Base):
    """Búsqueda que se repite periódicamente y avisa por los canales elegidos."""
    __tablename__ = 'saved_searches'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int | None] = mapped_column(Integer, index=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    position: Mapped[str] = mapped_column(String(200), nullable=False)
    location: Mapped[str] = mapped_column(String(200), nullable=False, default='')
    portals: Mapped[Any] = mapped_column(JSON, nullable=False)
    channels: Mapped[Any] = mapped_column(JSON, nullable=False)
    min_score: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime | None] = mapped_column(DateTime, default=datetime.now)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime)
    last_result: Mapped[str | None] = mapped_column(String(255))

    def to_dict(self):
        """Representación serializable (vista y tareas de Celery)."""
        return {
            'id': self.id, 'name': self.name, 'position': self.position,
            'location': self.location, 'portals': list(self.portals or []),
            'channels': list(self.channels or []), 'min_score': self.min_score,
            'active': self.active, 'last_run_at': self.last_run_at,
            'last_result': self.last_result,
        }


class SeenJob(Base):
    """Oferta ya avisada; su huella evita repetirla aunque aparezca en otro portal."""
    __tablename__ = 'seen_jobs'

    __table_args__ = (UniqueConstraint('user_id', 'fingerprint', name='uq_seen_jobs_user_fingerprint'),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int | None] = mapped_column(Integer, index=True)
    fingerprint: Mapped[str] = mapped_column(String(40), nullable=False)
    title: Mapped[str | None] = mapped_column(String(300))
    company: Mapped[str | None] = mapped_column(String(200))
    url: Mapped[str | None] = mapped_column(String(1000))
    source: Mapped[str | None] = mapped_column(String(50))
    search_id: Mapped[int | None] = mapped_column(Integer)
    first_seen_at: Mapped[datetime | None] = mapped_column(DateTime, default=datetime.now)


def configure(session_factory):
    """Usa la fábrica de sesiones dada (tests) o None para volver a MySQL."""
    global _session_factory
    _session_factory = session_factory


def _sessions():
    """Fábrica de sesiones de MySQL (las tablas las crea Alembic)."""
    global _session_factory
    if _session_factory is None:
        from models import SessionLocal
        _session_factory = SessionLocal
    return _session_factory


def _normalize(text):
    """Minúsculas, sin acentos ni signos: 'Analista  Sr. (Python)' -> 'analista sr python'."""
    text = unicodedata.normalize('NFKD', str(text or ''))
    text = ''.join(c for c in text if not unicodedata.combining(c)).lower()
    return re.sub(r'[^a-z0-9]+', ' ', text).strip()


def _field(job, name):
    """Lee un campo de oferta con la mayúscula de los scrapers ('Title') o en minúscula."""
    return job.get(name.capitalize()) or job.get(name) or ''


def fingerprint(job):
    """Huella de una oferta independiente del portal; las empresas anónimas usan la ubicación."""
    company = _normalize(_field(job, 'company'))
    if company in _ANONYMOUS:
        company = 'anon ' + _normalize(_field(job, 'location'))
    key = f"{_normalize(_field(job, 'title'))}|{company}"
    return hashlib.sha1(key.encode('utf-8'), usedforsecurity=False).hexdigest()


def _clean_list(values, allowed):
    """Valores permitidos, sin repetir y en el orden de `allowed`."""
    chosen = set(values or [])
    return [v for v in allowed if v in chosen]


def validate(data):
    """Normaliza los datos de una búsqueda; lanza ValueError con un mensaje para el usuario."""
    position = str(data.get('position') or '').strip()[:200]
    if not position:
        raise ValueError('Indicá el puesto a buscar.')
    portals = _clean_list(data.get('portals'), PORTALS)
    if not portals:
        raise ValueError('Elegí al menos un portal.')
    try:
        min_score = float(data.get('min_score') or 0)
    except (TypeError, ValueError):
        raise ValueError('El match mínimo debe ser un número entre 0 y 100.')
    if not 0 <= min_score <= 100:
        raise ValueError('El match mínimo debe ser un número entre 0 y 100.')
    location = str(data.get('location') or '').strip()[:200]
    name = str(data.get('name') or '').strip()[:120] or f"{position} {location}".strip()
    return {
        'name': name, 'position': position, 'location': location, 'portals': portals,
        'channels': _clean_list(data.get('channels'), CHANNELS), 'min_score': min_score,
    }


def _mine(model):
    """Condición: la fila es del usuario actual (o sin dueño si no hay usuario)."""
    uid = accounts.current_user_id()
    return model.user_id.is_(None) if uid is None else model.user_id == uid


def _own_row(session, search_id):
    """La búsqueda si es del usuario actual; None si no existe o es de otro."""
    row = session.get(SavedSearch, search_id)
    return row if row is not None and row.user_id == accounts.current_user_id() else None


def list_searches():
    """Búsquedas guardadas del usuario, la más nueva primero."""
    with _sessions()() as session:
        rows = session.scalars(select(SavedSearch).where(_mine(SavedSearch)).order_by(SavedSearch.id.desc())).all()
        return [r.to_dict() for r in rows]


def search_owner(search_id):
    """Usuario dueño de la búsqueda (para tareas de Celery que corren sin sesión)."""
    with _sessions()() as session:
        row = session.get(SavedSearch, search_id)
        return row.user_id if row else None


def active_search_ids():
    """(id, user_id) de todas las búsquedas activas de todos los usuarios."""
    with _sessions()() as session:
        return [tuple(r) for r in session.execute(
            select(SavedSearch.id, SavedSearch.user_id).where(SavedSearch.active.is_(True)))]


def get_search(search_id):
    """Una búsqueda del usuario como dict, o None."""
    with _sessions()() as session:
        row = _own_row(session, search_id)
        return row.to_dict() if row else None


def create_search(data):
    """Valida y guarda una búsqueda; devuelve su dict."""
    clean = validate(data)
    with _sessions()() as session:
        row = SavedSearch(**clean, active=True, user_id=accounts.current_user_id())
        session.add(row)
        session.commit()
        return row.to_dict()


def delete_search(search_id):
    """Borra una búsqueda; True si existía."""
    with _sessions()() as session:
        row = _own_row(session, search_id)
        if row is None:
            return False
        session.delete(row)
        session.commit()
        return True


def set_active(search_id, active):
    """Pausa o reanuda una búsqueda; True si existía."""
    with _sessions()() as session:
        row = _own_row(session, search_id)
        if row is None:
            return False
        row.active = bool(active)
        session.commit()
        return True


def find_new(jobs):
    """Ofertas que nunca se avisaron, sin repetidas en este lote. No las marca como vistas."""
    batch = {}
    for job in jobs:
        batch.setdefault(fingerprint(job), job)
    if not batch:
        return []
    with _sessions()() as session:
        seen = set(session.scalars(
            select(SeenJob.fingerprint).where(_mine(SeenJob), SeenJob.fingerprint.in_(list(batch)))
        ))
    return [job for fp, job in batch.items() if fp not in seen]


def mark_seen(jobs, search_id=None):
    """Registra las ofertas como avisadas para no repetirlas."""
    if not jobs:
        return
    with _sessions()() as session:
        for job in jobs:
            try:
                with session.begin_nested():
                    session.add(SeenJob(
                        fingerprint=fingerprint(job), search_id=search_id, user_id=accounts.current_user_id(),
                        title=str(_field(job, 'title'))[:300], company=str(_field(job, 'company'))[:200],
                        url=str(_field(job, 'url') or job.get('URL') or '')[:1000],
                        source=str(_field(job, 'source'))[:50],
                    ))
            except IntegrityError:
                pass  # otra búsqueda simultánea ya la registró
        session.commit()


def filter_new(jobs, search_id=None):
    """Ofertas nuevas, ya marcadas como vistas."""
    new = find_new(jobs)
    mark_seen(new, search_id)
    return new


def _make_scraper(portal):
    """Scraper sin login del portal dado."""
    if portal == 'computrabajo':
        from scrapers.computrabajo_scraper import ComputrabajoScraper
        return ComputrabajoScraper()
    if portal == 'zonajobs':
        from scrapers.zonajobs_scraper import ZonaJobsScraper
        return ZonaJobsScraper()
    if portal == 'getonboard':
        from scrapers.getonboard_scraper import GetOnBoardScraper
        return GetOnBoardScraper()
    from scrapers.bumeran_scraper import BumeranScraper
    return BumeranScraper()


def scrape(search, make_scraper=None):
    """Corre la búsqueda en cada portal; un portal caído no corta a los demás."""
    make_scraper = make_scraper or _make_scraper
    jobs = []
    for portal in search['portals']:
        scraper = None
        try:
            scraper = make_scraper(portal)
            found = scraper.search_jobs(
                search['position'], search.get('location', ''), max_jobs=MAX_JOBS_PER_PORTAL,
            ) or []
            scraper_stats.record(portal, found)
            jobs.extend(found)
        except Exception as e:
            logger.error(f"Alerta '{search['name']}': falló {portal}: {e}")
            scraper_stats.record(portal, None, e)
        finally:
            if scraper is not None:
                try:
                    scraper.close()
                except Exception:
                    pass
    return jobs


def score(jobs, profile):
    """Agrega `match_percent` (0-100) a cada oferta si hay un perfil de CV."""
    if not profile:
        return jobs
    from resume_parser import jobMatcher
    matcher = jobMatcher()
    for job in jobs:
        text = f"{_field(job, 'title')}\n{_field(job, 'description')}"
        try:
            job['match_percent'] = float(matcher.calculate_overall_match(profile, text)['overall_match'])
        except Exception as e:
            logger.warning(f"No se pudo calcular el match: {e}")
    return jobs


def _load_profile():
    """Primer perfil de CV guardado, o None."""
    try:
        import profile_store
        return profile_store.get_first_profile()
    except Exception:
        return None


def run_search(search_id, notify, make_scraper=None, profile=None):
    """Busca, filtra por match, descarta lo ya avisado y llama a notify(search, nuevas)."""
    search = get_search(search_id)
    if search is None:
        return {'search_id': search_id, 'error': 'no existe'}
    profile = profile if profile is not None else _load_profile()
    jobs = score(scrape(search, make_scraper), profile)
    if profile and search['min_score']:
        jobs = [j for j in jobs if j.get('match_percent', 0) >= search['min_score']]
    new = find_new(jobs)
    import job_ranking
    new = job_ranking.rank(new)
    pending = len(new)
    new = new[:MAX_JOBS_PER_ALERT]
    sent = notify(search, new) if new and search['channels'] else {}
    if any(sent.values()):
        mark_seen(new, search_id)
    result = f"{pending} nuevas de {len(jobs)}"
    if pending > len(new):
        result += f"; {pending - len(new)} quedan para el próximo aviso"
    if new and not any(sent.values()):
        result += " (sin avisar: se reintenta en la próxima corrida)"
    with _sessions()() as session:
        row = session.get(SavedSearch, search_id)
        if row is not None:
            row.last_run_at = datetime.now()
            row.last_result = result
            session.commit()
    logger.info(f"Alerta '{search['name']}': {result}; avisos: {sent}")
    return {'search_id': search_id, 'found': len(jobs), 'new': pending, 'sent': sent}


def run_all(notify, make_scraper=None):
    """Corre las búsquedas activas de todos los usuarios, cada una con el perfil de su dueño."""
    results, profiles = [], {}
    try:
        blocked = accounts.blocked_ids()
    except Exception as e:
        logger.error(f'No se pudieron leer las cuentas bloqueadas: {e}')
        blocked = set()
    for search_id, user_id in active_search_ids():
        if user_id in blocked:
            continue
        with accounts.as_user(user_id):
            if user_id not in profiles:
                profiles[user_id] = _load_profile()
            results.append(run_search(search_id, notify, make_scraper, profiles[user_id]))
    return results
