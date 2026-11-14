"""
test_analytics.py – Tests del endpoint de Analytics avanzado.
"""


class TestAnalyticsAdvanced:
    """Tests del endpoint /api/analytics/advanced."""

    def test_advanced_analytics_returns_success(self, api):
        response = api.get('/api/analytics/advanced')
        assert response.status_code == 200
        data = response.json()
        assert data['success'] is True

    def test_advanced_analytics_has_required_keys(self, api):
        response = api.get('/api/analytics/advanced')
        data = response.json()
        required_keys = ['total', 'response_rate', 'success_rate',
                         'rejection_rate', 'by_status', 'heatmap', 'funnel', 'insights']
        for key in required_keys:
            assert key in data, f"Missing key: {key}"

    def test_advanced_analytics_total_is_correct(self, api):
        response = api.get('/api/analytics/advanced')
        data = response.json()
        # Mock tiene 3 trabajos
        assert data['total'] == 3

    def test_advanced_analytics_heatmap_has_7_days(self, api):
        response = api.get('/api/analytics/advanced')
        data = response.json()
        assert len(data['heatmap']) == 7

    def test_advanced_analytics_funnel_structure(self, api):
        response = api.get('/api/analytics/advanced')
        data = response.json()
        funnel = data['funnel']
        assert isinstance(funnel, list)
        assert len(funnel) > 0
        for stage in funnel:
            assert 'key' in stage
            assert 'label' in stage
            assert 'count' in stage
            assert 'conversion' in stage

    def test_advanced_analytics_insights_not_empty(self, api):
        response = api.get('/api/analytics/advanced')
        data = response.json()
        assert isinstance(data['insights'], list)
        assert len(data['insights']) > 0

    def test_advanced_analytics_insight_structure(self, api):
        response = api.get('/api/analytics/advanced')
        data = response.json()
        for insight in data['insights']:
            assert 'icon' in insight
            assert 'type' in insight
            assert 'text' in insight
            assert insight['type'] in ('success', 'warning', 'info')

    def test_advanced_analytics_rates_are_floats(self, api):
        response = api.get('/api/analytics/advanced')
        data = response.json()
        for rate_key in ('response_rate', 'success_rate', 'rejection_rate'):
            assert isinstance(data[rate_key], (int, float))
            assert 0 <= data[rate_key] <= 100

    def test_analytics_page_loads(self, client):
        """La página de analytics HTML renderiza correctamente."""
        response = client.get('/analytics')
        assert response.status_code == 200
        content = response.data.decode('utf-8')
        # /analytics lo sirve FastAPI con dashboard.html
        assert 'Embudo de Conversión' in content
        assert '/static/js/pages/dashboard.js' in content

    def test_tracker_stats_counts_by_status(self, api):
        """El endpoint /api/tracker/stats agrupa bien por estado."""
        response = api.get('/api/tracker/stats')
        assert response.status_code == 200
        data = response.json()
        stats = data['stats']
        # Mock tiene 1 applied, 1 interviewing, 1 bookmarked
        assert stats.get('applied', 0) == 1
        assert stats.get('interviewing', 0) == 1
        assert stats.get('bookmarked', 0) == 1


def test_portal_of_detects_known_portals():
    """El portal sale del dominio del enlace."""
    from tracker_stats import portal_of
    assert portal_of('https://ar.computrabajo.com/ofertas/1') == 'Computrabajo'
    assert portal_of('https://www.getonbrd.com/jobs/x') == 'GetOnBoard'
    assert portal_of('https://www.zonajobs.com.ar/x') == 'ZonaJobs'
    assert portal_of('https://example.com') == 'Otros'
    assert portal_of(None) == 'Otros'


