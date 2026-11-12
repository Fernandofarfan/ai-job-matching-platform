"""
models.py — Modelos SQLAlchemy para EmpleoIA
ORM completo reemplazando queries SQL manuales en db_config.py
"""
import os
from collections.abc import Iterator
from datetime import date, datetime
from typing import Optional
from sqlalchemy import (
    create_engine, Integer, String, Text, DateTime, Date, Float, Boolean, Enum, ForeignKey, Index
)
from sqlalchemy.engine import URL
from sqlalchemy.orm import DeclarativeBase, relationship, sessionmaker, Session, Mapped, mapped_column
from sqlalchemy.pool import QueuePool
from dotenv import load_dotenv

load_dotenv()


class Base(DeclarativeBase):
    """Base declarativa de los modelos de este módulo."""


# ── Database URL ──────────────────────────────────────────────────────────────
def get_database_url() -> str:
    """URL de MySQL con usuario y contraseña escapados (admite '@', ':' o '/' en DB_PASSWORD)."""
    return URL.create(
        "mysql+mysqlconnector",
        username=os.getenv("DB_USER", "root"),
        password=os.getenv("DB_PASSWORD", ""),
        host=os.getenv("DB_HOST", "127.0.0.1"),
        database=os.getenv("DB_NAME", "job_tracker"),
        query={"charset": "utf8mb4"},
    ).render_as_string(hide_password=False)


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


def get_db() -> Iterator[Session]:
    """Dependency injector para FastAPI."""
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

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int | None] = mapped_column(Integer, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    company: Mapped[str] = mapped_column(String(255), nullable=False)
    location: Mapped[str | None] = mapped_column(String(255))
    salary: Mapped[str | None] = mapped_column(String(100))
    job_link: Mapped[str | None] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)
    experience_category: Mapped[str | None] = mapped_column(String(100))
    job_type: Mapped[str | None] = mapped_column(String(100))
    suggested_address: Mapped[str | None] = mapped_column(String(255))

    # Tracking
    status: Mapped[str] = mapped_column(
        Enum("bookmarked", "applying", "applied", "interviewing",
             "negotiating", "accepted", "rejected", name="app_status"),
        default="bookmarked", nullable=False
    )
    excitement: Mapped[int | None] = mapped_column(Integer, default=0)
    applied_date: Mapped[datetime | None] = mapped_column(DateTime, default=datetime.now)
    date_applied: Mapped[date | None] = mapped_column(Date, nullable=True)
    deadline: Mapped[date | None] = mapped_column(Date, nullable=True)
    follow_up: Mapped[date | None] = mapped_column(Date, nullable=True)
    last_reminder_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text)

    # AI scores
    overall_match: Mapped[float | None] = mapped_column(Float, default=0.0)
    skill_match: Mapped[float | None] = mapped_column(Float, default=0.0)
    experience_match: Mapped[float | None] = mapped_column(Float, default=0.0)
    text_similarity: Mapped[float | None] = mapped_column(Float, default=0.0)
    ai_match_score: Mapped[float | None] = mapped_column(Float, default=0.0)
    ai_nivel: Mapped[str | None] = mapped_column(String(50))
    ai_modalidad: Mapped[str | None] = mapped_column(String(50))
    ai_resumen: Mapped[str | None] = mapped_column(Text)

    # Market data
    salary_min_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
    salary_max_usd: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Timestamps
    created_at: Mapped[datetime | None] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)

    # Source platform
    source_platform: Mapped[str | None] = mapped_column(String(50), default="manual")

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

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int | None] = mapped_column(Integer, index=True)
    company: Mapped[str] = mapped_column(String(255), nullable=False)
    contact_name: Mapped[str | None] = mapped_column(String(255))
    contact_profile_url: Mapped[str | None] = mapped_column(Text)
    sent_date: Mapped[datetime | None] = mapped_column(DateTime, default=datetime.now)
    status: Mapped[str | None] = mapped_column(
        Enum("sent", "accepted", "declined", "pending", "withdrawn", name="conn_status"),
        default="sent"
    )
    application_ids: Mapped[str | None] = mapped_column(Text)  # CSV of application IDs
    message_sent: Mapped[str | None] = mapped_column(Text)

    def to_dict(self) -> dict:
        return {c.name: getattr(self, c.name) for c in self.__table__.columns}


