"""
travel/urls/urlpatterns.py
──────────────────────────
URL patterns for the Travel & Expense module.
Mounted at: travel/ (via apps.py ready())
"""

from django.urls import path

from travel.views.expense_views import (
    travel_expense_approve,
    travel_expense_create,
    travel_expense_delete,
    travel_expense_detail,
    travel_expense_list,
    travel_expense_submit,
    travel_expense_update,
    travel_my_expense_claims,
)
from travel.views.travel_views import (
    travel_advance_create,
    travel_advance_update,
    travel_booking_create,
    travel_booking_detail,
    travel_booking_list,
    travel_booking_update,
    travel_dashboard,
    travel_entitlement_list,
    travel_entitlement_update,
    travel_invoice_create,
    travel_invoice_list,
    travel_invoice_update,
    travel_my_requests,
    travel_pending_approvals,
    travel_purpose_delete,
    travel_purpose_list,
    travel_request_approve_action,
    travel_request_cancel,
    travel_request_create,
    travel_request_delete,
    travel_request_detail,
    travel_request_list,
    travel_request_submit,
    travel_request_update,
)

urlpatterns = [
    # ── Dashboard ─────────────────────────────────────────────────────────────
    path("",                        travel_dashboard,            name="travel-dashboard"),

    # ── Travel Request ────────────────────────────────────────────────────────
    path("requests/",               travel_request_list,         name="travel-request-list"),
    path("requests/my/",            travel_my_requests,          name="travel-my-requests"),
    path("requests/create/",        travel_request_create,       name="travel-request-create"),
    path("requests/<int:pk>/",      travel_request_detail,       name="travel-request-detail"),
    path("requests/<int:pk>/edit/", travel_request_update,       name="travel-request-update"),
    path("requests/<int:pk>/delete/",travel_request_delete,      name="travel-request-delete"),
    path("requests/<int:pk>/submit/",travel_request_submit,      name="travel-request-submit"),
    path("requests/<int:pk>/cancel/",travel_request_cancel,      name="travel-request-cancel"),

    # ── Approvals ─────────────────────────────────────────────────────────────
    path("approvals/",              travel_pending_approvals,    name="travel-pending-approvals"),
    path("approvals/<int:pk>/action/", travel_request_approve_action, name="travel-approve-action"),

    # ── Travel Booking ────────────────────────────────────────────────────────
    path("bookings/",               travel_booking_list,         name="travel-booking-list"),
    path("bookings/create/<int:request_pk>/", travel_booking_create, name="travel-booking-create"),
    path("bookings/<int:pk>/",      travel_booking_detail,       name="travel-booking-detail"),
    path("bookings/<int:pk>/edit/", travel_booking_update,       name="travel-booking-update"),

    # ── Employee Advance ──────────────────────────────────────────────────────
    path("advances/create/<int:request_pk>/", travel_advance_create, name="travel-advance-create"),
    path("advances/<int:pk>/edit/",           travel_advance_update, name="travel-advance-update"),

    # ── Expense Claims ────────────────────────────────────────────────────────
    path("expenses/",               travel_expense_list,         name="travel-expense-list"),
    path("expenses/my/",            travel_my_expense_claims,    name="travel-my-expense-claims"),
    path("expenses/create/",        travel_expense_create,       name="travel-expense-create"),
    path("expenses/<int:pk>/",      travel_expense_detail,       name="travel-expense-detail"),
    path("expenses/<int:pk>/edit/", travel_expense_update,       name="travel-expense-update"),
    path("expenses/<int:pk>/delete/",travel_expense_delete,      name="travel-expense-delete"),
    path("expenses/<int:pk>/submit/",travel_expense_submit,      name="travel-expense-submit"),
    path("expenses/<int:pk>/approve/",travel_expense_approve,    name="travel-expense-approve"),

    # ── Finance — Invoices ────────────────────────────────────────────────────
    path("invoices/",               travel_invoice_list,         name="travel-invoice-list"),
    path("invoices/create/<int:booking_pk>/", travel_invoice_create, name="travel-invoice-create"),
    path("invoices/<int:pk>/edit/", travel_invoice_update,       name="travel-invoice-update"),

    # ── Admin Config ──────────────────────────────────────────────────────────
    path("config/purposes/",        travel_purpose_list,         name="travel-purpose-list"),
    path("config/purposes/<int:pk>/delete/", travel_purpose_delete, name="travel-purpose-delete"),
    path("config/entitlements/",    travel_entitlement_list,     name="travel-entitlement-list"),
    path("config/entitlements/<int:pk>/edit/", travel_entitlement_update, name="travel-entitlement-update"),
]
