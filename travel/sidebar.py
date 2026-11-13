"""
travel/sidebar.py
─────────────────
Navigation menu definition for the Travel & Expense module.
Horilla reads MENU, IMG_SRC, and SUBMENUS from this file to build the
left-hand sidebar.  Accessibility functions control per-user visibility.
"""

from django.urls import reverse
from django.utils.translation import gettext_lazy as trans

MENU    = trans("Travel & Expense")
IMG_SRC = "images/ui/traveldesk.png"

SUBMENUS = [
    {
        "menu":          trans("Dashboard"),
        "redirect":      reverse("travel-dashboard"),
        "accessibility": "travel.sidebar.dashboard_accessibility",
    },
    {
        "menu":          trans("My Travel Requests"),
        "redirect":      reverse("travel-my-requests"),
    },
    {
        "menu":          trans("All Travel Requests"),
        "redirect":      reverse("travel-request-list"),
        "accessibility": "travel.sidebar.all_requests_accessibility",
    },
    {
        "menu":          trans("New Travel Request"),
        "redirect":      reverse("travel-request-create"),
    },
    {
        "menu":          trans("Pending Approvals"),
        "redirect":      reverse("travel-pending-approvals"),
        "accessibility": "travel.sidebar.approval_accessibility",
    },
    {
        "menu":          trans("Expense Claims"),
        "redirect":      reverse("travel-expense-list"),
    },
    {
        "menu":          trans("My Expense Claims"),
        "redirect":      reverse("travel-my-expense-claims"),
    },
    # ── Admin / configuration ───────────────────────────────────────────────
    {
        "menu":          trans("Travel Entitlements"),
        "redirect":      reverse("travel-entitlement-list"),
        "accessibility": "travel.sidebar.admin_accessibility",
    },
    {
        "menu":          trans("Purposes of Travel"),
        "redirect":      reverse("travel-purpose-list"),
        "accessibility": "travel.sidebar.admin_accessibility",
    },
    {
        "menu":          trans("Bookings"),
        "redirect":      reverse("travel-booking-list"),
        "accessibility": "travel.sidebar.booking_accessibility",
    },
    {
        "menu":          trans("Travel Invoices"),
        "redirect":      reverse("travel-invoice-list"),
        "accessibility": "travel.sidebar.finance_accessibility",
    },
]


# ── Accessibility callbacks ────────────────────────────────────────────────────

def dashboard_accessibility(request, submenu, user_perms, *args, **kwargs):
    """Everyone can see the dashboard — shows personal data when no broader perm."""
    return True


def all_requests_accessibility(request, submenu, user_perms, *args, **kwargs):
    """Only users who can view all requests (HR / Managers) see this entry."""
    return request.user.has_perm("travel.view_all_travelrequest")


def approval_accessibility(request, submenu, user_perms, *args, **kwargs):
    """Managers / HOD / HR who can validate or approve requests."""
    return (
        request.user.has_perm("travel.validate_travelrequest")
        or request.user.has_perm("travel.approve_travelrequest")
    )


def booking_accessibility(request, submenu, user_perms, *args, **kwargs):
    """Travel Desk — users with book permission."""
    return request.user.has_perm("travel.book_travelrequest")


def admin_accessibility(request, submenu, user_perms, *args, **kwargs):
    """HR admin configuration pages."""
    return (
        request.user.is_superuser
        or request.user.has_perm("travel.add_travelentitlement")
        or request.user.has_perm("travel.add_purposeoftravel")
    )


def finance_accessibility(request, submenu, user_perms, *args, **kwargs):
    """Finance team — users who can add/change travel invoices."""
    return (
        request.user.is_superuser
        or request.user.has_perm("travel.add_travelinvoice")
        or request.user.has_perm("travel.change_travelinvoice")
    )
