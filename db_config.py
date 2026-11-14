"""Acceso a las tablas del tracker (`applications`, `connection_requests`, `networking_exclusions`,
`processed_files`) sobre el engine SQLAlchemy de models.py, con el mismo pool que perfiles y alertas.

Cada consulta se limita a las filas del usuario actual (`accounts.current_user_id()`, parámetro :uid;
`<=>` también empareja NULL, que es el dueño de las filas cuando no hay usuario)."""
import logging
from datetime import datetime, timezone

from dotenv import load_dotenv
from sqlalchemy import bindparam, text
from sqlalchemy.exc import SQLAlchemyError

import accounts

load_dotenv()

logger = logging.getLogger(__name__)

_TRACKER_ORDER = """
    CASE status
        WHEN 'bookmarked' THEN 1 WHEN 'applying' THEN 2 WHEN 'applied' THEN 3
        WHEN 'interviewing' THEN 4 WHEN 'negotiating' THEN 5 WHEN 'accepted' THEN 6
        WHEN 'rejected' THEN 7
    END, applied_date DESC, id DESC"""

_INSERT_APPLICATION = text("""
    INSERT INTO applications
    (title, company, location, job_link, description, salary,
     experience_category, job_type, suggested_address, applied_date, status, user_id)
    VALUES (:title, :company, :location, :job_link, :description, :salary,
            :experience_category, :job_type, :suggested_address, :applied_date, :status, :uid)
""")


def _application_values(job_data, **overrides):
    values = {
        'title': job_data.get('title', 'Not specified'),
        'company': job_data.get('company', 'Not specified'),
        'location': job_data.get('location', 'Not specified'),
        'job_link': job_data.get('job_link', 'Not specified'),
        'description': job_data.get('description', ''),
        'salary': job_data.get('salary', 'Not specified'),
        'experience_category': job_data.get('experience_category', 'Unknown'),
        'job_type': job_data.get('job_type', 'Not specified'),
        'suggested_address': job_data.get('suggested_address', 'Remote/Flexible'),
    }
    values.update(overrides)
    return values


def _applied_date(value):
    """Fecha de postulación como datetime UTC sin zona (MySQL DATETIME); acepta ISO 8601 con `Z`, como manda
    `new Date().toISOString()` en la página de resultados. Sin fecha o ilegible: ahora."""
    if isinstance(value, datetime):
        return value
    try:
        parsed = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
    except ValueError:
        return datetime.now()
    return parsed.astimezone(timezone.utc).replace(tzinfo=None) if parsed.tzinfo else parsed


