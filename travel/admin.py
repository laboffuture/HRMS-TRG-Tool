"""
travel/admin.py
───────────────
Register all Travel & Expense models with the Django admin site.
Uses SimpleHistoryAdmin where the model inherits HorillaModel (which uses
django-simple-history via horilla_history).
"""

from django.contrib import admin
from simple_history.admin import SimpleHistoryAdmin

from travel.models import (
    EmployeeAdvance,
    ExpenseClaim,
    ExpenseClaimDetail,
    HotelBooking,
    PurposeOfTravel,
    TravelApproval,
    TravelBooking,
    TravelEntitlement,
    TravelInvoice,
    TravelItinerary,
    TravelRequest,
)


# ── Inline admins ──────────────────────────────────────────────────────────────

class TravelItineraryInline(admin.TabularInline):
    model = TravelItinerary
    extra = 1
    fields = (
        "travel_from", "travel_to", "mode_of_travel",
        "departure", "arrival", "lodging_required",
        "check_in", "check_out", "estimated_cost",
    )


class TravelApprovalInline(admin.TabularInline):
    model = TravelApproval
    extra = 0
    readonly_fields = ("actioned_at",)
    fields = ("level", "approver", "status", "remarks", "actioned_at")


class HotelBookingInline(admin.TabularInline):
    model = HotelBooking
    extra = 0
    fields = (
        "hotel_name", "check_in", "check_out",
        "room_type", "hotel_cost", "confirmation_number",
    )


class ExpenseClaimDetailInline(admin.TabularInline):
    model = ExpenseClaimDetail
    extra = 1
    fields = (
        "expense_date", "expense_type", "description",
        "amount_claimed", "amount_approved", "receipt", "billable",
    )


# ── Model Admins ──────────────────────────────────────────────────────────────

@admin.register(PurposeOfTravel)
class PurposeOfTravelAdmin(SimpleHistoryAdmin):
    list_display  = ("name", "description", "is_active")
    search_fields = ("name",)
    list_filter   = ("is_active",)


@admin.register(TravelEntitlement)
class TravelEntitlementAdmin(SimpleHistoryAdmin):
    list_display  = (
        "job_role", "travel_class", "max_advance",
        "domestic_days_notice", "international_days_notice", "is_active",
    )
    list_filter   = ("travel_class", "is_active")
    search_fields = ("job_role__job_role",)


@admin.register(TravelRequest)
class TravelRequestAdmin(SimpleHistoryAdmin):
    list_display  = (
        "employee_name", "travel_to", "departure_date",
        "travel_type", "travel_class", "status", "is_active",
    )
    list_filter   = ("status", "travel_type", "mode_of_travel", "travel_class")
    search_fields = ("employee_name", "travel_to", "travel_from")
    readonly_fields = ("employee_name", "department", "designation", "contact_number")
    inlines       = [TravelItineraryInline, TravelApprovalInline]
    date_hierarchy = "departure_date"


@admin.register(TravelItinerary)
class TravelItineraryAdmin(admin.ModelAdmin):
    list_display  = (
        "travel_request", "travel_from", "travel_to",
        "mode_of_travel", "departure",
    )
    list_filter   = ("mode_of_travel",)
    search_fields = ("travel_from", "travel_to")


@admin.register(TravelApproval)
class TravelApprovalAdmin(admin.ModelAdmin):
    list_display  = ("travel_request", "level", "approver", "status", "actioned_at")
    list_filter   = ("level", "status")
    search_fields = ("travel_request__employee_name",)
    readonly_fields = ("actioned_at",)


@admin.register(TravelBooking)
class TravelBookingAdmin(SimpleHistoryAdmin):
    list_display  = (
        "travel_request", "pnr", "ticket_number",
        "vendor", "ticket_cost", "booked_on",
    )
    search_fields = ("pnr", "ticket_number", "vendor")
    inlines       = [HotelBookingInline]


@admin.register(HotelBooking)
class HotelBookingAdmin(SimpleHistoryAdmin):
    list_display  = (
        "hotel_name", "travel_booking", "check_in", "check_out",
        "room_type", "hotel_cost",
    )
    search_fields = ("hotel_name", "confirmation_number")


@admin.register(EmployeeAdvance)
class EmployeeAdvanceAdmin(SimpleHistoryAdmin):
    list_display  = (
        "employee", "travel_request", "amount",
        "status", "disbursed_on", "pending_amount",
    )
    list_filter   = ("status",)
    search_fields = ("employee__employee_first_name", "employee__employee_last_name")
    readonly_fields = ("pending_amount",)


@admin.register(ExpenseClaim)
class ExpenseClaimAdmin(SimpleHistoryAdmin):
    list_display  = (
        "employee", "claim_date", "total_claimed",
        "total_approved", "advance_adjusted", "status",
    )
    list_filter   = ("status",)
    search_fields = ("employee__employee_first_name", "employee__employee_last_name")
    readonly_fields = ("net_payable",)
    inlines       = [ExpenseClaimDetailInline]


@admin.register(ExpenseClaimDetail)
class ExpenseClaimDetailAdmin(admin.ModelAdmin):
    list_display  = (
        "expense_claim", "expense_date", "expense_type",
        "amount_claimed", "amount_approved", "billable",
    )
    list_filter   = ("expense_type", "billable")


@admin.register(TravelInvoice)
class TravelInvoiceAdmin(SimpleHistoryAdmin):
    list_display  = (
        "invoice_number", "vendor", "travel_booking",
        "invoice_amount", "gst_amount", "status",
        "payment_voucher_no", "agent_acknowledged",
    )
    list_filter   = ("status", "agent_acknowledged", "reconciliation_month")
    search_fields = ("invoice_number", "vendor", "payment_voucher_no")
    readonly_fields = ("net_payable",)
    date_hierarchy = "invoice_date"
