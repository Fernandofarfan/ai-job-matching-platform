"""Analytics y estadísticas del tracker."""
import accounts
import glob
import os
import pandas as pd
from datetime import datetime
from db_config import db_manager
from flask import render_template

from app import (  # noqa: F401
    app,
    logger,
)


@app.route('/analytics')
def analytics():
    """Dashboard de analytics: métricas de postulaciones y archivos scrapeados."""
    from collections import defaultdict

    # ── Datos desde MySQL (tabla applications) ──
    stats = {
        'total_jobs': 0,
        'bookmarked': 0,
        'applying': 0,
        'applied': 0,
        'interviewing': 0,
        'negotiating': 0,
        'accepted': 0,
        'rejected': 0,
        'top_companies': [],
    }

    timeline_labels = []
    timeline_data   = []
    status_labels   = []
    status_data     = []
    csv_stats       = []

    try:
        all_jobs = db_manager.get_all_tracked_jobs()
        status_counts = defaultdict(int)
        company_counts = defaultdict(int)
        date_counts    = defaultdict(int)

        for job in all_jobs:
            st = job.get('status', 'unknown')
            status_counts[st] += 1
            company = job.get('company', 'Desconocida')
            company_counts[company] += 1
            date_applied = job.get('applied_date') or job.get('date_saved')
            if date_applied:
                try:
                    day = str(date_applied)[:10]
                    date_counts[day] += 1
                except Exception:
                    pass

        stats['total_jobs']    = len(all_jobs)
        stats['bookmarked']    = status_counts.get('bookmarked', 0)
        stats['applying']      = status_counts.get('applying', 0)
        stats['applied']       = status_counts.get('applied', 0)
        stats['interviewing']  = status_counts.get('interviewing', 0)
        stats['negotiating']   = status_counts.get('negotiating', 0)
        stats['accepted']      = status_counts.get('accepted', 0)
        stats['rejected']      = status_counts.get('rejected', 0)

        # Top companies
        stats['top_companies'] = [
            {'name': k, 'count': v}
            for k, v in sorted(company_counts.items(), key=lambda x: -x[1])[:10]
        ]

        # Timeline (últimos 30 días)
        sorted_dates = sorted(date_counts.keys())[-30:]
        timeline_labels = sorted_dates
        timeline_data   = [date_counts[d] for d in sorted_dates]

        # Status doughnut
        status_order = ['applied','interviewing','negotiating','accepted','bookmarked','applying','rejected']
        status_labels_map = {
            'applied': 'Postulados',
            'interviewing': 'Entrevistas',
            'negotiating': 'Negociando',
            'accepted': 'Aceptados',
            'bookmarked': 'Guardados',
            'applying': 'Aplicando',
            'rejected': 'Rechazados',
        }
        for k in status_order:
            if status_counts.get(k, 0) > 0:
                status_labels.append(status_labels_map.get(k, k))
                status_data.append(status_counts[k])

    except Exception as e:
        logger.error(f"Error loading analytics data from DB: {e}")

    # ── CSV Stats ──
    try:
        csv_files = glob.glob(os.path.join(accounts.results_dir(), '*.csv'))
        for fpath in sorted(csv_files, key=os.path.getmtime, reverse=True)[:15]:
            fname = os.path.basename(fpath)
            try:
                pd.read_csv(fpath, encoding='latin-1', nrows=1)
                count  = sum(1 for _ in open(fpath, encoding='latin-1')) - 1
            except Exception:
                count = 0

            # Detectar plataforma desde nombre de archivo
            platform = 'otro'
            for p in ['indeed','linkedin','computrabajo','bumeran']:
                if p in fname.lower():
                    platform = p
                    break

            mtime = datetime.fromtimestamp(os.path.getmtime(fpath)).strftime('%d/%m/%Y %H:%M')
            csv_stats.append({'name': fname, 'count': count, 'platform': platform, 'date': mtime})
    except Exception as e:
        logger.error(f"Error loading CSV stats: {e}")

    return render_template(
        'analytics.html',
        stats=stats,
        timeline_labels=timeline_labels,
        timeline_data=timeline_data,
        status_labels=status_labels,
        status_data=status_data,
        csv_stats=csv_stats,
    )