class DatabaseManager:
    """Consultas del tracker; cada método abre y cierra su propia transacción."""

    def __init__(self, engine=None):
        self._engine = engine

    @property
    def engine(self):
        if self._engine is None:
            from models import engine
            self._engine = engine
        return self._engine

    @staticmethod
    def _params(params):
        return {'uid': accounts.current_user_id(), **(params or {})}

    def _rows(self, query, params=None):
        with self.engine.connect() as conn:
            return [dict(row) for row in conn.execute(text(query) if isinstance(query, str) else query,
                                                       self._params(params)).mappings()]

    def _write(self, query, params=None, label='applications'):
        """Ejecuta una escritura; devuelve el resultado o None si MySQL falló."""
        try:
            with self.engine.begin() as conn:
                return conn.execute(text(query) if isinstance(query, str) else query, self._params(params))
        except SQLAlchemyError as err:
            logger.error(f"Error writing {label}: {err}")
            return None

    def _execute(self, query, params=None):
        """Ejecuta un UPDATE y devuelve True si salió bien."""
        return self._write(query, params) is not None

    def _execute_one(self, query, params=None):
        """UPDATE/DELETE de una fila por id: True solo si existía y es del usuario actual."""
        result = self._write(query, params)
        return result is not None and result.rowcount > 0

    STATUS_HISTORY_INSERT = """
        INSERT INTO application_status_history (application_id, user_id, old_status, new_status, changed_at)
        VALUES (:id, :uid, :old, :new, NOW())
    """

    def _log_status(self, job_id, old_status, new_status):
        """Anota un cambio de estado en el historial (si falla, el cambio igual queda guardado)."""
        self._write(self.STATUS_HISTORY_INSERT, {'id': job_id, 'old': old_status, 'new': new_status},
                    label='status history')

    def get_status_history(self, job_id=None):
        """Cambios de estado de la cuenta (o de una postulación), del más viejo al más nuevo."""
        query = ("SELECT application_id, old_status, new_status, changed_at FROM application_status_history "
                 "WHERE user_id <=> :uid")
        params = {}
        if job_id is not None:
            query += " AND application_id = :id"
            params['id'] = job_id
        try:
            return self._rows(query + " ORDER BY changed_at, id", params)
        except SQLAlchemyError as err:
            logger.error(f"Error reading status history: {err}")
            return []

    def save_application(self, job_data):
        """Guarda una postulación enviada y devuelve su id."""
        result = self._write(_INSERT_APPLICATION, _application_values(
            job_data, applied_date=_applied_date(job_data.get('applied_date')), status='applied'))
        if result is None:
            return None
        self._log_status(result.lastrowid, None, 'applied')
        return result.lastrowid

    def get_applications(self, filters=None):
        """Postulaciones filtradas por estado, empresa y rango de fechas."""
        query, params = "SELECT * FROM applications WHERE user_id <=> :uid", {}
        filters = filters or {}
        if filters.get('status'):
            query += " AND status = :status"
            params['status'] = filters['status']
        if filters.get('company'):
            query += " AND company LIKE :company"
            params['company'] = f"%{filters['company']}%"
        if filters.get('date_from'):
            query += " AND applied_date >= :date_from"
            params['date_from'] = filters['date_from']
        if filters.get('date_to'):
            query += " AND applied_date <= :date_to"
            params['date_to'] = filters['date_to']
        try:
            return self._rows(query + " ORDER BY applied_date DESC, id DESC", params)
        except SQLAlchemyError as err:
            logger.error(f"Error retrieving applications: {err}")
            return []

    def create_networking_exclusions_table(self):
        """Crea la tabla de empresas excluidas del networking."""
        return self._write("""
            CREATE TABLE IF NOT EXISTS networking_exclusions (
                id INT AUTO_INCREMENT PRIMARY KEY,
                user_id INT NULL,
                company_name VARCHAR(255) NOT NULL,
                excluded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                INDEX ix_networking_exclusions_user_id (user_id),
                UNIQUE KEY uq_networking_exclusions_user_company_name (user_id, company_name)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """, label='exclusions table') is not None

    def exclude_company(self, company_name):
        """Excluye una empresa de las sugerencias de conexión."""
        return self._write("INSERT IGNORE INTO networking_exclusions (company_name, user_id) VALUES (:name, :uid)",
                           {'name': company_name}, label='exclusion') is not None

    def get_companies_for_connections(self):
        """Empresas donde te postulaste, sin las excluidas."""
        self.create_networking_exclusions_table()
        try:
            return self._rows("""
                SELECT DISTINCT a.company, COUNT(*) as application_count
                FROM applications a
                LEFT JOIN networking_exclusions ne
                    ON a.company = ne.company_name COLLATE utf8mb4_unicode_ci AND ne.user_id <=> a.user_id
                WHERE a.user_id <=> :uid AND a.status = 'applied' AND ne.company_name IS NULL
                GROUP BY a.company
                ORDER BY MAX(a.applied_date) DESC, a.company
            """)
        except SQLAlchemyError as err:
            logger.error(f"Error getting companies: {err}")
            return []

    def save_processed_file(self, filename, total_jobs, jobs_applied):
        """Registra (o actualiza) un CSV procesado; sin cuenta el índice único no ve los NULL, así que actualiza primero."""
        params = self._params({'filename': filename, 'total': total_jobs, 'applied': jobs_applied,
                               'date': datetime.now()})
        try:
            with self.engine.begin() as conn:
                updated = conn.execute(text("""
                    UPDATE processed_files SET total_jobs = :total, jobs_applied = :applied, processed_date = :date
                    WHERE filename = :filename AND user_id <=> :uid
                """), params)
                if updated.rowcount == 0:
                    conn.execute(text("""
                        INSERT INTO processed_files (filename, total_jobs, jobs_applied, processed_date, user_id)
                        VALUES (:filename, :total, :applied, :date, :uid)
                    """), params)
            return True
        except SQLAlchemyError as err:
            logger.error(f"Error writing processed file: {err}")
            return False

    # ==== JOB TRACKER ====

    def add_job_to_tracker(self, job_data):
        """Agrega un empleo al tracker; si ya existe (título + empresa) devuelve su id con exists=True."""
        values = _application_values(job_data, job_link=job_data.get('job_link', ''),
                                     applied_date=job_data.get('date_applied', datetime.now()),
                                     status=job_data.get('status', 'applying'))
        try:
            with self.engine.begin() as conn:
                existing = conn.execute(
                    text("SELECT id FROM applications "
                         "WHERE title = :title AND company = :company AND user_id <=> :uid"),
                    self._params({'title': values['title'], 'company': values['company']})).first()
                if existing:
                    logger.warning(f"Job already exists in tracker with ID: {existing.id}")
                    return {'exists': True, 'job_id': existing.id, 'message': 'Job already in tracker'}
                new_id = conn.execute(_INSERT_APPLICATION, self._params(values)).lastrowid
        except SQLAlchemyError as err:
            logger.error(f"MySQL Error adding job to tracker: {err}", exc_info=True)
            return None
        self._log_status(new_id, None, values['status'])
        return new_id

    def get_all_tracked_jobs(self, raise_errors=False):
        """Todo el tracker, ordenado por columna del kanban y fecha.

        Si la base falla devuelve [], salvo con raise_errors=True: así quien sincroniza una copia (el caché offline)
        no la confunde con un tracker vacío.
        """
        try:
            return self._rows(f"SELECT * FROM applications WHERE user_id <=> :uid ORDER BY {_TRACKER_ORDER}")
        except SQLAlchemyError as err:
            logger.error(f"Error getting tracked jobs: {err}")
            if raise_errors:
                raise
            return []

    def get_tracked_job_by_id(self, job_id):
        """Una postulación por id, o None."""
        try:
            rows = self._rows("SELECT * FROM applications WHERE id = :id AND user_id <=> :uid", {'id': job_id})
        except SQLAlchemyError as err:
            logger.error(f"Error getting tracked job: {err}")
            return None
        return rows[0] if rows else None

    def update_job_status(self, job_id, new_status):
        """Cambia el estado; al pasar a postulado (o de guardada directo a entrevista/oferta) fecha hoy."""
        if new_status == 'applied':
            query = ("UPDATE applications SET status = :status, applied_date = CURDATE() "
                     "WHERE id = :id AND user_id <=> :uid")
        else:
            query = """
                UPDATE applications
                SET applied_date = IF(status IN ('bookmarked', 'applying')
                                      AND :status IN ('interviewing', 'negotiating', 'accepted'),
                                      CURDATE(), applied_date),
                    status = :status
                WHERE id = :id AND user_id <=> :uid
            """
        params = self._params({'status': new_status, 'id': job_id})
        try:
            with self.engine.begin() as conn:
                # FOR UPDATE: dos cambios simultáneos se ordenan y el historial queda en la misma transacción
                old_status = conn.execute(text("SELECT status FROM applications WHERE id = :id AND user_id <=> :uid "
                                               "FOR UPDATE"), params).scalar()
                if old_status is None:
                    return False
                conn.execute(text(query), params)
                if old_status != new_status:
                    conn.execute(text(self.STATUS_HISTORY_INSERT), {**params, 'old': old_status, 'new': new_status})
        except SQLAlchemyError as err:
            logger.error(f"Error writing applications: {err}")
            return False
        return True

    def delete_tracked_job(self, job_id):
        """Borra una postulación del tracker y su historial."""
        deleted = self._execute_one("DELETE FROM applications WHERE id = :id AND user_id <=> :uid", {'id': job_id})
        if deleted:
            self._write("DELETE FROM application_status_history WHERE application_id = :id AND user_id <=> :uid",
                        {'id': job_id}, label='status history')
        return deleted

    def update_tracker_dates(self, job_id, follow_up=None, deadline=None, notes=None):
        """Fecha de seguimiento, vencimiento y notas de una postulación (None borra la fecha)."""
        return self._execute_one(
            "UPDATE applications SET follow_up = :follow_up, deadline = :deadline, notes = :notes "
            "WHERE id = :id AND user_id <=> :uid",
            {'follow_up': follow_up, 'deadline': deadline, 'notes': notes, 'id': job_id},
        )

    def get_followup_candidates(self):
        """Postulaciones enviadas o en entrevista, que son las que admiten seguimiento."""
        return self._rows(
            "SELECT id, title, company, job_link, status, applied_date, follow_up, deadline, last_reminder_at "
            "FROM applications WHERE user_id <=> :uid AND status IN ('applied', 'interviewing')"
        )

    def mark_reminded(self, job_ids):
        """Registra que ya se avisó hoy por estas postulaciones."""
        if not job_ids:
            return True
        query = text("UPDATE applications SET last_reminder_at = NOW() "
                     "WHERE id IN :ids AND user_id <=> :uid").bindparams(bindparam('ids', expanding=True))
        return self._execute(query, {'ids': list(job_ids)})


db_manager = DatabaseManager()
