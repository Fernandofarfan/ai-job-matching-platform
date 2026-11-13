from sqlalchemy import ColumnElement
from typing import Any
from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import HTMLResponse

from fastapi_web import render

try:
    from models import orm_manager, Application
    from sqlalchemy import func
except ImportError:
    orm_manager = None

router = APIRouter(tags=["analytics"])


@router.get("/analytics", response_class=HTMLResponse)
def dashboard_view(request: Request) -> Response:
    """Vista principal del Dashboard de Funnel de Conversión."""
    return render(request, "dashboard.html")


def _owned() -> ColumnElement[bool]:
    """Filtro de las postulaciones de la cuenta actual."""
    import accounts
    uid = accounts.current_user_id()
    return Application.user_id.is_(None) if uid is None else Application.user_id == uid


@router.get("/api/analytics/funnel", response_model=None)
async def get_funnel_stats() -> dict[str, Any]:
    """Retorna las estadísticas del embudo de reclutamiento."""
    if not orm_manager:
        raise HTTPException(status_code=500, detail="Database ORM Manager no disponible")
    
    with orm_manager.get_session() as session:
        # Contamos cuántas aplicaciones hay por status
        status_counts = session.query(
            Application.status, 
            func.count(Application.id)
        ).filter(_owned()).group_by(Application.status).all()
        
        # Convertir a un diccionario {status: count}
        stats = {row[0]: row[1] for row in status_counts}
        
        # Agrupamos en el funnel clásico
        funnel = {
            "found": sum(stats.values()), # Total de jobs guardados
            "applied": stats.get("applied", 0) + stats.get("interviewing", 0) + stats.get("negotiating", 0) + stats.get("accepted", 0) + stats.get("rejected", 0),
            "interviews": stats.get("interviewing", 0) + stats.get("negotiating", 0) + stats.get("accepted", 0) + stats.get("rejected", 0), # Sumando los estados post-aplicacion
            "offers": stats.get("accepted", 0) + stats.get("negotiating", 0)
        }
        
        return {
            "success": True,
            "raw_stats": stats,
            "funnel": funnel
        }
