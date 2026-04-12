"""
models.py — Modelos SQLAlchemy para EmpleoIA
ORM completo reemplazando queries SQL manuales en db_config.py
"""
import os
from datetime import datetime
from sqlalchemy import (
    create_engine, Column, Integer, String, Text, DateTime,
    Date, Float, Boolean, Enum, ForeignKey, Index, event
)
from sqlalchemy.orm import declarative_base, relationship, sessionmaker, Session
from sqlalchemy.pool import QueuePool
from dotenv import load_dotenv

load_dotenv()

Base = declarative_base()

# ── Database URL ──────────────────────────────────────────────────────────────
def get_database_url() -> str:
    host = os.getenv("DB_HOST", "127.0.0.1")
    user = os.getenv("DB_USER", "root")
    password = os.getenv("DB_PASSWORD", "")
    db = os.getenv("DB_NAME", "job_tracker")
    return f"mysql+mysqlconnector://{user}:{password}@{host}/{db}?charset=utf8mb4"


# ── Engine & Session Factory ──────────────────────────────────────────────────
engine = create_engine(
    get_database_url(),
    poolclass=QueuePool,
    pool_size=int(os.getenv("DB_POOL_SIZE", "5")),
    max_overflow=10,
    pool_pre_ping=True,       # Verifica conexiones antes de usarlas
    pool_recycle=3600,        # Recicla conexiones cada hora
    echo=False,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db() -> Session:
    """Dependency injector para Flask/FastAPI."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ─────────────────────────────────────────────────────────────────────────────
# MODELOS
# ─────────────────────────────────────────────────────────────────────────────

class Application(Base):
    """Tabla principal de postulaciones (anteriormente usada como job_tracker también)."""
    __tablename__ = "applications"

    id = Column(Integer, primary_key=True, autoincrement=True)
    title = Column(String(255), nullable=False)
    company = Column(String(255), nullable=False)
    location = Column(String(255))
    salary = Column(String(100))
    job_link = Column(Text)
    description = Column(Text)
    experience_category = Column(String(100))
    job_type = Column(String(100))
    suggested_address = Column(String(255))

    # Tracking
    status = Column(
        Enum("bookmarked", "applying", "applied", "interviewing",
             "negotiating", "accepted", "rejected", name="app_status"),
        default="bookmarked", nullable=False
    )
    excitement = Column(Integer, default=0)
    applied_date = Column(DateTime, default=datetime.now)
    date_applied = Column(Date, nullable=True)
    deadline = Column(Date, nullable=True)
    follow_up = Column(Date, nullable=True)
    notes = Column(Text)

    # AI scores
    overall_match = Column(Float, default=0.0)
    skill_match = Column(Float, default=0.0)
    experience_match = Column(Float, default=0.0)
    text_similarity = Column(Float, default=0.0)
    ai_match_score = Column(Float, default=0.0)
    ai_nivel = Column(String(50))
    ai_modalidad = Column(String(50))
    ai_resumen = Column(Text)

    # Market data
    salary_min_usd = Column(Float, nullable=True)
    salary_max_usd = Column(Float, nullable=True)

    # Timestamps
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    # Source platform
    source_platform = Column(String(50), default="manual")

    __table_args__ = (
        Index("idx_status", "status"),
        Index("idx_company", "company"),
        Index("idx_applied_date", "applied_date"),
        Index("idx_overall_match", "overall_match"),
    )

    def to_dict(self) -> dict:
        return {c.name: getattr(self, c.name) for c in self.__table__.columns}

    def __repr__(self):
        return f"<Application(id={self.id}, title='{self.title}', company='{self.company}', status='{self.status}')>"


class ConnectionRequest(Base):
    """Solicitudes de conexión enviadas en LinkedIn."""
    __tablename__ = "connection_requests"

    id = Column(Integer, primary_key=True, autoincrement=True)
    company = Column(String(255), nullable=False)
    contact_name = Column(String(255))
    contact_profile_url = Column(Text)
    sent_date = Column(DateTime, default=datetime.now)
    status = Column(
        Enum("sent", "accepted", "pending", "withdrawn", name="conn_status"),
        default="sent"
    )
    application_ids = Column(String(500))  # CSV of application IDs
    message_sent = Column(Text)

    def to_dict(self) -> dict:
        return {c.name: getattr(self, c.name) for c in self.__table__.columns}


class NetworkingExclusion(Base):
    """Empresas excluidas del networking automatizado."""
    __tablename__ = "networking_exclusions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    company_name = Column(String(255), nullable=False, unique=True)
    excluded_at = Column(DateTime, default=datetime.now)


class ProcessedFile(Base):
    """Registro de archivos CSV procesados."""
    __tablename__ = "processed_files"

    id = Column(Integer, primary_key=True, autoincrement=True)
    filename = Column(String(500), unique=True, nullable=False)
    total_jobs = Column(Integer, default=0)
    jobs_applied = Column(Integer, default=0)
    processed_date = Column(DateTime, default=datetime.now)


class MarketInsight(Base):
    """Cache de insights de mercado salarial generados por IA."""
    __tablename__ = "market_insights"

    id = Column(Integer, primary_key=True, autoincrement=True)
    role = Column(String(255), nullable=False)
    experience_level = Column(String(50))
    location = Column(String(100), default="Argentina")
    salary_avg_usd = Column(Float)
    salary_low_usd = Column(Float)
    salary_high_usd = Column(Float)
    demand_level = Column(String(20))
    trend = Column(String(50))
    top_skills = Column(Text)          # JSON array as string
    raw_data = Column(Text)            # Full JSON from AI
    generated_at = Column(DateTime, default=datetime.now)
    expires_at = Column(DateTime)      # Para invalidar caché

    __table_args__ = (
        Index("idx_role_level", "role", "experience_level"),
    )


class MockInterview(Base):
    """Sesiones de entrevistas simuladas con IA."""
    __tablename__ = "mock_interviews"

    id = Column(Integer, primary_key=True, autoincrement=True)
    job_title = Column(String(255), nullable=False)
    company = Column(String(255))
    application_id = Column(Integer, ForeignKey("applications.id", ondelete="SET NULL"), nullable=True)
    questions_json = Column(Text)      # JSON array of questions
    answers_json = Column(Text)        # JSON array of user answers + evaluations
    overall_score = Column(Float)
    completed = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.now)
    completed_at = Column(DateTime, nullable=True)

    application = relationship("Application", foreign_keys=[application_id])


class UserSettings(Base):
    """Configuración del usuario (notificaciones, preferencias)."""
    __tablename__ = "user_settings"

    id = Column(Integer, primary_key=True, autoincrement=True)
    key = Column(String(100), nullable=False, unique=True)
    value = Column(Text)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)


# ── Utility functions ─────────────────────────────────────────────────────────

def create_all_tables():
    """Crea todas las tablas si no existen."""
    Base.metadata.create_all(bind=engine)


def drop_all_tables():
    """⚠️ Elimina todas las tablas (solo para desarrollo)."""
    Base.metadata.drop_all(bind=engine)


# ── SQLAlchemy Manager (wrapper compatible con el db_config.py existente) ─────

class SQLAlchemyManager:
    """
    Wrapper de SQLAlchemy que provee la misma interfaz que DatabaseManager
    para mantener compatibilidad hacia atrás con app.py mientras se migra gradualmente.
    """

    def __init__(self):
        create_all_tables()

    def get_session(self) -> Session:
        return SessionLocal()

    def get_applications(self, filters: dict = None) -> list:
        with SessionLocal() as session:
            query = session.query(Application)
            if filters:
                if filters.get("status"):
                    query = query.filter(Application.status == filters["status"])
                if filters.get("company"):
                    query = query.filter(Application.company.ilike(f"%{filters['company']}%"))
                if filters.get("date_from"):
                    query = query.filter(Application.applied_date >= filters["date_from"])
                if filters.get("date_to"):
                    query = query.filter(Application.applied_date <= filters["date_to"])
            return [row.to_dict() for row in query.order_by(Application.applied_date.desc()).all()]

    def add_job_to_tracker(self, job_data: dict):
        with SessionLocal() as session:
            existing = session.query(Application).filter_by(
                title=job_data.get("title"),
                company=job_data.get("company")
            ).first()
            if existing:
                return {"exists": True, "job_id": existing.id, "message": "Job already in tracker"}

            app = Application(**{
                k: v for k, v in job_data.items()
                if k in Application.__table__.columns.keys()
            })
            session.add(app)
            session.commit()
            session.refresh(app)
            return app.id

    def update_job_status(self, job_id: int, new_status: str) -> bool:
        with SessionLocal() as session:
            app = session.query(Application).get(job_id)
            if not app:
                return False
            app.status = new_status
            if new_status == "applied":
                from datetime import date
                app.date_applied = date.today()
            session.commit()
            return True

    def get_all_tracked_jobs(self) -> list:
        with SessionLocal() as session:
            jobs = session.query(Application).order_by(Application.applied_date.desc()).all()
            return [j.to_dict() for j in jobs]

    def get_tracked_job_by_id(self, job_id: int) -> dict:
        with SessionLocal() as session:
            job = session.query(Application).get(job_id)
            return job.to_dict() if job else None

    def delete_tracked_job(self, job_id: int) -> bool:
        with SessionLocal() as session:
            job = session.query(Application).get(job_id)
            if not job:
                return False
            session.delete(job)
            session.commit()
            return True

    def save_application(self, job_data: dict):
        return self.add_job_to_tracker(job_data)

    def get_companies_for_connections(self) -> list:
        with SessionLocal() as session:
            exclusions = {e.company_name for e in session.query(NetworkingExclusion).all()}
            from sqlalchemy import func
            rows = (
                session.query(Application.company, func.count(Application.id).label("application_count"))
                .filter(Application.status == "applied")
                .filter(Application.company.notin_(exclusions))
                .group_by(Application.company)
                .order_by(func.max(Application.applied_date).desc())
                .all()
            )
            return [{"company": r.company, "application_count": r.application_count} for r in rows]

    def save_market_insight(self, role: str, level: str, location: str, data: dict) -> int:
        import json
        from datetime import timedelta
        with SessionLocal() as session:
            insight = MarketInsight(
                role=role,
                experience_level=level,
                location=location,
                salary_avg_usd=data.get("salario_promedio_usd"),
                salary_low_usd=data.get("rango_bajo_usd"),
                salary_high_usd=data.get("rango_alto_usd"),
                demand_level=data.get("demanda"),
                trend=data.get("tendencia"),
                top_skills=json.dumps(data.get("skills_mas_valoradas", []), ensure_ascii=False),
                raw_data=json.dumps(data, ensure_ascii=False),
                expires_at=datetime.now() + timedelta(days=7),
            )
            session.add(insight)
            session.commit()
            return insight.id

    def get_cached_market_insight(self, role: str, level: str, location: str) -> dict:
        with SessionLocal() as session:
            insight = (
                session.query(MarketInsight)
                .filter(
                    MarketInsight.role.ilike(f"%{role}%"),
                    MarketInsight.experience_level == level,
                    MarketInsight.location == location,
                    MarketInsight.expires_at > datetime.now()
                )
                .order_by(MarketInsight.generated_at.desc())
                .first()
            )
            if not insight:
                return None
            import json
            return json.loads(insight.raw_data)


# Instancia global compatible con el código existente
try:
    orm_manager = SQLAlchemyManager()
except Exception as e:
    import logging
    logging.getLogger(__name__).error(f"SQLAlchemy init failed: {e}")
    orm_manager = None
