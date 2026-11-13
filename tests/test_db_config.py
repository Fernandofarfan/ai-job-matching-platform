"""Tests de la normalización de datos antes de escribir en MySQL."""
from datetime import datetime

from db_config import _applied_date


def test_applied_date_accepts_javascript_iso():
    """`toISOString()` (con `Z`) queda en UTC sin zona: MySQL rechazaba el texto tal cual."""
    assert _applied_date('2026-11-12T17:04:46.496Z') == datetime(2026, 11, 12, 17, 4, 46, 496000)
    assert _applied_date('2026-11-12T14:00:00-03:00') == datetime(2026, 11, 12, 17, 0)


def test_applied_date_keeps_naive_values_and_defaults_to_now():
    """Un datetime o una fecha sin zona pasan igual; sin fecha o ilegible, ahora."""
    when = datetime(2025, 1, 2, 3, 4)
    assert _applied_date(when) is when
    assert _applied_date('2025-01-02 03:04:00') == when
    before = datetime.now()
    assert before <= _applied_date(None) <= datetime.now()
    assert before <= _applied_date('ayer') <= datetime.now()


def test_tracked_jobs_hide_db_errors_unless_asked(monkeypatch):
    """El tracker de las páginas se ve vacío si la base falla; el caché offline necesita el error para no borrarse."""
    import pytest
    from sqlalchemy.exc import OperationalError

    from db_config import DatabaseManager
    manager = object.__new__(DatabaseManager)
    monkeypatch.setattr(manager, '_rows', lambda *a, **k: (_ for _ in ()).throw(OperationalError('SELECT', {}, Exception('caída'))),
                        raising=False)
    assert manager.get_all_tracked_jobs() == []
    with pytest.raises(OperationalError):
        manager.get_all_tracked_jobs(raise_errors=True)
