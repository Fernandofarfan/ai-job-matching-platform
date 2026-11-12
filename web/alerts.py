"""Alertas de empleo: alta, pausa, borrado y ejecución manual de búsquedas guardadas."""
import accounts
import logging

from flask import flash, redirect, render_template, request, url_for

import job_alerts
import job_dispatch
from app import app

logger = logging.getLogger(__name__)


def _channels_status():
    from tasks.notification_tasks import email_configured, telegram_configured
    return {'email': email_configured(), 'telegram': telegram_configured()}


@app.route('/alerts', methods=['GET', 'POST'])
def alerts():
    if request.method == 'POST':
        try:
            job_alerts.create_search({
                'name': request.form.get('name'),
                'position': request.form.get('position'),
                'location': request.form.get('location'),
                'portals': request.form.getlist('portals'),
                'channels': request.form.getlist('channels'),
                'min_score': request.form.get('min_score'),
            })
            flash('Alerta guardada. Se revisa sola cada pocas horas.', 'success')
        except ValueError as e:
            flash(str(e), 'danger')
        except Exception as e:
            logger.error(f"No se pudo guardar la alerta: {e}")
            flash('No se pudo guardar la alerta: la base de datos no responde.', 'danger')
        return redirect(url_for('alerts'))
    try:
        searches = job_alerts.list_searches()
        db_error = False
    except Exception as e:
        logger.error(f"No se pudieron leer las alertas: {e}")
        searches, db_error = [], True
    return render_template(
        'alerts.html', searches=searches, db_error=db_error, channels=_channels_status(),
        portals=job_alerts.PORTALS,
    )


@app.route('/alerts/<int:search_id>/delete', methods=['POST'])
def delete_alert(search_id):
    if job_alerts.delete_search(search_id):
        flash('Alerta borrada.', 'success')
    return redirect(url_for('alerts'))


@app.route('/alerts/<int:search_id>/toggle', methods=['POST'])
def toggle_alert(search_id):
    search = job_alerts.get_search(search_id)
    if search:
        job_alerts.set_active(search_id, not search['active'])
        flash('Alerta reanudada.' if not search['active'] else 'Alerta pausada.', 'success')
    return redirect(url_for('alerts'))


@app.route('/alerts/<int:search_id>/run', methods=['POST'])
def run_alert(search_id):
    if job_alerts.get_search(search_id) is None:
        return redirect(url_for('alerts'))
    if job_dispatch.use_celery():
        from celery_app import celery
        celery.send_task('tasks.notification_tasks.run_job_alert', args=[search_id])
    else:
        from tasks.notification_tasks import notify_alert
        accounts.thread(
            target=job_alerts.run_search, args=(search_id, notify_alert), daemon=True,
        ).start()
    flash('Buscando ofertas nuevas; recargá en unos minutos para ver el resultado.', 'info')
    return redirect(url_for('alerts'))