class NetworkingExclusion(Base):
    """Empresas excluidas del networking automatizado."""
    __tablename__ = "networking_exclusions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int | None] = mapped_column(Integer, index=True)
    company_name: Mapped[str] = mapped_column(String(255), nullable=False)
    excluded_at: Mapped[datetime | None] = mapped_column(DateTime, default=datetime.now)

    __table_args__ = (
        Index("uq_networking_exclusions_user_company_name", "user_id", "company_name", unique=True),
    )


class ProcessedFile(Base):
    """Registro de archivos CSV procesados."""
    __tablename__ = "processed_files"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int | None] = mapped_column(Integer, index=True)
    filename: Mapped[str] = mapped_column(String(500), nullable=False)
    total_jobs: Mapped[int | None] = mapped_column(Integer, default=0)
    jobs_applied: Mapped[int | None] = mapped_column(Integer, default=0)
    processed_date: Mapped[datetime | None] = mapped_column(DateTime, default=datetime.now)

    __table_args__ = (
        Index("uq_processed_files_user_filename", "user_id", "filename", unique=True),
    )


class MarketInsight(Base):
    """Cache de insights de mercado salarial generados por IA."""
    __tablename__ = "market_insights"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    role: Mapped[str] = mapped_column(String(255), nullable=False)
    experience_level: Mapped[str | None] = mapped_column(String(50))
    location: Mapped[str | None] = mapped_column(String(100), default="Argentina")
    salary_avg_usd: Mapped[float | None] = mapped_column(Float)
    salary_low_usd: Mapped[float | None] = mapped_column(Float)
    salary_high_usd: Mapped[float | None] = mapped_column(Float)
    demand_level: Mapped[str | None] = mapped_column(String(20))
    trend: Mapped[str | None] = mapped_column(String(50))
    top_skills: Mapped[str | None] = mapped_column(Text)          # JSON array as string
    raw_data: Mapped[str | None] = mapped_column(Text)            # Full JSON from AI
    generated_at: Mapped[datetime | None] = mapped_column(DateTime, default=datetime.now)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime)      # Para invalidar caché

    __table_args__ = (
        Index("idx_role_level", "role", "experience_level"),
    )


class MockInterview(Base):
    """Sesiones de entrevistas simuladas con IA."""
    __tablename__ = "mock_interviews"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_title: Mapped[str] = mapped_column(String(255), nullable=False)
    company: Mapped[str | None] = mapped_column(String(255))
    application_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("applications.id", ondelete="SET NULL"), nullable=True)
    questions_json: Mapped[str | None] = mapped_column(Text)      # JSON array of questions
    answers_json: Mapped[str | None] = mapped_column(Text)        # JSON array of user answers + evaluations
    overall_score: Mapped[float | None] = mapped_column(Float)
    completed: Mapped[bool | None] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime | None] = mapped_column(DateTime, default=datetime.now)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    application: Mapped["Application | None"] = relationship("Application", foreign_keys=[application_id])


class UserSettings(Base):
    """Configuración del usuario (notificaciones, preferencias)."""
    __tablename__ = "user_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    key: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    value: Mapped[str | None] = mapped_column(Text)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)


# ── Utility functions ─────────────────────────────────────────────────────────

# ── SQLAlchemy Manager (wrapper compatible con el db_config.py existente) ─────

class SQLAlchemyManager:
    """Sesiones ORM para las consultas que no pasan por db_config (p. ej. el dashboard de analytics).
    Las tablas las crea Alembic (`alembic upgrade head`)."""

    def get_session(self) -> Session:
        return SessionLocal()


# Instancia global compatible con el código existente
orm_manager: Optional[SQLAlchemyManager]
try:
    orm_manager = SQLAlchemyManager()
except Exception as e:
    import logging
    logging.getLogger(__name__).error(f"SQLAlchemy init failed: {e}")
    orm_manager = None
