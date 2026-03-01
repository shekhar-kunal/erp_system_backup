"""
CSV export backend using Python's stdlib csv module.
"""
import csv
import io
from datetime import datetime
from django.http import HttpResponse

from .base import BaseExporter


class CsvExporter(BaseExporter):
    content_type = 'text/csv'
    file_extension = 'csv'

    def export(self, admin_instance, queryset, options: dict) -> HttpResponse:
        include_headers = options.get('include_headers', True)

        buf = io.StringIO()
        writer = csv.writer(buf)

        if include_headers:
            writer.writerow(self.get_headers(admin_instance))

        for row in self.get_rows(admin_instance, queryset, options):
            writer.writerow(row)

        if options.get('include_footer', False):
            writer.writerow([])
            writer.writerow([f"Exported {queryset.count()} records on {datetime.now().strftime('%Y-%m-%d %H:%M')}"])

        filename = f"{admin_instance.model.__name__}_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        response = HttpResponse(content_type=self.content_type)
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        response.write(buf.getvalue())
        return response
