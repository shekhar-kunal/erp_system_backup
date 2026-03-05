from django.shortcuts import redirect


class SetupMiddleware:
    """Redirect to setup wizard if ERP has not been configured yet."""

    EXEMPT_PREFIXES = (
        '/static/',
        '/media/',
        '/setup/',
        '/login/',
        '/logout/',
        '/favicon.ico',
    )

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if any(request.path.startswith(p) for p in self.EXEMPT_PREFIXES):
            return self.get_response(request)

        from .models import SetupStatus
        if not SetupStatus.is_complete():
            return redirect('setup:setup_welcome')

        return self.get_response(request)
