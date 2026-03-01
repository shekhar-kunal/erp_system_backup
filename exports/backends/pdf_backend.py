"""
PDF export backend using weasyprint.
Renders an HTML template to PDF via Django's template engine.
Falls back gracefully if weasyprint is not installed.
"""
from datetime import datetime
from django.http import HttpResponse
from django.template.loader import render_to_string

from .base import BaseExporter


class PdfExporter(BaseExporter):
    content_type = 'application/pdf'
    file_extension = 'pdf'

    def export(self, admin_instance, queryset, options: dict) -> HttpResponse:
        try:
            import weasyprint
        except ImportError:
            raise ImportError(
                "weasyprint is required for PDF export. "
                "Install it with: pip install weasyprint"
            )

        headers = self.get_headers(admin_instance)
        rows = self.get_rows(admin_instance, queryset, options)

        html_content = render_to_string(
            'admin/exports/pdf_table.html',
            {
                'model_name': admin_instance.model._meta.verbose_name_plural.title(),
                'headers': headers,
                'rows': rows,
                'record_count': len(rows),
                'exported_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'include_footer': options.get('include_footer', False),
            }
        )

        pdf_bytes = weasyprint.HTML(string=html_content).write_pdf()

        filename = f"{admin_instance.model.__name__}_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
        response = HttpResponse(content_type=self.content_type)
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        response.write(pdf_bytes)
        return response
