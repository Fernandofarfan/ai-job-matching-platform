"""Lógica de la app separada de la web: perfiles, búsquedas de Indeed y LinkedIn, conexiones y pruebas de scrapers.

app.py arma un AppServices y las páginas lo leen con fastapi_web.services_for(request).
"""
from collections.abc import MutableMapping
from dataclasses import dataclass
from types import ModuleType
from typing import Any


@dataclass
class AppServices:
    """Dependencias de las páginas: base de datos, progreso de búsquedas, parser de CVs y módulos de servicios."""

    db: Any
    job_status: MutableMapping[str, Any]
    resume_parser: Any
    profiles: ModuleType
    probe_tasks: ModuleType
    portal_search: ModuleType
    connections: ModuleType
