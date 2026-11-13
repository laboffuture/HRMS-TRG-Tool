"""
Client-specific overrides — LOF / TRG deployment.

Imported last from horilla.settings.__init__ (after base + addons).
Override settings here; do NOT use ``from .base import *`` — that re-exports
base MEDIA_* values and wipes AWS S3 paths set by addons.py.

Everything LOF-specific that used to be patched into horilla/settings.py,
horilla/horilla_apps.py and horilla/horilla_context_processors.py in the 1.x
fork lives here now, so upstream upgrades only touch base.py.
"""

import os

from .base import (
    AUTHENTICATION_BACKENDS,
    DATABASES,
    INSTALLED_APPS,
    SIDEBARS,
    TEMPLATES,
    env,
)

# ── LOF apps ────────────────────────────────────────────────────────────────
# Travel & Expense (LOF ticketing SOP). Its AppConfig.ready() also registers
# itself in settings.APPS / settings.SIDEBARS and mounts /travel/.
if "travel" not in INSTALLED_APPS:
    INSTALLED_APPS += ["travel"]
# LOF glue: app-switcher template, setup_lof_theme command.
if "lof_integration" not in INSTALLED_APPS:
    INSTALLED_APPS += ["lof_integration"]
if "travel" not in SIDEBARS:
    SIDEBARS += ["travel"]

# ── Database: shared lof_internal Postgres, Horilla tables in "hr" schema ───
# Only applied for PostgreSQL connections configured through DATABASE_URL,
# matching the 1.x behaviour.
if env("DATABASE_URL", default=None) and "postgresql" in DATABASES["default"].get(
    "ENGINE", ""
):
    DATABASES["default"].setdefault("OPTIONS", {})
    DATABASES["default"]["OPTIONS"]["options"] = env(
        "DB_SEARCH_PATH_OPTIONS", default="-c search_path=hr,public"
    )

# ── Sub-path routing (nginx serves HR under /hr) ───────────────────────────
_script_name = os.environ.get("FORCE_SCRIPT_NAME", "")
if _script_name:
    FORCE_SCRIPT_NAME = _script_name

# ── LOF Global SSO ──────────────────────────────────────────────────────────
# There is no separate HR login. All auth goes through the LOF portal.
# @login_required redirects to LOGIN_URL; horilla/lof_sso_view.portal_login
# bounces the user to the portal (or shows Horilla's form when
# LOF_LOCAL_LOGIN=True for local development).
PORTAL_URL = env("PORTAL_URL", default="http://localhost:3001")
LOF_API_URL = env("LOF_API_URL", default="http://localhost:8000")
FEEDBACK_URL = env("FEEDBACK_URL", default="http://localhost:3000")
TIMESHEET_URL = env("TIMESHEET_URL", default="http://localhost:9002/timesheet")
SYNCFLOW_URL = env("SYNCFLOW_URL", default="http://localhost:3002/syncflow")
LOF_LOCAL_LOGIN = env.bool("LOF_LOCAL_LOGIN", default=False)

# Axes must stay first (it short-circuits locked-out clients); the LOF
# backend goes right after it, ahead of the company-scoped ModelBackend.
if "horilla.lof_backend.LofSSOBackend" not in AUTHENTICATION_BACKENDS:
    AUTHENTICATION_BACKENDS.insert(1, "horilla.lof_backend.LofSSOBackend")

# Injects PORTAL_URL / FEEDBACK_URL / ... for the LOF app switcher.
_ctx = TEMPLATES[0]["OPTIONS"]["context_processors"]
if "horilla.lof_context.lof_urls" not in _ctx:
    _ctx.append("horilla.lof_context.lof_urls")
