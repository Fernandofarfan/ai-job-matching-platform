"""CSV de resultados a Excel (tracker_export.results_excel)."""
import io

from openpyxl import load_workbook

import tracker_export


def test_results_excel(tmp_path):
    path = tmp_path / 'r.csv'
    path.write_text('Title,Company,overall_match\nData Engineer,Acme,87\nQA,Globant,40\n', encoding='latin-1')
    sheet = load_workbook(io.BytesIO(tracker_export.results_excel(str(path)))).active
    assert sheet.title == 'Resultados' and sheet['A1'].value == 'Title'
    assert sheet['B3'].value == 'Globant' and sheet.freeze_panes == 'A2'
