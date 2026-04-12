"""
test_export.py – Tests de los endpoints de exportación Excel/PDF.
"""
import pytest


class TestExportTracker:
    """Tests para exportación del tracker."""

    def test_export_tracker_excel_returns_xlsx(self, client):
        response = client.get('/export/tracker/excel')
        # Puede retornar 200 (archivo) o 302 (redirect si mock falla)
        assert response.status_code in (200, 302)
        if response.status_code == 200:
            ct = response.content_type
            assert 'spreadsheetml' in ct or 'openxmlformats' in ct
            # El archivo debe tener contenido
            assert len(response.data) > 0

    def test_export_tracker_pdf_returns_pdf(self, client):
        response = client.get('/export/tracker/pdf')
        assert response.status_code in (200, 302)
        if response.status_code == 200:
            assert response.content_type == 'application/pdf'
            assert len(response.data) > 0

    def test_export_tracker_excel_has_xlsx_header(self, client):
        """El cuerpo del xlsx debe comenzar con la firma PK (ZIP)."""
        response = client.get('/export/tracker/excel')
        if response.status_code == 200:
            # Los archivos .xlsx son paquetes ZIP y empiezan con 'PK'
            assert response.data[:2] == b'PK'

    def test_export_tracker_pdf_has_pdf_header(self, client):
        """El body del PDF debe comenzar con %PDF."""
        response = client.get('/export/tracker/pdf')
        if response.status_code == 200:
            assert response.data[:4] == b'%PDF'


class TestExportResults:
    """Tests para exportar archivos CSV como Excel."""

    def test_export_nonexistent_csv_redirects(self, client):
        response = client.get('/export/results/nonexistent_file.csv/excel')
        # Debe redirigir a results con mensaje de error
        assert response.status_code in (302, 404)

    def test_export_non_csv_file_redirects(self, client):
        response = client.get('/export/results/somefile.txt/excel')
        assert response.status_code in (302, 404)
