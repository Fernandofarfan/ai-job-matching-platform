"""
routers/export.py — Exportación del tracker y resultados a Excel/PDF.
Migrado desde app.py (Flask send_file → Response de FastAPI).
"""
import io
import os
import logging
from datetime import datetime

import pandas as pd
from fastapi import APIRouter, Request
from fastapi.responses import Response

from core.state import db_manager
from core.templating import flash, redirect

router = APIRouter(tags=["export"])
logger = logging.getLogger(__name__)

XLSX_MIME = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'


@router.get("/export/tracker/excel")
async def export_tracker_excel(request: Request):
    """Exporta el Job Tracker completo a Excel (.xlsx)."""
    try:
        import openpyxl
        from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
        from openpyxl.utils import get_column_letter

        jobs = db_manager.get_all_tracked_jobs()

        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Job Tracker"

        header_fill = PatternFill(start_color="667EEA", end_color="667EEA", fill_type="solid")
        header_font = Font(name='Calibri', bold=True, color="FFFFFF", size=11)
        center_align = Alignment(horizontal='center', vertical='center', wrap_text=True)
        left_align = Alignment(horizontal='left', vertical='center', wrap_text=True)
        thin_border = Border(
            left=Side(style='thin', color='E5E7EB'),
            right=Side(style='thin', color='E5E7EB'),
            top=Side(style='thin', color='E5E7EB'),
            bottom=Side(style='thin', color='E5E7EB')
        )

        status_colors = {
            'bookmarked': "FEF3C7", 'applying': "DBEAFE",
            'applied': "E0E7FF", 'interviewing': "D1FAE5",
            'negotiating': "FDE68A", 'accepted': "A7F3D0", 'rejected': "FEE2E2"
        }

        columns = ['ID', 'Título', 'Empresa', 'Ubicación', 'Salario',
                   'Estado', 'Entusiasmo', 'Fecha Guardado', 'Fecha Aplicado',
                   'Deadline', 'Notas', 'Enlace']
        db_keys = ['id', 'title', 'company', 'location', 'salary',
                   'status', 'excitement', 'date_saved', 'date_applied',
                   'deadline', 'notes', 'job_link']

        for col_idx, col_name in enumerate(columns, start=1):
            cell = ws.cell(row=1, column=col_idx, value=col_name)
            cell.font = header_font
            cell.fill = header_fill
            cell.alignment = center_align
            cell.border = thin_border

        ws.row_dimensions[1].height = 22

        for row_idx, job in enumerate(jobs, start=2):
            status = job.get('status', '')
            row_fill_color = status_colors.get(status, "FFFFFF")
            row_fill = PatternFill(start_color=row_fill_color, end_color=row_fill_color,
                                   fill_type="solid")

            for col_idx, key in enumerate(db_keys, start=1):
                value = job.get(key, '')
                if hasattr(value, 'strftime'):
                    value = value.strftime('%Y-%m-%d')
                cell = ws.cell(row=row_idx, column=col_idx, value=value)
                cell.fill = row_fill
                cell.border = thin_border
                cell.alignment = left_align if col_idx > 2 else center_align
            ws.row_dimensions[row_idx].height = 18

        col_widths = [6, 32, 22, 18, 14, 15, 12, 16, 16, 14, 30, 40]
        for i, width in enumerate(col_widths, start=1):
            ws.column_dimensions[get_column_letter(i)].width = width

        ws.freeze_panes = 'A2'

        # Hoja de resumen
        ws2 = wb.create_sheet("Resumen")
        from collections import Counter
        statuses = Counter(j.get('status', 'unknown') for j in jobs)
        ws2.append(['Estado', 'Cantidad', '% del Total'])
        for st, cnt in sorted(statuses.items(), key=lambda x: -x[1]):
            pct = round(cnt / len(jobs) * 100, 1) if jobs else 0
            ws2.append([st, cnt, f"{pct}%"])

        output = io.BytesIO()
        wb.save(output)
        output.seek(0)

        filename = f"EmpleoIA_Tracker_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx"
        return Response(
            content=output.read(),
            media_type=XLSX_MIME,
            headers={"Content-Disposition": f"attachment; filename={filename}"},
        )
    except Exception as e:
        logger.error(f"Error exporting tracker to Excel: {e}")
        flash(request, f'Error al exportar: {str(e)}', 'danger')
        return redirect('/tracker')


