"""
ODS (OpenDocument Spreadsheet) export backend using odfpy.
Falls back gracefully if odfpy is not installed.
"""
import io
from datetime import datetime
from django.http import HttpResponse

from .base import BaseExporter


class OdsExporter(BaseExporter):
    content_type = 'application/vnd.oasis.opendocument.spreadsheet'
    file_extension = 'ods'

    def export(self, admin_instance, queryset, options: dict) -> HttpResponse:
        try:
            from odf.opendocument import OpenDocumentSpreadsheet
            from odf.style import Style, TextProperties, TableColumnProperties, TableCellProperties
            from odf.text import P
            from odf.table import Table, TableColumn, TableRow, TableCell
        except ImportError:
            raise ImportError(
                "odfpy is required for ODS export. "
                "Install it with: pip install odfpy"
            )

        doc = OpenDocumentSpreadsheet()
        table = Table(name=admin_instance.model.__name__[:31])

        include_headers = options.get('include_headers', True)
        include_footer = options.get('include_footer', False)

        def make_cell(value):
            tc = TableCell()
            tc.addElement(P(text=str(value) if value is not None else ''))
            return tc

        # Header row
        if include_headers:
            header_row = TableRow()
            for header in self.get_headers(admin_instance):
                header_row.addElement(make_cell(header))
            table.addElement(header_row)

        # Data rows
        rows = self.get_rows(admin_instance, queryset, options)
        for row_data in rows:
            tr = TableRow()
            for value in row_data:
                tr.addElement(make_cell(value))
            table.addElement(tr)

        # Footer row
        if include_footer and rows:
            footer_row = TableRow()
            footer_text = f"Exported {len(rows)} records on {datetime.now().strftime('%Y-%m-%d %H:%M')}"
            footer_row.addElement(make_cell(footer_text))
            table.addElement(footer_row)

        doc.spreadsheet.addElement(table)

        buf = io.BytesIO()
        doc.save(buf)
        buf.seek(0)

        filename = f"{admin_instance.model.__name__}_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.ods"
        response = HttpResponse(content_type=self.content_type)
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        response.write(buf.getvalue())
        return response
