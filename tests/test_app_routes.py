"""
test_app_routes.py – Tests de rutas principales de la app.
"""
import json


class TestMainRoutes:
    """Rutas de navegación estándar."""

    def test_index_returns_200(self, client):
        response = client.get('/')
        assert response.status_code == 200

    def test_results_returns_200(self, client):
        response = client.get('/results')
        assert response.status_code == 200

    def test_profile_returns_200(self, client):
        response = client.get('/profile')
        assert response.status_code == 200

    def test_analytics_returns_200(self, client):
        response = client.get('/analytics')
        assert response.status_code == 200

    def test_tracker_returns_200(self, client):
        response = client.get('/tracker')
        assert response.status_code == 200

    def test_connections_returns_200(self, client):
        response = client.get('/connections')
        assert response.status_code == 200

    def test_nonexistent_route_returns_404(self, client):
        response = client.get('/this-route-does-not-exist-xyz')
        assert response.status_code == 404

    def test_status_endpoint_returns_json(self, client):
        response = client.get('/status')
        assert response.status_code == 200
        data = json.loads(response.data)
        # Debe tener los keys de scraping
        assert 'indeed_scraping' in data
        assert 'linkedin_scraping' in data


class TestTrackerAPI:
    """Endpoints de la API del Tracker."""

    def test_tracker_stats(self, api):
        response = api.get('/api/tracker/stats')
        assert response.status_code == 200
        data = response.json()
        assert data['success'] is True
        assert 'stats' in data
        # Los jobs del mock tienen applied, interviewing, bookmarked
        stats = data['stats']
        assert 'applied' in stats or 'interviewing' in stats or 'bookmarked' in stats


class TestProfileAPI:
    """Endpoints relacionados al perfil de usuario."""

    def test_api_all_profiles_returns_ok(self, api):
        response = api.get('/api/all_profiles')
        assert response.status_code == 200
        data = response.json()
        assert data['success'] is True

    def test_upload_resume_no_file_redirects(self, client):
        response = client.post('/upload_resume', data={})
        # Debería redirigir o dar un error flash, no un 500
        assert response.status_code in (302, 200, 400)
