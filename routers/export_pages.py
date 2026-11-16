"""Exportación del tracker (Excel y PDF) y de los resultados de una búsqueda (Excel), en FastAPI."""
import logging
import os
from datetime import datetime

from fastapi import APIRouter, Request, Response

import accounts
import tracker_export
from fastapi_web import flash, redirect, services_for, url_for
from routers.account_pages import _download

logger = logging.getLogger(__name__)
router = APIRouter(tags=["export"], include_in_schema=False)


def _stamp() -> str:
    """Fecha y hora para el nombre del archivo."""
    return datetime.now().strftime('%Y%m%d_%H%M')


@router.get("/export/tracker/excel", name="export_tracker_excel")
def export_tracker_excel(request: Request) -> Response:
    """Exporta el tracker de la cuenta a Excel (.xlsx)."""
    try:
        data = tracker_export.tracker_excel(services_for(request).db.get_all_tracked_jobs())
    except Exception as e:
        logger.error(f'Error exporting tracker to Excel: {e}')
        flash(request, 'No se pudo exportar; probá de nuevo', 'danger')
        return redirect(request, url_for(request, 'tracker'))
    return _download(request, data, tracker_export.XLSX, f'EmpleoIA_Tracker_{_stamp()}.xlsx')


@router.get("/export/tracker/pdf", name="export_tracker_pdf")
def export_tracker_pdf(request: Request) -> Response:
    """Exporta el tracker de la cuenta a PDF."""
    try:
        data = tracker_export.tracker_pdf(services_for(request).db.get_all_tracked_jobs())
    except Exception as e:
        logger.error(f'Error exporting tracker to PDF: {e}')
        flash(request, 'No se pudo exportar; probá de nuevo', 'danger')
        return redirect(request, url_for(request, 'tracker'))
    return _download(request, data, 'application/pdf', f'EmpleoIA_Tracker_{_stamp()}.pdf')


@router.get("/export/results/{filename}/excel", name="export_results_excel")
def export_results_excel(request: Request, filename: str) -> Response:
    """Exporta un CSV de resultados de la cuenta como Excel."""
    path = os.path.join(accounts.results_dir(), filename)
    if filename != os.path.basename(filename) or not filename.endswith('.csv') or not os.path.isfile(path):
        flash(request, 'Archivo no encontrado', 'danger')
        return redirect(request, url_for(request, 'results'))
    try:
        data = tracker_export.results_excel(path)
    except Exception as e:
        logger.error(f'Error exporting results to Excel: {e}')
        flash(request, 'No se pudo exportar; probá de nuevo', 'danger')
        return redirect(request, url_for(request, 'results'))
    return _download(request, data, tracker_export.XLSX, f'{filename[:-4]}_export.xlsx')
