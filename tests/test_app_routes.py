"""
test_app_routes.py – Tests de rutas principales de la app Flask.
"""
import json
import pytest


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

    def test_get_tracker_jobs_returns_success(self, client):
        response = client.get('/api/tracker/jobs')
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['success'] is True
        assert 'jobs' in data
        assert isinstance(data['jobs'], list)
        assert data['count'] == 3  # 3 trabajos del mock

    def test_get_single_job_returns_correct_data(self, client):
        response = client.get('/api/tracker/job/1')
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['success'] is True
        assert data['job']['title'] == 'Data Analyst'
        assert data['job']['company'] == 'Acme Corp'

    def test_get_nonexistent_job_returns_404(self, client):
        response = client.get('/api/tracker/job/9999')
        assert response.status_code == 404
        data = json.loads(response.data)
        assert data['success'] is False

    def test_add_job_to_tracker(self, client):
        payload = {
            'title': 'DevOps Engineer',
            'company': 'CloudCo',
            'location': 'Remoto',
            'status': 'bookmarked'
        }
        response = client.post(
            '/api/tracker/job',
            data=json.dumps(payload),
            content_type='application/json'
        )
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['success'] is True
        assert 'job_id' in data

    def test_add_job_missing_required_fields_returns_400(self, client):
        # Falta 'company'
        payload = {'title': 'Some Job'}
        response = client.post(
            '/api/tracker/job',
            data=json.dumps(payload),
            content_type='application/json'
        )
        assert response.status_code == 400
        data = json.loads(response.data)
        assert data['success'] is False

    def test_update_job_status(self, client):
        payload = {'status': 'interviewing'}
        response = client.put(
            '/api/tracker/job/1/status',
            data=json.dumps(payload),
            content_type='application/json'
        )
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['success'] is True

    def test_update_job_status_missing_status_returns_400(self, client):
        response = client.put(
            '/api/tracker/job/1/status',
            data=json.dumps({}),
            content_type='application/json'
        )
        assert response.status_code == 400

    def test_delete_tracked_job(self, client):
        response = client.delete('/api/tracker/job/3')
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['success'] is True

    def test_tracker_stats(self, client):
        response = client.get('/api/tracker/stats')
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['success'] is True
        assert 'stats' in data
        # Los jobs del mock tienen applied, interviewing, bookmarked
        stats = data['stats']
        assert 'applied' in stats or 'interviewing' in stats or 'bookmarked' in stats


class TestProfileAPI:
    """Endpoints relacionados al perfil de usuario."""

    def test_api_all_profiles_returns_ok(self, client):
        response = client.get('/api/all_profiles')
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['success'] is True

    def test_upload_resume_no_file_redirects(self, client):
        response = client.post('/upload_resume', data={})
        # Debería redirigir o dar un error flash, no un 500
        assert response.status_code in (302, 200, 400)
