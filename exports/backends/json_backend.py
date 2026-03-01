"""
JSON export backend using Python's stdlib json module.
Exports as an array of objects (dicts), one per record.
"""
import json
from datetime import datetime
from django.http import HttpResponse

from .base import BaseExporter


class JsonExporter(BaseExporter):
    content_type = 'application/json'
    file_extension = 'json'

    def export(self, admin_instance, queryset, options: dict) -> HttpResponse:
        headers = self.get_headers(admin_instance)
        rows = self.get_rows(admin_instance, queryset, options)

        data = [dict(zip(headers, row)) for row in rows]

        payload = {
            'model': admin_instance.model.__name__,
            'exported_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'record_count': len(data),
            'records': data,
        }

        if options.get('include_footer', False):
            payload['footer'] = f"Exported {len(data)} records"

        filename = f"{admin_instance.model.__name__}_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        response = HttpResponse(content_type=self.content_type)
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        response.write(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
        return response
