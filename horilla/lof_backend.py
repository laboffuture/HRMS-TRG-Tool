"""
LOF Platform SSO Authentication Backend — Horilla HR
─────────────────────────────────────────────────────
Validates a LOF platform JWT against the platform backend (/auth/me),
then finds or creates the matching Django User + Horilla Employee.

This is what makes HR part of the global LOF login — users never
see a separate Horilla login form when coming from the portal.
"""

import logging
import os

import requests
from django.contrib.auth import get_user_model
from django.conf import settings

LOF_API = getattr(settings, "LOF_API_URL", "http://localhost:8000")
logger = logging.getLogger(__name__)


class LofSSOBackend:
    """
    Authenticate via LOF platform token.
    Called by: horilla/lof_sso_view.py → django.contrib.auth.authenticate()
    """

    def authenticate(self, request, lof_token=None):
        if not lof_token:
            return None

        # ── 1. Validate token against platform backend ───────────────────
        try:
            res = requests.get(
                f"{LOF_API}/auth/me",
                headers={"Authorization": f"Bearer {lof_token}"},
                timeout=5,
            )
        except requests.RequestException:
            return None

        if not res.ok:
            return None

        lof_user = res.json()
        # Platform returns: { id, username, role, full_name }
        username  = lof_user.get("username", "")
        full_name = lof_user.get("full_name") or username
        role      = lof_user.get("role", "trainer")
        is_admin  = role == "admin"

        name_parts = full_name.split(" ", 1)
        first_name = name_parts[0]
        last_name  = name_parts[1] if len(name_parts) > 1 else ""

        # ── 2. Find or create Django User ────────────────────────────────
        User = get_user_model()
        user, created = User.objects.get_or_create(
            username=username,
            defaults={
                "first_name":    first_name,
                "last_name":     last_name,
                "email":         f"{username}@lof.internal",
                "is_staff":      is_admin,
                "is_superuser":  is_admin,
            },
        )

        if not created:
            # Keep permissions in sync with platform role
            changed = False
            if user.is_staff != is_admin:
                user.is_staff = is_admin
                changed = True
            if user.is_superuser != is_admin:
                user.is_superuser = is_admin
                changed = True
            if changed:
                user.save(update_fields=["is_staff", "is_superuser"])

        # ── 3. Find or create Horilla Employee record ────────────────────
        # Employee record is required for HR features (leave, payslip, etc.)
        try:
            from employee.models import Employee
            if not Employee.objects.filter(employee_user_id=user).exists():
                Employee.objects.create(
                    employee_user_id=user,
                    employee_first_name=first_name,
                    employee_last_name=last_name,
                    email=f"{username}@lof.internal",
                    phone="-",
                    badge_id=username,
                )
        except Exception:
            # Don't fail login if employee creation fails
            logger.warning("LOF SSO: employee creation failed for %s", username, exc_info=True)

        # ── 4. Make sure the employee belongs to a company ───────────────
        # Horilla 2.x scopes every query to the user's company; a non-superuser
        # whose work info has no company sees nothing (not even their own
        # record). New SSO users get the HQ company (or the first one).
        try:
            self._ensure_company(user)
        except Exception:
            logger.warning("LOF SSO: could not assign company for %s", username, exc_info=True)

        return user

    @staticmethod
    def _ensure_company(user):
        from base.models import Company
        from employee.models import Employee, EmployeeWorkInformation

        # entire(): bypass company scoping — we are fixing exactly that here.
        employee = Employee.objects.entire().filter(employee_user_id=user).first()
        if employee is None:
            return
        work_info, _created = EmployeeWorkInformation.objects.get_or_create(
            employee_id=employee
        )
        if work_info.company_id_id:
            return
        company = Company.objects.filter(hq=True).first() or Company.objects.order_by("id").first()
        if company is not None:
            work_info.company_id = company
            work_info.save()

    def get_user(self, user_id):
        User = get_user_model()
        try:
            return User.objects.get(pk=user_id)
        except User.DoesNotExist:
            return None