# ─────────────────────────────────────────────────────────────
# ANALYTICS AVANZADO – endpoint JSON (para llamadas AJAX)
# ─────────────────────────────────────────────────────────────

PORTALS = {
    'computrabajo': 'Computrabajo', 'bumeran': 'Bumeran', 'zonajobs': 'ZonaJobs',
    'getonbrd': 'GetOnBoard', 'getonboard': 'GetOnBoard', 'linkedin': 'LinkedIn', 'indeed': 'Indeed',
}
APPLIED_OR_LATER = {'applied', 'interviewing', 'negotiating', 'accepted', 'rejected'}
RESPONDED = {'interviewing', 'negotiating', 'accepted'}


def portal_of(link):
    """Portal de una oferta según el dominio de su enlace ('Otros' si no es uno conocido)."""
    from urllib.parse import urlparse
    host = (urlparse(link or '').hostname or '').lower()
    return next((name for key, name in PORTALS.items() if key in host), 'Otros')


def _as_date(value):
    from datetime import date, datetime
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return datetime.strptime(str(value)[:10], '%Y-%m-%d').date() if value else None
    except ValueError:
        return None


POSTED = APPLIED_OR_LATER - {'rejected'}


def history_by_job(history):
    """{id de postulación: [cambios en orden]} a partir de get_status_history()."""
    grouped = {}
    for change in history or []:
        grouped.setdefault(change.get('application_id'), []).append(change)
    return grouped


def _applied_on(job, changes):
    """Fecha en que se postuló según el historial, o None si el historial no lo registra."""
    return next((_as_date(c.get('changed_at')) for c in changes if c.get('new_status') in POSTED), None)


def _was_applied(job, changes):
    """Con historial, una rechazada cuenta solo si pasó por postulada; sin historial se asume que sí."""
    status = job.get('status')
    if status != 'rejected':
        return status in APPLIED_OR_LATER
    known = [c for c in changes if c.get('old_status') is not None]
    return _applied_on(job, changes) is not None if known else True


def portal_stats(jobs, history=None):
    """Por portal: guardadas, postuladas, con respuesta y tasa de respuesta (respuestas / postuladas)."""
    stats = {}
    by_job = history_by_job(history)
    for job in jobs:
        row = stats.setdefault(portal_of(job.get('job_link')), {'saved': 0, 'applied': 0, 'responses': 0})
        row['saved'] += 1
        status = job.get('status')
        row['applied'] += _was_applied(job, by_job.get(job.get('id'), []))
        row['responses'] += status in RESPONDED
    return sorted(
        ({'portal': name, **row, 'response_rate': round(row['responses'] / row['applied'] * 100, 1) if row['applied'] else 0}
         for name, row in stats.items()),
        key=lambda r: (-r['saved'], r['portal']),
    )


def avg_days_to_apply(jobs, history=None):
    """Días promedio entre que se guarda una oferta y se postula (None si no hay datos)."""
    days = []
    by_job = history_by_job(history)
    for job in jobs:
        changes = by_job.get(job.get('id'), [])
        saved = _as_date(job.get('created_at'))
        from_history = _applied_on(job, [c for c in changes if c.get('old_status') is not None])
        created_applied = next((c for c in changes if c.get('old_status') is None and c.get('new_status') == 'applied'), None)
        if created_applied:
            # se cargó ya postulada: la fecha de postulación es la de alta, no la de un cambio posterior
            applied = _as_date(job.get('applied_date')) or _as_date(created_applied.get('changed_at'))
        elif from_history:
            applied = from_history
        elif job.get('status') in POSTED:
            # sin historial, una rechazada queda afuera: no se sabe si llegó a postularse
            applied = _as_date(job.get('applied_date'))
        else:
            applied = None
        if saved and applied and applied >= saved:
            days.append((applied - saved).days)
    return round(sum(days) / len(days), 1) if days else None


