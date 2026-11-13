"""
test_export.py – Tests de los endpoints de exportación Excel/PDF.
"""
import pytest


class TestExportTracker:
    """Tests para exportación del tracker."""

    def test_export_tracker_excel_returns_xlsx(self, client):
        response = client.get('/export/tracker/excel', follow_redirects=False)
        # El mock de BD siempre funciona: SIEMPRE debe salir el archivo
        assert response.status_code == 200
        ct = response.headers.get('content-type', '')
        assert 'spreadsheetml' in ct or 'openxmlformats' in ct
        # El archivo debe tener contenido
        assert len(response.content) > 0

    def test_export_tracker_pdf_returns_pdf(self, client):
        response = client.get('/export/tracker/pdf', follow_redirects=False)
        assert response.status_code == 200
        assert response.headers.get('content-type') == 'application/pdf'
        assert len(response.content) > 0

    def test_export_tracker_excel_has_xlsx_header(self, client):
        """El cuerpo del xlsx debe comenzar con la firma PK (ZIP)."""
        response = client.get('/export/tracker/excel', follow_redirects=False)
        assert response.status_code == 200
        # Los archivos .xlsx son paquetes ZIP y empiezan con 'PK'
        assert response.content[:2] == b'PK'

    def test_export_tracker_pdf_has_pdf_header(self, client):
        """El body del PDF debe comenzar con %PDF."""
        response = client.get('/export/tracker/pdf', follow_redirects=False)
        assert response.status_code == 200
        assert response.content[:4] == b'%PDF'


class TestExportResults:
    """Tests para exportar archivos CSV como Excel."""

    def test_export_nonexistent_csv_redirects(self, client):
        response = client.get('/export/results/nonexistent_file.csv/excel',
                              follow_redirects=False)
        # Debe redirigir a results con mensaje de error
        assert response.status_code in (302, 303, 404)

    def test_export_non_csv_file_redirects(self, client):
        response = client.get('/export/results/somefile.txt/excel',
                              follow_redirects=False)
        assert response.status_code in (302, 303, 404)
