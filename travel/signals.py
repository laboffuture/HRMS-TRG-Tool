"""
travel/signals.py
─────────────────
Post-save signals for the Travel & Expense module.

Signal responsibilities:
  • TravelRequest  — notify relevant parties on status transitions
  • TravelBooking  — mark parent request as "booked" when booking is created
  • EmployeeAdvance— set employee from travel request if not set
  • ExpenseClaim   — recalculate totals, mark travel request as "completed"
"""

import logging
import os
import threading

from django.db import transaction
from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

_agent_log = logging.getLogger("travel.agent_trigger")


# ── Helper: send notification in background ────────────────────────────────────

def _notify_async(recipients, subject, body, actor=None):
    """
    Send an in-app notification once the current transaction commits.

    Uses Horilla's ``notify`` signal, which fills the required actor fields
    (creating Notification rows directly without an actor always failed and
    was silently swallowed). ``actor`` is the object the notification is
    about — here the TravelRequest.
    """
    def _send():
        try:
            from django.urls import reverse
            from notifications.signals import notify

            redirect_url = (
                reverse("travel-request-detail", kwargs={"pk": actor.pk})
                if actor is not None
                else ""
            )
            notify.send(
                actor,
                recipient=list(recipients),
                verb=subject,
                description=body,
                icon="airplane-outline",
                redirect=redirect_url,
            )
        except Exception:
            _agent_log.warning("Travel notification failed", exc_info=True)

    transaction.on_commit(_send)


# ── Travel Desk Agent auto-trigger ────────────────────────────────────────────

def _trigger_travel_agent_async(request_id: int) -> None:
    """
    Fire-and-forget: POST to the LOF Platform Travel Desk Agent so it picks up
    a newly-approved travel request immediately — no manual admin click needed.

    The platform backend URL is read from PLATFORM_API_URL (default localhost:8000).
    Failures are logged but never propagate — the Django save must not break.
    """
    def _call():
        try:
            import urllib.request as _ur
            api_url = os.environ.get("PLATFORM_API_URL", "http://localhost:8000").rstrip("/")
            url = f"{api_url}/claude/agents/travel/horilla/{request_id}/trigger"
            req = _ur.Request(url, data=b"{}", method="POST")
            req.add_header("Content-Type", "application/json")
            # Optional shared secret so the platform can verify the caller.
            agent_token = os.environ.get("PLATFORM_AGENT_TOKEN", "")
            if agent_token:
                req.add_header("Authorization", f"Bearer {agent_token}")
            with _ur.urlopen(req, timeout=10):
                pass  # response body not needed
            _agent_log.info("Travel agent triggered for Horilla request %s", request_id)
        except Exception as exc:
            _agent_log.warning(
                "Travel agent auto-trigger failed for request %s: %s",
                request_id, exc,
            )

    # Start only after commit so the agent never reads an uncommitted request.
    transaction.on_commit(
        lambda: threading.Thread(target=_call, daemon=True).start()
    )


# ── TravelRequest signals ──────────────────────────────────────────────────────

@receiver(pre_save, sender="travel.TravelRequest")
def travel_request_pre_save(sender, instance, **kwargs):
    """
    Capture previous status so we can detect transitions in post_save.
    """
    if instance.pk:
        try:
            old = sender.objects.get(pk=instance.pk)
            instance._prev_status = old.status
        except sender.DoesNotExist:
            instance._prev_status = None
    else:
        instance._prev_status = None


@receiver(post_save, sender="travel.TravelRequest")
def travel_request_post_save(sender, instance, created, **kwargs):
    """
    On status transitions:
      draft → pending_hr         : notify HR team
      pending_hr → pending_manager: notify reporting manager
      pending_manager → pending_hod: notify HOD
      approved                   : notify employee (travel desk picks up)
      rejected / cancelled       : notify employee
    """
    prev   = getattr(instance, "_prev_status", None)
    curr   = instance.status
    emp_user = getattr(instance.employee, "employee_user_id", None)

    if prev == curr and not created:
        return

    # Notify employee when their request is approved / rejected / booked
    if curr in ("approved", "booked", "completed", "rejected", "cancelled") and emp_user:
        verbs = {
            "approved":  _("Your travel request to %(dest)s has been approved."),
            "booked":    _("Your travel to %(dest)s has been booked. Check your itinerary."),
            "completed": _("Your travel request to %(dest)s is marked complete."),
            "rejected":  _("Your travel request to %(dest)s was rejected."),
            "cancelled": _("Your travel request to %(dest)s has been cancelled."),
        }
        msg = verbs[curr] % {"dest": instance.travel_to}
        _notify_async([emp_user], str(msg), str(msg), actor=instance)

    # ── Auto-trigger Travel Desk Agent ─────────────────────────────────────────
    # When a request transitions to 'approved' (not already approved), hand it
    # off to the LOF Platform Travel Desk Agent automatically.
    # prev == curr guard above already filters no-change saves.
    if curr == "approved":
        _trigger_travel_agent_async(instance.id)

    # Create initial approval trail records when submitted to HR
    if curr == "pending_hr" and created or (prev == "draft" and curr == "pending_hr"):
        from travel.models import TravelApproval
        for level in ("hr", "manager", "hod"):
            TravelApproval.objects.get_or_create(
                travel_request=instance,
                level=level,
                defaults={"status": "pending"},
            )


# ── TravelBooking signals ──────────────────────────────────────────────────────

@receiver(post_save, sender="travel.TravelBooking")
def travel_booking_post_save(sender, instance, created, **kwargs):
    """
    When a booking is first created, move parent request to 'booked'.
    Also record booked_on timestamp if missing.
    """
    if created:
        req = instance.travel_request
        if req.status == "approved":
            req.status = "booked"
            req.save(update_fields=["status"])

        if not instance.booked_on:
            sender.objects.filter(pk=instance.pk).update(booked_on=timezone.now())


# ── EmployeeAdvance signals ────────────────────────────────────────────────────

@receiver(pre_save, sender="travel.EmployeeAdvance")
def employee_advance_pre_save(sender, instance, **kwargs):
    """
    Auto-fill employee from travel request if not explicitly set.
    """
    if not instance.employee_id and instance.travel_request_id:
        instance.employee = instance.travel_request.employee


# ── ExpenseClaim signals ───────────────────────────────────────────────────────

@receiver(post_save, sender="travel.ExpenseClaim")
def expense_claim_post_save(sender, instance, **kwargs):
    """
    • Recalculate total_claimed from detail lines.
    • When claim is approved and linked to a travel request,
      mark the request as 'completed'.
    • Adjust related EmployeeAdvance records.
    """
    from travel.models import ExpenseClaim

    # Recompute total_claimed from detail rows (avoid infinite recursion guard)
    new_total = sum(
        d.amount_claimed for d in instance.details.all()
    )
    if instance.total_claimed != new_total:
        ExpenseClaim.objects.filter(pk=instance.pk).update(total_claimed=new_total)

    # Mark travel as completed when claim is paid
    if instance.status == "paid" and instance.travel_request:
        req = instance.travel_request
        if req.status not in ("completed", "cancelled", "rejected"):
            req.status = "completed"
            req.save(update_fields=["status"])

    # Auto-fill advance_adjusted from linked advances
    if instance.travel_request:
        from travel.models import EmployeeAdvance
        total_advance = sum(
            a.amount
            for a in EmployeeAdvance.objects.filter(
                travel_request=instance.travel_request,
                status__in=("paid", "adjusted"),
            )
        )
        if instance.advance_adjusted != total_advance:
            ExpenseClaim.objects.filter(pk=instance.pk).update(
                advance_adjusted=total_advance
            )