def advanced_stats(all_jobs, history=None):
    """Métricas avanzadas: tiempos promedio por etapa, tasa respuesta, heatmap."""
    from collections import defaultdict


    # ── Conteos por estado ──
    by_status = defaultdict(int)
    by_weekday = defaultdict(int)  # 0=Lun … 6=Dom
    total = len(all_jobs)

    applied = interviewing = accepted = rejected = 0

    for job in all_jobs:
        st = job.get('status', 'unknown')
        by_status[st] += 1

        # Detección de día de la semana de postulación
        raw_date = job.get('applied_date') or job.get('date_saved')
        if raw_date:
            try:
                if hasattr(raw_date, 'weekday'):
                    by_weekday[raw_date.weekday()] += 1
                else:
                    from datetime import datetime as _dt
                    parsed = _dt.strptime(str(raw_date)[:10], '%Y-%m-%d')
                    by_weekday[parsed.weekday()] += 1
            except Exception:
                pass

        if st == 'applied':     applied += 1
        if st == 'interviewing': interviewing += 1
        if st == 'accepted':    accepted += 1
        if st == 'rejected':    rejected += 1

    # ── Tasas (evitar divisiones por cero) ──
    response_rate   = round(interviewing / applied * 100, 1) if applied  > 0 else 0
    success_rate    = round(accepted / total * 100, 1)       if total    > 0 else 0
    rejection_rate  = round(rejected / total * 100, 1)       if total    > 0 else 0

    # ── Heatmap por día de semana ──
    weekday_labels = ['Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes', 'Sábado', 'Domingo']
    heatmap = [{'day': weekday_labels[i], 'count': by_weekday.get(i, 0)} for i in range(7)]

    # ── Insights automáticos ──
    insights = []
    if response_rate >= 20:
        insights.append({'icon': '🎯', 'type': 'success', 'text': f'Excelente tasa de respuesta ({response_rate}%). ¡Tus cartas de presentación están funcionando!'})
    elif response_rate > 0:
        insights.append({'icon': '💡', 'type': 'warning', 'text': f'Tasa de respuesta del {response_rate}%. Considera personalizar más tu CV para cada empresa.'})
    else:
        insights.append({'icon': '📝', 'type': 'info', 'text': 'Comienza a postularte para ver métricas de respuesta.'})

    if by_status.get('bookmarked', 0) > by_status.get('applied', 0):
        insights.append({'icon': '🚀', 'type': 'info', 'text': 'Tienes más empleos guardados que postulaciones. ¡Es momento de aplicar!'})

    best_day = max(by_weekday, key=lambda k: by_weekday[k], default=None)
    if best_day is not None and by_weekday[best_day] > 0:
        insights.append({'icon': '📅', 'type': 'info', 'text': f'Tu día más activo es el {weekday_labels[best_day]}.'})

    # ── Embudo detallado con conversiones ──
    funnel = []
    stages = [
        ('bookmarked',  'Guardados'),
        ('applying',    'Aplicando'),
        ('applied',     'Postulados'),
        ('interviewing','Entrevistas'),
        ('negotiating', 'Negociando'),
        ('accepted',    'Aceptados'),
    ]
    prev_count = total if total > 0 else 1
    for key, label in stages:
        count = by_status.get(key, 0)
        conversion = round(count / prev_count * 100, 1) if prev_count > 0 else 0
        funnel.append({'key': key, 'label': label, 'count': count, 'conversion': conversion})
        if count > 0:
            prev_count = count

    return {
        'total': total,
        'response_rate': response_rate,
        'success_rate': success_rate,
        'rejection_rate': rejection_rate,
        'by_status': dict(by_status),
        'heatmap': heatmap,
        'funnel': funnel,
        'insights': insights,
        'by_portal': portal_stats(all_jobs, history),
        'avg_days_to_apply': avg_days_to_apply(all_jobs, history),
    }



# ─────────────────────────────────────────────────────────────
# EXPORTACIÓN – Excel y PDF
# ─────────────────────────────────────────────────────────────
