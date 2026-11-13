"""
travel/filters.py
─────────────────
django-filter FilterSet classes for Travel & Expense module.
Used by list views to allow server-side filtering via GET params.
"""

import django_filters
from django import forms
from django.utils.translation import gettext_lazy as _

from base.filters import FilterSet
from employee.models import Employee

from travel.models import (
    ExpenseClaim,
    TravelBooking,
    TravelInvoice,
    TravelRequest,
)


class TravelRequestFilter(FilterSet):
    """Filter for the travel request list — HR / Manager view."""

    employee = django_filters.ModelChoiceFilter(
        queryset=Employee.objects.filter(is_active=True),
        label=_("Employee"),
        widget=forms.Select(attrs={"class": "oh-select oh-select-2 w-100"}),
    )
    travel_type = django_filters.ChoiceFilter(
        choices=[("", _("All")), ("domestic", _("Domestic")), ("international", _("International"))],
        label=_("Travel Type"),
        widget=forms.Select(attrs={"class": "oh-select w-100"}),
    )
    status = django_filters.MultipleChoiceFilter(
        choices=TravelRequest.STATUS,
        label=_("Status"),
        widget=forms.CheckboxSelectMultiple(),
    )
    departure_date__gte = django_filters.DateFilter(
        field_name="departure_date",
        lookup_expr="gte",
        label=_("Departure From"),
        widget=forms.DateInput(attrs={"type": "date", "class": "oh-input w-100"}),
    )
    departure_date__lte = django_filters.DateFilter(
        field_name="departure_date",
        lookup_expr="lte",
        label=_("Departure To"),
        widget=forms.DateInput(attrs={"type": "date", "class": "oh-input w-100"}),
    )
    travel_to = django_filters.CharFilter(
        lookup_expr="icontains",
        label=_("Destination"),
        widget=forms.TextInput(attrs={"class": "oh-input w-100", "placeholder": _("Search destination")}),
    )
    department = django_filters.CharFilter(
        lookup_expr="icontains",
        label=_("Department"),
        widget=forms.TextInput(attrs={"class": "oh-input w-100"}),
    )

    class Meta:
        model  = TravelRequest
        fields = [
            "employee", "travel_type", "status",
            "departure_date__gte", "departure_date__lte",
            "travel_to", "department",
        ]


class ExpenseClaimFilter(FilterSet):
    """Filter for expense claim list view."""

    employee = django_filters.ModelChoiceFilter(
        queryset=Employee.objects.filter(is_active=True),
        label=_("Employee"),
        widget=forms.Select(attrs={"class": "oh-select oh-select-2 w-100"}),
    )
    status = django_filters.MultipleChoiceFilter(
        choices=ExpenseClaim.STATUS,
        label=_("Status"),
        widget=forms.CheckboxSelectMultiple(),
    )
    claim_date__gte = django_filters.DateFilter(
        field_name="claim_date",
        lookup_expr="gte",
        label=_("Claim Date From"),
        widget=forms.DateInput(attrs={"type": "date", "class": "oh-input w-100"}),
    )
    claim_date__lte = django_filters.DateFilter(
        field_name="claim_date",
        lookup_expr="lte",
        label=_("Claim Date To"),
        widget=forms.DateInput(attrs={"type": "date", "class": "oh-input w-100"}),
    )

    class Meta:
        model  = ExpenseClaim
        fields = ["employee", "status", "claim_date__gte", "claim_date__lte"]


class TravelBookingFilter(FilterSet):
    """Filter for travel desk booking list."""

    vendor = django_filters.CharFilter(
        lookup_expr="icontains",
        label=_("Vendor"),
        widget=forms.TextInput(attrs={"class": "oh-input w-100"}),
    )
    pnr = django_filters.CharFilter(
        lookup_expr="icontains",
        label=_("PNR"),
        widget=forms.TextInput(attrs={"class": "oh-input w-100"}),
    )
    booked_on__gte = django_filters.DateFilter(
        field_name="booked_on",
        lookup_expr="gte",
        label=_("Booked From"),
        widget=forms.DateInput(attrs={"type": "date", "class": "oh-input w-100"}),
    )
    booked_on__lte = django_filters.DateFilter(
        field_name="booked_on",
        lookup_expr="lte",
        label=_("Booked To"),
        widget=forms.DateInput(attrs={"type": "date", "class": "oh-input w-100"}),
    )

    class Meta:
        model  = TravelBooking
        fields = ["vendor", "pnr", "booked_on__gte", "booked_on__lte"]


class TravelInvoiceFilter(FilterSet):
    """Filter for Finance invoice list."""

    vendor = django_filters.CharFilter(
        lookup_expr="icontains",
        label=_("Vendor"),
        widget=forms.TextInput(attrs={"class": "oh-input w-100"}),
    )
    status = django_filters.MultipleChoiceFilter(
        choices=TravelInvoice.STATUS,
        label=_("Status"),
        widget=forms.CheckboxSelectMultiple(),
    )
    reconciliation_month = django_filters.CharFilter(
        lookup_expr="icontains",
        label=_("Month (YYYY-MM)"),
        widget=forms.TextInput(attrs={"class": "oh-input w-100", "placeholder": "2025-06"}),
    )
    agent_acknowledged = django_filters.BooleanFilter(
        label=_("Agent Acknowledged"),
        widget=forms.CheckboxInput(),
    )

    class Meta:
        model  = TravelInvoice
        fields = ["vendor", "status", "reconciliation_month", "agent_acknowledged"]
