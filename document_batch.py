"""Cartas y CVs adaptados en lote, en el proceso web o en un worker de Celery (AI_BACKEND=celery).

En Celery el pedido no depende de que la instancia web siga viva: el worker publica el
progreso como estado de la tarea y la página lo consulta en /api/documents/tasks/<id>.
"""
import accounts
import logging
import os
import time

import pandas as pd

logger = logging.getLogger(__name__)

TASK_NAME = 'tasks.ai_tasks.generate_documents_batch'
KINDS = ('cover_letters', 'resumes')
RESULTS_DIR = 'results'
DESCRIPTION_COLUMNS = ('Job_Description', 'Description', 'job_description', 'description')
MAX_JOBS = 50
_TASK_TTL = 24 * 3600


class BatchError(ValueError):
    """Pedido inválido: se informa al usuario con el código HTTP indicado."""

    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


def generated_dir(kind):
    """Carpeta de los documentos generados; GENERATED_DIR la comparte entre web y worker."""
    from document_generators import _generated_dir
    return _generated_dir(kind)


def use_celery():
    return os.getenv('AI_BACKEND', 'sync').strip().lower() == 'celery'


def validate(kind, filename, num_jobs):
    """Normaliza el pedido; lanza BatchError si no se puede procesar."""
    if kind not in KINDS:
        raise BatchError('Tipo de documento desconocido')
    if not filename:
        raise BatchError('Elegí un archivo de empleos')
    if os.path.basename(filename) != filename or not filename.endswith('.csv'):
        raise BatchError('Archivo inválido')
    if not os.path.isfile(os.path.join(accounts.results_dir(), filename)):
        raise BatchError('No se encontró el archivo', 404)
    try:
        num_jobs = int(num_jobs)
    except (TypeError, ValueError):
        raise BatchError('Cantidad de empleos inválida') from None
    return filename, max(1, min(num_jobs, MAX_JOBS))


def _account_alive():
    """False si la cuenta dueña del lote se borró mientras se generaba (no hay que recrear sus archivos)."""
    uid = accounts.current_user_id()
    return uid is None or accounts.get_user(uid) is not None


def run(kind, filename, num_jobs, resume_text, progress=None, pause=2.0):
    """Genera un documento por oferta del CSV. `progress(done, total)` se llama tras cada una."""
    from document_generators import CoverLetterGenerator, ResumeOptimizer

    filename, num_jobs = validate(kind, filename, num_jobs)
    if not resume_text:
        raise BatchError('Primero subí tu CV')
    df = pd.read_csv(os.path.join(accounts.results_dir(), filename), encoding='latin-1')
    description_col = next((c for c in DESCRIPTION_COLUMNS if c in df.columns), None)
    if not description_col:
        raise BatchError('El archivo no tiene una columna de descripción')

    if kind == 'cover_letters':
        generator = CoverLetterGenerator()
        create, save = generator.generate_cover_letter, generator.save_cover_letter
    else:
        optimizer = ResumeOptimizer()
        create, save = optimizer.optimize_resume, optimizer.save_resume

    rows = df.head(num_jobs)
    results = []
    for done, (index, row) in enumerate(rows.iterrows(), 1):
        job_title = str(row.get('Title', 'Puesto sin título'))
        company = str(row.get('Company', 'Empresa sin nombre'))
        job_description = str(row.get(description_col, ''))
        if job_description and job_description != 'nan':
            try:
                text = create(resume_text, job_description, job_title, company)
                if not _account_alive():
                    raise BatchError('La cuenta fue borrada', 410)
                saved = save(text, job_title, company, output_dir=generated_dir(kind))
                results.append({'job_title': job_title, 'company': company, 'filename': saved, 'status': 'success'})
                if pause and done < len(rows):
                    time.sleep(pause)
            except BatchError:
                raise
            except Exception as e:
                logger.error(f'Error generando {kind} para la oferta {index}: {e}')
                results.append({'job_title': job_title, 'company': company, 'filename': None,
                                'status': 'failed', 'error': 'No se pudo generar el documento'})
        if progress:
            progress(done, len(rows))
    return {
        'success': True,
        'results': results,
        'total': len(results),
        'successful': sum(r['status'] == 'success' for r in results),
    }


def _task_key(task_id):
    return f'empleoia:document_task:{task_id}'


def enqueue(kind, filename, num_jobs):
    """Encola el lote en el worker; el CV lo lee el worker, no viaja por el broker."""
    from celery_app import celery

    filename, num_jobs = validate(kind, filename, num_jobs)
    result = celery.send_task(TASK_NAME, args=[kind, filename, num_jobs],
                             kwargs={'user_id': accounts.current_user_id()})
    celery.backend.client.set(_task_key(result.id), kind, ex=_TASK_TTL)
    return result.id


def status(task_id):
    """Estado de una tarea encolada por `enqueue`; None si el id no es de un lote de documentos."""
    from celery_app import celery

    if not celery.backend.client.get(_task_key(task_id)):
        return None
    result = celery.AsyncResult(task_id)
    state, info = result.state, result.info
    if state == 'SUCCESS' and isinstance(info, dict):
        if not info.get('success'):
            return {'success': False, 'state': 'failed', 'error': info.get('error', 'Error interno del servidor')}
        return {**info, 'state': 'completed', 'progress': 100}
    if state == 'FAILURE':
        return {'success': False, 'state': 'failed', 'error': 'Error interno del servidor'}
    if state == 'PROGRESS' and isinstance(info, dict):
        return {'success': True, 'state': 'running', **info}
    return {'success': True, 'state': 'running' if state == 'STARTED' else 'queued', 'progress': 0}
