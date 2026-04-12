"""
test_analytics.py – Tests del endpoint de Analytics avanzado.
"""
import json
import pytest


class TestAnalyticsAdvanced:
    """Tests del endpoint /api/analytics/advanced."""

    def test_advanced_analytics_returns_success(self, client):
        response = client.get('/api/analytics/advanced')
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['success'] is True

    def test_advanced_analytics_has_required_keys(self, client):
        response = client.get('/api/analytics/advanced')
        data = json.loads(response.data)
        required_keys = ['total', 'response_rate', 'success_rate',
                         'rejection_rate', 'by_status', 'heatmap', 'funnel', 'insights']
        for key in required_keys:
            assert key in data, f"Missing key: {key}"

    def test_advanced_analytics_total_is_correct(self, client):
        response = client.get('/api/analytics/advanced')
        data = json.loads(response.data)
        # Mock tiene 3 trabajos
        assert data['total'] == 3

    def test_advanced_analytics_heatmap_has_7_days(self, client):
        response = client.get('/api/analytics/advanced')
        data = json.loads(response.data)
        assert len(data['heatmap']) == 7

    def test_advanced_analytics_funnel_structure(self, client):
        response = client.get('/api/analytics/advanced')
        data = json.loads(response.data)
        funnel = data['funnel']
        assert isinstance(funnel, list)
        assert len(funnel) > 0
        for stage in funnel:
            assert 'key' in stage
            assert 'label' in stage
            assert 'count' in stage
            assert 'conversion' in stage

    def test_advanced_analytics_insights_not_empty(self, client):
        response = client.get('/api/analytics/advanced')
        data = json.loads(response.data)
        assert isinstance(data['insights'], list)
        assert len(data['insights']) > 0

    def test_advanced_analytics_insight_structure(self, client):
        response = client.get('/api/analytics/advanced')
        data = json.loads(response.data)
        for insight in data['insights']:
            assert 'icon' in insight
            assert 'type' in insight
            assert 'text' in insight
            assert insight['type'] in ('success', 'warning', 'info')

    def test_advanced_analytics_rates_are_floats(self, client):
        response = client.get('/api/analytics/advanced')
        data = json.loads(response.data)
        for rate_key in ('response_rate', 'success_rate', 'rejection_rate'):
            assert isinstance(data[rate_key], (int, float))
            assert 0 <= data[rate_key] <= 100

    def test_analytics_page_loads(self, client):
        """La página de analytics HTML renderiza correctamente."""
        response = client.get('/analytics')
        assert response.status_code == 200
        content = response.data.decode('utf-8')
        # Verificar elementos clave del template
        assert 'Centro de Analytics' in content
        assert 'Embudo de Conversión' in content

    def test_tracker_stats_counts_by_status(self, client):
        """El endpoint /api/tracker/stats agrupa bien por estado."""
        response = client.get('/api/tracker/stats')
        assert response.status_code == 200
        data = json.loads(response.data)
        stats = data['stats']
        # Mock tiene 1 applied, 1 interviewing, 1 bookmarked
        assert stats.get('applied', 0) == 1
        assert stats.get('interviewing', 0) == 1
        assert stats.get('bookmarked', 0) == 1
