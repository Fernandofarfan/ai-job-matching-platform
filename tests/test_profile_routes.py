"""Tests de las rutas de perfil."""
from unittest import mock


def _patch_profiles(app, profiles):
    """Reemplaza get_all_user_profiles en el módulo de la app por un valor fijo."""
    view_globals = app.view_functions['view_profile'].__globals__
    return mock.patch.dict(view_globals, {'get_all_user_profiles': lambda: profiles})


def test_view_profile_redirects_to_latest_role(client, app):
    """Con varios perfiles, redirige al de upload_date más reciente."""
    profiles = {
        'data': {'upload_date': '2026-01-01T10:00:00'},
        'dev': {'upload_date': '2026-02-01T10:00:00'},
    }
    with _patch_profiles(app, profiles):
        response = client.get('/view_profile')
    assert response.status_code == 302
    assert response.headers['Location'].endswith('/view_profile/dev')


def test_view_profile_without_profiles_redirects_to_upload(client, app):
    """Sin perfiles, redirige a la página de carga de CV."""
    with _patch_profiles(app, {}):
        response = client.get('/view_profile')
    assert response.status_code == 302
    assert response.headers['Location'].endswith('/profile')


def test_delete_all_data_requires_post(client):
    """'Borrar mis datos' no se dispara con un GET (enlace o prefetch)."""
    assert client.get('/delete_profile').status_code == 405
