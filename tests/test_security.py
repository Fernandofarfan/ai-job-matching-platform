"""
test_security.py – Tests de seguridad: path traversal, CSRF y endpoint abierto.
"""
import os


class TestPathTraversal:
    """Ninguna ruta debe leer/escribir fuera de su directorio permitido."""

    def test_batch_optimize_traversal_rejected(self, client):
        r = client.post('/api/batch_optimize',
                        json={'filename': '../.env', 'num_jobs': 1})
        assert r.status_code == 404
        assert r.json()['success'] is False

    def test_batch_optimize_absolute_path_rejected(self, client):
        r = client.post('/api/batch_cover_letters',
                        json={'filename': '/etc/passwd', 'num_jobs': 1})
        assert r.status_code == 404

    def test_salary_analysis_traversal_rejected(self, client):
        r = client.post('/api/salary/analyze-csv',
                        json={'filename': '../../secrets.csv'})
        assert r.status_code == 404

    def test_salary_analysis_requires_csv(self, client):
        r = client.post('/api/salary/analyze-csv', json={'filename': '.env'})
        assert r.status_code == 404

    def test_export_results_traversal_redirects(self, client):
        r = client.get('/export/results/../.env/excel', follow_redirects=False)
        # path param no matchea slashes / o nombre rechazado → 404 o redirect
        assert r.status_code in (302, 303, 404)

    def test_download_csv_rejects_non_csv(self, client):
        r = client.get('/download_csv/secret.txt', follow_redirects=False)
        assert r.status_code in (302, 303)

    def test_test_task_status_invalid_id_rejected(self, client):
        r = client.get('/test_task_status',
                       params={'task_id': '../../etc/passwd'})
        assert r.status_code == 400

    def test_test_task_status_valid_uuid_ok(self, client):
        r = client.get('/test_task_status',
                       params={'task_id': '123e4567-e89b-12d3-a456-426614174000'})
        # UUID válido pero inexistente → 404
        assert r.status_code == 404

    def test_upload_resume_malicious_role_rejected(self, client, tmp_path):
        r = client.post(
            '/upload_resume',
            files={'resume': ('cv.pdf', b'%PDF-1.4 fake', 'application/pdf')},
            data={'role_type': 'a/../../evil'},
            follow_redirects=False,
        )
        assert r.status_code in (302, 303)
        # No debe crearse ningún archivo fuera ni con ese nombre
        assert not os.path.exists('uploads/a')

    def test_upload_resume_bad_extension_rejected(self, client):
        r = client.post(
            '/upload_resume',
            files={'resume': ('evil.exe', b'MZ...', 'application/octet-stream')},
            data={'role_type': 'data_scientist'},
            follow_redirects=False,
        )
        assert r.status_code in (302, 303)
        assert not any(f.endswith('.exe')
                       for f in os.listdir('uploads')) if os.path.isdir('uploads') else True


class TestCSRFAndOrigin:
    """Validación de Origin en peticiones que cambian estado."""

    def test_evil_origin_rejected(self, client):
        r = client.post(
            '/api/tracker/job',
            json={'title': 'X', 'company': 'Y'},
            headers={'Origin': 'https://evil-testserver.com'},
        )
        assert r.status_code == 403
        assert r.json()['success'] is False

    def test_suffix_bypass_blocked(self, client):
        """evil-testserver NO debe pasar por ser sufijo de testserver."""
        r = client.post(
            '/api/tracker/job',
            json={'title': 'X', 'company': 'Y'},
            headers={'Origin': 'https://evil-testserver'},
        )
        assert r.status_code == 403

    def test_same_origin_allowed(self, client):
        r = client.post(
            '/api/tracker/job',
            json={'title': 'Origin Job', 'company': 'OriginCo'},
            headers={'Origin': 'http://testserver'},
        )
        assert r.status_code == 200
        assert r.json()['success'] is True


class TestExtensionEndpoint:
    """El endpoint de la extensión solo acepta Origin chrome-extension://."""

    EXT_HEADERS = {'Origin': 'chrome-extension://abcdefghijklmnop'}

    def test_extension_origin_allowed_without_session(self):
        """La extensión (sin sesión) puede escribir SOLO en su endpoint."""
        import main
        from fastapi.testclient import TestClient
        anon = TestClient(main.app, raise_server_exceptions=False)
        r = anon.post(
            '/api/tracker/save-from-extension',
            json={'title': 'Ext Job', 'company': 'ExtCo',
                  'platform': 'linkedin'},
            headers=self.EXT_HEADERS,
        )
        assert r.status_code == 200
        assert r.json()['success'] is True

    def test_no_origin_requires_auth(self, client):
        """curl sin Origin ni sesión → 401 (no más escritura anónima)."""
        import main
        # Cliente temporal deslogueado (misma app, sin cookies)
        from fastapi.testclient import TestClient
        anon = TestClient(main.app, raise_server_exceptions=False)
        r = anon.post('/api/tracker/save-from-extension',
                      json={'title': 'Anon', 'company': 'NoAuth'})
        assert r.status_code == 401

    def test_browser_origin_requires_auth(self, client):
        import main
        from fastapi.testclient import TestClient
        anon = TestClient(main.app, raise_server_exceptions=False)
        r = anon.post(
            '/api/tracker/save-from-extension',
            json={'title': 'Web', 'company': 'NoAuth'},
            headers={'Origin': 'http://testserver'},
        )
        assert r.status_code == 401

    def test_extension_origin_blocked_on_other_endpoints(self, client):
        r = client.post('/api/tracker/job',
                        json={'title': 'X', 'company': 'Y'},
                        headers=self.EXT_HEADERS)
        assert r.status_code == 403
