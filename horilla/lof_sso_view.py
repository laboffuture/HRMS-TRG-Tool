"""
LOF Platform SSO Views — Horilla HR
─────────────────────────────────────
Two views:

  /sso/    ← portal redirects here with ?lof_token=<jwt>
              Validates token, creates Django session, enters HR dashboard.

  /login/  ← overrides Horilla's built-in login page.
              There is NO separate HR login. Any unauthenticated access
              is sent straight back to the LOF portal.
"""

from django.conf import settings as django_settings
from django.contrib.auth import authenticate, login
from django.shortcuts import redirect
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_GET
from django.views.decorators.csrf import csrf_exempt

# Portal URL — where users authenticate globally
PORTAL_URL = getattr(django_settings, "PORTAL_URL", "http://localhost:3001")


# ── 1. SSO entry point (called by portal with ?lof_token=) ───────────────────

@csrf_exempt          # portal sends a plain GET redirect — no CSRF token
@require_GET
def lof_sso(request):
    token = request.GET.get("lof_token", "").strip()

    if not token:
        # No token supplied — bounce back to portal to re-authenticate
        return redirect(PORTAL_URL)

    # Validate token against platform /auth/me, find/create Django User
    user = authenticate(request, lof_token=token)

    if user is None:
        # Token rejected — send back to portal
        return redirect(f"{PORTAL_URL}?error=hr_sso_failed")

    # Create a Django session for this user
    login(request, user, backend="horilla.lof_backend.LofSSOBackend")

    # Land on the page the user originally wanted (or dashboard root).
    # Only same-site targets are allowed — otherwise /sso/?next=https://evil
    # would be an open redirect off a trusted login link.
    next_url = request.GET.get("next", "/")
    if not url_has_allowed_host_and_scheme(
        next_url,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        next_url = "/"
    return redirect(next_url)


# ── 2. Login page replacement — NO local login form, portal only ──────────────

def portal_login(request):
    """
    Replaces Horilla's /login/ page.
    Unauthenticated users are sent to the portal — they should never
    see an HR-specific login form.
    """
    if request.user.is_authenticated:
        # Already logged in (e.g. Django admin used ModelBackend)
        return redirect("/")

    # Local development: use Horilla's built-in login form
    if getattr(django_settings, "LOF_LOCAL_LOGIN", False):
        from base.views import login_user

        return login_user(request)

    # Send everyone else to the global portal
    return redirect(PORTAL_URL)
