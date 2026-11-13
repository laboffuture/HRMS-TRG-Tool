"""
travel/apps.py
──────────────
Registers the Travel module as a Horilla app.
URL patterns are injected dynamically in ready() — same pattern as helpdesk,
payroll etc. in Horilla 2.x (settings.APPS / settings.SIDEBARS replace the
old horilla.horilla_settings / horilla.horilla_apps modules).
"""

from django.apps import AppConfig
from django.conf import settings
from django.utils.translation import gettext_lazy as _


class TravelConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "travel"
    verbose_name = _("Travel & Expense")

    def ready(self):
        from django.urls import include, path

        from horilla.urls import urlpatterns
        from travel import signals  # noqa: F401 — connect signals

        # Register with Horilla's app registry
        if "travel" not in settings.APPS:
            settings.APPS.append("travel")

        # Register in sidebar navigation (drives the left-hand menu)
        if "travel" not in settings.SIDEBARS:
            settings.SIDEBARS.append("travel")

        # Mount URL patterns under /travel/
        urlpatterns.append(
            path("travel/", include("travel.urls.urlpatterns")),
        )
        super().ready()
