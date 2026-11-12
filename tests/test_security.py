"""Tests de hardening de seguridad."""
import io
import os
from unittest import mock


def test_debug_directories_hidden_when_not_debug(client, app):
    app.debug = False
    assert client.get('/debug/directories').status_code == 404


def test_upload_resume_rejects_unsupported_extension(client):
    data = {'role_type': 'data', 'resume': (io.BytesIO(b'x'), 'malware.exe')}
    response = client.post('/upload_resume', data=data, content_type='multipart/form-data')
    assert response.status_code == 302
    assert not any(f.endswith('malware.exe') for f in os.listdir('uploads'))


def test_upload_resume_sanitizes_path_traversal(client, app):
    before = set(os.listdir('uploads'))
    data = {'role_type': '../x', 'resume': (io.BytesIO(b'cv'), '../../evil.txt')}
    save_profile = mock.Mock(return_value=True)
    with mock.patch.object(app.extensions['empleoia_services'].profiles, 'save_user_profile_for_role', save_profile):
        client.post('/upload_resume', data=data, content_type='multipart/form-data')
    new_files = set(os.listdir('uploads')) - before
    try:
        assert len(new_files) == 1
        name = new_files.pop()
        assert name.endswith('_evil.txt') and '..' not in name
        assert not os.path.exists(os.path.join('..', 'evil.txt'))
        assert save_profile.call_args.args[2] == 'x'
    finally:
        for f in set(os.listdir('uploads')) - before:
            os.remove(os.path.join('uploads', f))
