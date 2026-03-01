"""
Base exporter class. All format backends inherit from this.
The central get_rows() method builds tabular data from any admin instance
that has export_fields / export_methods attributes (ExcelExportMixin pattern).
"""
from decimal import Decimal
from datetime import datetime, date


class BaseExporter:
    """
    Abstract base for all export format backends.

    Subclasses must set:
        content_type: str       e.g. 'application/vnd.openxmlformats-...'
        file_extension: str     e.g. 'xlsx'

    Subclasses must implement:
        export(admin_instance, queryset, options) -> HttpResponse
    """
    content_type: str = 'application/octet-stream'
    file_extension: str = 'bin'

    def export(self, admin_instance, queryset, options: dict):
        raise NotImplementedError

    # ------------------------------------------------------------------
    # Shared data extraction helpers
    # ------------------------------------------------------------------

    def get_headers(self, admin_instance) -> list[str]:
        """Return column header labels."""
        fields = self._get_fields(admin_instance)
        return [str(f).replace('_', ' ').replace('__', ' / ').upper() for f in fields]

    def get_rows(self, admin_instance, queryset, options: dict) -> list[list]:
        """
        Return a list of rows (each row is a list of plain Python values).
        Uses admin_instance.export_fields and export_methods to extract data.
        Applies date formatting from options['date_format'].
        """
        fields = self._get_fields(admin_instance)
        date_fmt = options.get('date_format', '%Y-%m-%d')
        rows = []
        for obj in queryset:
            row = []
            for field in fields:
                try:
                    value = self._get_field_value(admin_instance, obj, field, date_fmt)
                except Exception:
                    value = 'ERROR'
                row.append(value)
            rows.append(row)
        return rows

    def _get_fields(self, admin_instance) -> list[str]:
        if hasattr(admin_instance, 'export_fields') and admin_instance.export_fields:
            return list(admin_instance.export_fields)
        return [f.name for f in admin_instance.model._meta.fields]

    def _get_field_value(self, admin_instance, obj, field_name: str, date_fmt: str):
        # Custom method override
        if hasattr(admin_instance, 'export_methods') and admin_instance.export_methods:
            if field_name in admin_instance.export_methods:
                raw = admin_instance.export_methods[field_name](obj)
                return self._prepare_value(raw, date_fmt)

        # Dotted / dunder path traversal
        if '__' in field_name:
            value = obj
            for part in field_name.split('__'):
                value = getattr(value, part, None)
                if value is None:
                    break
            return self._prepare_value(value, date_fmt)

        value = getattr(obj, field_name, '')
        return self._prepare_value(value, date_fmt)

    def _prepare_value(self, value, date_fmt: str):
        """Convert any Python value to a plain type suitable for export."""
        if value is None:
            return ''
        if isinstance(value, bool):
            return 'Yes' if value else 'No'
        if isinstance(value, datetime):
            if value.tzinfo is not None:
                value = value.replace(tzinfo=None)
            return value.strftime(date_fmt + ' %H:%M')
        if isinstance(value, date):
            return value.strftime(date_fmt)
        if isinstance(value, Decimal):
            return float(value)
        if callable(value) and not isinstance(value, type):
            return self._prepare_value(value(), date_fmt)
        return str(value) if not isinstance(value, (int, float)) else value

    # ------------------------------------------------------------------
    # ZIP helper
    # ------------------------------------------------------------------

    @staticmethod
    def wrap_in_zip(response, inner_filename: str):
        """
        Wrap an HttpResponse's content in a ZIP archive.
        Returns a new HttpResponse with application/zip content type.
        """
        import io
        import zipfile
        from django.http import HttpResponse as DjangoHttpResponse

        buf = io.BytesIO()
        with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
            zf.writestr(inner_filename, response.content)

        zip_name = inner_filename.rsplit('.', 1)[0] + '.zip'
        zip_response = DjangoHttpResponse(content_type='application/zip')
        zip_response['Content-Disposition'] = f'attachment; filename="{zip_name}"'
        zip_response.write(buf.getvalue())
        return zip_response, zip_name
