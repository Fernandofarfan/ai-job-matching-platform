"""Tests de hardening de seguridad."""
import io
import os


def test_debug_directories_hidden_when_not_debug(client, app):
    app.debug = False
    assert client.get('/debug/directories').status_code == 404


def test_upload_resume_rejects_unsupported_extension(client):
    data = {'role_type': 'data', 'resume': (io.BytesIO(b'x'), 'malware.exe')}
    response = client.post('/upload_resume', data=data, content_type='multipart/form-data')
    assert response.status_code == 302
    assert not any(f.endswith('malware.exe') for f in os.listdir('uploads'))


def test_upload_resume_sanitizes_path_traversal(client, tmp_path, monkeypatch):
    import app as flask_app
    saved = []
    monkeypatch.setattr(flask_app.resume_parser, 'parse_resume', lambda path: saved.append(path) or None)
    data = {'role_type': '../x', 'resume': (io.BytesIO(b'cv'), '../../evil.txt')}
    client.post('/upload_resume', data=data, content_type='multipart/form-data')
    assert saved, 'el archivo válido debería procesarse'
    path = saved[0]
    assert os.path.dirname(path) == 'uploads'
    assert '..' not in os.path.basename(path)
    os.remove(path)
