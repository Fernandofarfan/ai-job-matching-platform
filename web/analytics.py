"""Analytics y estadísticas del tracker."""
import glob
import os
import pandas as pd
from datetime import datetime
from db_config import db_manager
from flask import jsonify, render_template

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
        csv_files = glob.glob(os.path.join('results', '*.csv'))
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


@app.route('/api/tracker/stats')
def tracker_stats():
    """Devuelve conteos por estado para el embudo del Job Tracker."""
    try:
        from collections import defaultdict
        all_jobs = db_manager.get_all_tracked_jobs()
        counts   = defaultdict(int)
        for job in all_jobs:
            counts[job.get('status', 'unknown')] += 1
        return jsonify({'success': True, 'stats': dict(counts)})
    except Exception as e:
        logger.error(f"Error in tracker stats: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


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


def portal_stats(jobs):
    """Por portal: guardadas, postuladas, con respuesta y tasa de respuesta (respuestas / postuladas)."""
    stats = {}
    for job in jobs:
        row = stats.setdefault(portal_of(job.get('job_link')), {'saved': 0, 'applied': 0, 'responses': 0})
        row['saved'] += 1
        status = job.get('status')
        row['applied'] += status in APPLIED_OR_LATER
        row['responses'] += status in RESPONDED
    return sorted(
        ({'portal': name, **row, 'response_rate': round(row['responses'] / row['applied'] * 100, 1) if row['applied'] else 0}
         for name, row in stats.items()),
        key=lambda r: (-r['saved'], r['portal']),
    )


def avg_days_to_apply(jobs):
    """Días promedio entre que se guarda una oferta y se postula (None si no hay datos)."""
    days = []
    for job in jobs:
        saved, applied = _as_date(job.get('created_at')), _as_date(job.get('applied_date'))
        if saved and applied and applied >= saved and job.get('status') in APPLIED_OR_LATER:
            days.append((applied - saved).days)
    return round(sum(days) / len(days), 1) if days else None


@app.route('/api/analytics/advanced')
def api_analytics_advanced():
    """Métricas avanzadas: tiempos promedio por etapa, tasa respuesta, heatmap."""
    from collections import defaultdict

    try:
        all_jobs = db_manager.get_all_tracked_jobs()

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

        return jsonify({
            'success': True,
            'total': total,
            'response_rate': response_rate,
            'success_rate': success_rate,
            'rejection_rate': rejection_rate,
            'by_status': dict(by_status),
            'heatmap': heatmap,
            'funnel': funnel,
            'insights': insights,
            'by_portal': portal_stats(all_jobs),
            'avg_days_to_apply': avg_days_to_apply(all_jobs),
        })

    except Exception as e:
        logger.error(f"Error in advanced analytics: {e}")
        return jsonify({'success': False, 'error': 'Error interno del servidor'}), 500


# ─────────────────────────────────────────────────────────────
# EXPORTACIÓN – Excel y PDF
# ─────────────────────────────────────────────────────────────
