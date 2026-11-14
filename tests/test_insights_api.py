"""APIs de estadísticas, perfiles y postulaciones migradas a FastAPI (routers/insights.py)."""


def test_get_applications_passes_filters(api, tracker_db):
    """Los filtros de la query llegan a la base y la respuesta mantiene la forma de Flask."""
    data = api.get('/api/get_applications?status=applied&company=Acme').json()
    tracker_db.get_applications.assert_called_with({'status': 'applied', 'company': 'Acme'})
    assert data['success'] and data['count'] == len(data['applications'])


def test_get_applications_hides_internal_errors(api, tracker_db, monkeypatch):
    """Un error de MySQL no se filtra en la respuesta."""
    monkeypatch.setattr(tracker_db.get_applications, 'side_effect', RuntimeError('detalle secreto'))
    resp = api.get('/api/get_applications')
    assert resp.status_code == 500 and 'secreto' not in resp.text and resp.json()['success'] is False


def test_profile_summary_404_without_profile(api):
    """Sin CV subido, 404 con el formato de error del frontend."""
    resp = api.get('/api/profile_summary')
    assert resp.status_code == 404 and resp.json() == {'success': False, 'error': 'No profile found'}


def test_insights_require_login(api, monkeypatch):
    """Con APP_PASSWORD, todas las rutas migradas devuelven 401 sin sesión."""
    monkeypatch.setenv('APP_PASSWORD', 'secreta')
    for url in ('/api/get_applications', '/api/all_profiles', '/api/profile_summary',
                '/api/analytics/advanced', '/api/tracker/stats', '/api/ranking'):
        assert api.get(url).status_code == 401, url