def test_portal_stats_and_days_to_apply():
    """Tasa de respuesta por portal = respuestas / postulaciones; días promedio de guardado a postulación."""
    from datetime import date, datetime

    from tracker_stats import avg_days_to_apply, portal_stats
    jobs = [
        {'job_link': 'https://www.bumeran.com.ar/a', 'status': 'applied',
         'created_at': datetime(2026, 11, 1, 10), 'applied_date': date(2026, 11, 3)},
        {'job_link': 'https://www.bumeran.com.ar/b', 'status': 'interviewing',
         'created_at': '2026-11-01 08:00:00', 'applied_date': '2026-11-05'},
        {'job_link': 'https://www.bumeran.com.ar/c', 'status': 'bookmarked', 'created_at': None, 'applied_date': None},
        {'job_link': 'https://ar.computrabajo.com/d', 'status': 'rejected', 'created_at': None, 'applied_date': None},
    ]
    assert portal_stats(jobs) == [
        {'portal': 'Bumeran', 'saved': 3, 'applied': 2, 'responses': 1, 'response_rate': 50.0},
        {'portal': 'Computrabajo', 'saved': 1, 'applied': 1, 'responses': 0, 'response_rate': 0},
    ]
    assert avg_days_to_apply(jobs) == 3.0
    assert avg_days_to_apply([]) is None


def test_advanced_analytics_includes_portals(api):
    """El endpoint devuelve el desglose por portal."""
    data = api.get('/api/analytics/advanced').json()
    assert sum(p['saved'] for p in data['by_portal']) == data['total']
    assert 'avg_days_to_apply' in data


def test_advanced_analytics_hides_internal_errors(tracker_db, api, monkeypatch):
    """Un error interno no se filtra en la respuesta."""
    db = tracker_db
    monkeypatch.setattr(db.get_all_tracked_jobs, 'side_effect', RuntimeError('detalle secreto'))
    resp = api.get('/api/analytics/advanced')
    assert resp.status_code == 500 and 'secreto' not in resp.text


def test_avg_days_to_apply_ignores_rejected():
    """Una oferta guardada y descartada no cuenta como postulación."""
    from tracker_stats import avg_days_to_apply
    jobs = [{'status': 'rejected', 'created_at': '2026-01-01', 'applied_date': '2026-01-01'}]
    assert avg_days_to_apply(jobs) is None


def test_history_makes_rejected_and_days_exact():
    """Con historial, una rechazada cuenta como postulada solo si pasó por 'applied'."""
    from datetime import datetime
    from tracker_stats import avg_days_to_apply, portal_stats
    jobs = [
        {'id': 1, 'status': 'rejected', 'job_link': 'https://www.bumeran.com.ar/x', 'created_at': '2026-01-01'},
        {'id': 2, 'status': 'rejected', 'job_link': 'https://www.bumeran.com.ar/y', 'created_at': '2026-01-01'},
    ]
    history = [
        {'application_id': 1, 'old_status': None, 'new_status': 'bookmarked', 'changed_at': datetime(2026, 1, 1)},
        {'application_id': 1, 'old_status': 'bookmarked', 'new_status': 'applied', 'changed_at': datetime(2026, 1, 4)},
        {'application_id': 1, 'old_status': 'applied', 'new_status': 'rejected', 'changed_at': datetime(2026, 1, 9)},
        {'application_id': 2, 'old_status': None, 'new_status': 'bookmarked', 'changed_at': datetime(2026, 1, 1)},
        {'application_id': 2, 'old_status': 'bookmarked', 'new_status': 'rejected', 'changed_at': datetime(2026, 1, 2)},
    ]
    assert portal_stats(jobs, history)[0]['applied'] == 1
    assert avg_days_to_apply(jobs, history) == 3.0


def test_days_to_apply_uses_creation_when_created_as_applied():
    """Una postulación cargada ya postulada usa su fecha de alta aunque después pase a entrevista."""
    from tracker_stats import avg_days_to_apply
    jobs = [{'id': 1, 'status': 'interviewing', 'created_at': '2026-01-01', 'applied_date': '2026-01-01'}]
    history = [
        {'application_id': 1, 'old_status': None, 'new_status': 'applied', 'changed_at': '2026-01-01'},
        {'application_id': 1, 'old_status': 'applied', 'new_status': 'interviewing', 'changed_at': '2026-01-10'},
    ]
    assert avg_days_to_apply(jobs, history) == 0
