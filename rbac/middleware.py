from django.contrib import messages
from django.contrib.auth import logout
from django.shortcuts import redirect

from .services import PermissionService

EXEMPT_PREFIXES = (
    '/static/',
    '/media/',
    '/login/',
    '/logout/',
    '/admin/jsi18n/',
)


class ERPSecurityMiddleware:
    """
    Enforces account lockout and working-hour restrictions.
    Superusers are always exempt.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.user.is_authenticated and not request.user.is_superuser:
            path = request.path_info
            if not any(path.startswith(p) for p in EXEMPT_PREFIXES):
                if PermissionService.is_account_locked(request.user):
                    logout(request)
                    messages.error(
                        request,
                        'Your account is locked. Please contact your administrator.',
                    )
                    return redirect('/login/')

                if not PermissionService.is_within_working_hours(request.user):
                    logout(request)
                    messages.warning(
                        request,
                        'Access is restricted outside your configured working hours.',
                    )
                    return redirect('/login/')

        return self.get_response(request)
