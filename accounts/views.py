import datetime

from django.conf import settings
from django.contrib.auth import login, logout, REDIRECT_FIELD_NAME
from django.shortcuts import redirect, render
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.http import require_http_methods

from .forms import LoginForm


@never_cache
@csrf_protect
def login_view(request):
    """Custom ERP login page at /login/."""
    if request.user.is_authenticated:
        return redirect(_resolve_redirect(request, request.user))

    next_url = (
        request.GET.get(REDIRECT_FIELD_NAME, '')
        or request.POST.get(REDIRECT_FIELD_NAME, '')
    )

    error = None
    if request.method == 'POST':
        form = LoginForm(request, data=request.POST)
        if form.is_valid():
            user = form.get_user()

            # RBAC lockout check before allowing login
            try:
                from rbac.services import PermissionService
                if PermissionService.is_account_locked(user):
                    error = 'Your account is locked. Please contact your administrator.'
                    form = LoginForm(request)
                    return render(request, 'accounts/login.html', {
                        'form': form, 'next': next_url, 'error': error,
                    })
            except Exception:
                pass

            login(request, user)
            _reset_failed_attempts(user)
            _log_action(user, 'login', request)

            # Redirect: next param > admin (system admin) > dashboard (RBAC users)
            if next_url and _is_safe_url(next_url, request):
                return redirect(next_url)
            return redirect(_resolve_redirect(request, user))
        else:
            # Increment failed attempts for the submitted username
            _increment_failed_attempts(request.POST.get('username', ''))
    else:
        form = LoginForm(request)

    return render(request, 'accounts/login.html', {
        'form': form,
        'next': next_url,
    })


@never_cache
def logout_view(request):
    """POST → logout + redirect to /login/. GET → confirmation page."""
    if request.method == 'POST':
        _log_action(request.user if request.user.is_authenticated else None, 'logout', request)
        logout(request)
        return redirect(settings.LOGOUT_REDIRECT_URL)
    return render(request, 'accounts/logged_out.html')


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _resolve_redirect(request, user):
    """Return the appropriate post-login URL for this user."""
    if getattr(user, 'is_system_admin', False):
        return '/admin/'
    return '/dashboard/'


def _is_safe_url(url, request):
    return url_has_allowed_host_and_scheme(
        url,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    )


def _reset_failed_attempts(user):
    try:
        profile = user.profile
        if profile.failed_login_attempts > 0:
            profile.failed_login_attempts = 0
            profile.save(update_fields=['failed_login_attempts'])
    except Exception:
        pass


def _increment_failed_attempts(username):
    from django.contrib.auth import get_user_model
    User = get_user_model()
    try:
        user    = User.objects.get(username=username)
        profile = user.profile
        profile.failed_login_attempts += 1
        if profile.failed_login_attempts >= 5:
            profile.locked_until = timezone.now() + datetime.timedelta(minutes=30)
        profile.save(update_fields=['failed_login_attempts', 'locked_until'])
    except Exception:
        pass


def _log_action(user, action, request):
    if user is None:
        return
    try:
        from rbac.services import PermissionService
        PermissionService.log_action(
            user=user,
            action=action,
            ip_address=PermissionService.get_client_ip(request),
            user_agent=request.META.get('HTTP_USER_AGENT', ''),
        )
    except Exception:
        pass