@router.get("/export/tracker/pdf")
async def export_tracker_pdf(request: Request):
    """Exporta el Job Tracker a PDF con ReportLab."""
    try:
        from reportlab.lib.pagesizes import A4, landscape
        from reportlab.lib import colors
        from reportlab.lib.units import cm
        from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

        jobs = db_manager.get_all_tracked_jobs()

        output = io.BytesIO()
        doc = SimpleDocTemplate(output, pagesize=landscape(A4),
                                leftMargin=1.5 * cm, rightMargin=1.5 * cm,
                                topMargin=1.5 * cm, bottomMargin=1.5 * cm)

        styles = getSampleStyleSheet()
        title_style = ParagraphStyle('title', parent=styles['Title'],
                                     fontSize=18, textColor=colors.HexColor('#667EEA'),
                                     spaceAfter=6)
        subtitle_style = ParagraphStyle('sub', parent=styles['Normal'],
                                        fontSize=10, textColor=colors.HexColor('#6B7280'),
                                        spaceAfter=16)

        elements = []
        elements.append(Paragraph("EmpleoIA – Reporte de Postulaciones", title_style))
        elements.append(Paragraph(
            f"Generado el {datetime.now().strftime('%d/%m/%Y %H:%M')} · {len(jobs)} registros totales",
            subtitle_style))
        elements.append(Spacer(1, 10))

        col_names = ['Título', 'Empresa', 'Ubicación', 'Estado', 'Fecha Aplicado', 'Salario']
        db_keys = ['title', 'company', 'location', 'status', 'date_applied', 'salary']
        data = [col_names]
        for job in jobs[:200]:
            row = []
            for key in db_keys:
                val = job.get(key, '')
                if hasattr(val, 'strftime'):
                    val = val.strftime('%d/%m/%Y')
                row.append(str(val)[:40] if val else '-')
            data.append(row)

        col_widths_pdf = [7 * cm, 6 * cm, 5 * cm, 3.5 * cm, 3.5 * cm, 3.5 * cm]
        table = Table(data, colWidths=col_widths_pdf, repeatRows=1)

        status_color_map = {
            'bookmarked': colors.HexColor('#FEF3C7'),
            'applying': colors.HexColor('#DBEAFE'),
            'applied': colors.HexColor('#E0E7FF'),
            'interviewing': colors.HexColor('#D1FAE5'),
            'negotiating': colors.HexColor('#FDE68A'),
            'accepted': colors.HexColor('#A7F3D0'),
            'rejected': colors.HexColor('#FEE2E2'),
        }

        base_style = [
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#667EEA')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 9),
            ('FONTSIZE', (0, 1), (-1, -1), 8),
            ('GRID', (0, 0), (-1, -1), 0.4, colors.HexColor('#E5E7EB')),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1),
             [colors.white, colors.HexColor('#F9FAFB')]),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('LEFTPADDING', (0, 0), (-1, -1), 6),
            ('RIGHTPADDING', (0, 0), (-1, -1), 6),
            ('TOPPADDING', (0, 0), (-1, -1), 5),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ]

        for i, job in enumerate(jobs[:200], start=1):
            st = job.get('status', '')
            if st in status_color_map:
                base_style.append(('BACKGROUND', (3, i), (3, i), status_color_map[st]))

        table.setStyle(TableStyle(base_style))
        elements.append(table)

        doc.build(elements)
        output.seek(0)

        filename = f"EmpleoIA_Tracker_{datetime.now().strftime('%Y%m%d_%H%M')}.pdf"
        return Response(
            content=output.read(),
            media_type='application/pdf',
            headers={"Content-Disposition": f"attachment; filename={filename}"},
        )
    except Exception as e:
        logger.error(f"Error exporting tracker to PDF: {e}")
        flash(request, f'Error al exportar PDF: {str(e)}', 'danger')
        return redirect('/tracker')


@router.get("/export/results/{filename}/excel")
async def export_results_excel(request: Request, filename: str):
    """Exporta un CSV de resultados como Excel formateado."""
    try:
        import openpyxl
        from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
        from openpyxl.utils import get_column_letter

        from core.security import is_safe_results_path
        file_path = is_safe_results_path(filename)
        if not file_path or not os.path.exists(file_path) or not filename.lower().endswith('.csv'):
            flash(request, 'Archivo no encontrado', 'danger')
            return redirect('/results')

        df = pd.read_csv(file_path, encoding='latin-1')

        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Resultados"

        header_fill = PatternFill(start_color="764BA2", end_color="764BA2", fill_type="solid")
        header_font = Font(name='Calibri', bold=True, color="FFFFFF", size=10)
        center_align = Alignment(horizontal='center', vertical='center', wrap_text=True)
        thin_border = Border(
            left=Side(style='thin', color='E5E7EB'), right=Side(style='thin', color='E5E7EB'),
            top=Side(style='thin', color='E5E7EB'), bottom=Side(style='thin', color='E5E7EB')
        )

        for col_idx, col_name in enumerate(df.columns, start=1):
            cell = ws.cell(row=1, column=col_idx, value=col_name)
            cell.font = header_font
            cell.fill = header_fill
            cell.alignment = center_align
            cell.border = thin_border

        ws.row_dimensions[1].height = 20

        alt_fill = PatternFill(start_color="F3F4F6", end_color="F3F4F6", fill_type="solid")
        for row_idx, row in enumerate(df.itertuples(index=False), start=2):
            row_fill = alt_fill if row_idx % 2 == 0 else PatternFill()
            for col_idx, value in enumerate(row, start=1):
                cell = ws.cell(row=row_idx, column=col_idx,
                               value=str(value) if value is not None else '')
                cell.fill = row_fill
                cell.border = thin_border
                cell.alignment = Alignment(horizontal='left', vertical='center',
                                           wrap_text=False)
            ws.row_dimensions[row_idx].height = 15

        for col_idx, col_name in enumerate(df.columns, start=1):
            max_len = max(len(str(col_name)),
                          df[col_name].astype(str).str.len().max() if len(df) > 0 else 10)
            ws.column_dimensions[get_column_letter(col_idx)].width = min(max_len + 4, 50)

        ws.freeze_panes = 'A2'

        output = io.BytesIO()
        wb.save(output)
        output.seek(0)

        base = filename.replace('.csv', '')
        dl_name = f"{base}_export.xlsx"
        return Response(
            content=output.read(),
            media_type=XLSX_MIME,
            headers={"Content-Disposition": f"attachment; filename={dl_name}"},
        )
    except Exception as e:
        logger.error(f"Error exporting results to Excel: {e}")
        flash(request, f'Error al exportar: {str(e)}', 'danger')
        return redirect('/results')
