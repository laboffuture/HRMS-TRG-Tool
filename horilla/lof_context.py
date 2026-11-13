"""
LOF Global Context Processor
─────────────────────────────
Injects portal/app URLs into every Django template so the
LOF shell navbar can render its links without hardcoding them.
"""

from django.conf import settings


def lof_urls(request):
    return {
        "PORTAL_URL":   getattr(settings, "PORTAL_URL",   "http://localhost:3001"),
        "FEEDBACK_URL": getattr(settings, "FEEDBACK_URL", "http://localhost:3000"),
        "TIMESHEET_URL":getattr(settings, "TIMESHEET_URL","http://localhost:9002/timesheet"),
        "SYNCFLOW_URL": getattr(settings, "SYNCFLOW_URL", "http://localhost:3002/syncflow"),
    }
