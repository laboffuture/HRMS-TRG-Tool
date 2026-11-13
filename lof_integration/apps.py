"""
lof_integration — LOF/TRG-specific glue for Horilla 2.x.

Holds what is ours rather than upstream's, so Horilla upgrades stay clean:
  * templates/lof/app_switcher.html  — navbar "LOF Apps" switcher
  * management command setup_lof_theme — LOF Blue colour theme

The SSO backend/views live in horilla/lof_*.py and settings in
horilla/settings/local_settings.py.
"""

from django.apps import AppConfig


class LofIntegrationConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "lof_integration"
    verbose_name = "LOF Integration"

    def ready(self):
        from django.urls import path

        from horilla.urls import urlpatterns
        from lof_integration.views import payroll_flow

        # Same URL as in the 1.x fork: /payroll/payroll-flow/ (name kept).
        urlpatterns.append(
            path("payroll/payroll-flow/", payroll_flow, name="payroll-flow"),
        )
        super().ready()
