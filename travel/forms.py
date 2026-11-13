"""
travel/forms.py
───────────────
Django ModelForms for Travel & Expense module.

Forms:
  • TravelRequestForm        — employee creates / edits a travel request
  • TravelRequestApproveForm — HR / Manager action (approve / reject / hold)
  • TravelBookingForm        — travel desk fills PNR, ticket, vendor details
  • HotelBookingForm         — travel desk adds hotel booking
  • EmployeeAdvanceForm      — finance issues / updates advance
  • ExpenseClaimForm         — employee submits expense claim header
  • ExpenseClaimDetailForm   — individual expense line item
  • TravelInvoiceForm        — finance records vendor invoice
  • PurposeOfTravelForm      — HR admin creates / edits purposes
  • TravelEntitlementForm    — HR admin configures entitlements
"""

from django import forms
from django.utils.translation import gettext_lazy as _

from horilla_widgets.forms import HorillaModelForm

from travel.models import (
    EmployeeAdvance,
    ExpenseClaim,
    ExpenseClaimDetail,
    HotelBooking,
    PurposeOfTravel,
    TravelBooking,
    TravelEntitlement,
    TravelInvoice,
    TravelRequest,
)


# ── Travel Request ────────────────────────────────────────────────────────────

class TravelRequestForm(HorillaModelForm):
    """Employee-facing form for creating or editing a travel request."""

    class Meta:
        model   = TravelRequest
        exclude = [
            # Auto-filled on save
            "employee_name", "department", "designation", "contact_number",
            # Set by workflow, not employee
            "status", "rejection_reason", "approval_mail_proof",
            # Horilla base fields
            "created_by", "modified_by", "is_active",
        ]
        widgets = {
            "departure_date": forms.DateTimeInput(
                attrs={"type": "datetime-local", "class": "oh-input w-100"},
                format="%Y-%m-%dT%H:%M",
            ),
            "return_date": forms.DateTimeInput(
                attrs={"type": "datetime-local", "class": "oh-input w-100"},
                format="%Y-%m-%dT%H:%M",
            ),
            "check_in_date": forms.DateInput(
                attrs={"type": "date", "class": "oh-input w-100"},
            ),
            "check_out_date": forms.DateInput(
                attrs={"type": "date", "class": "oh-input w-100"},
            ),
            "description": forms.Textarea(attrs={"rows": 3, "class": "oh-input w-100"}),
            "travel_from":  forms.TextInput(attrs={"class": "oh-input w-100"}),
            "travel_to":    forms.TextInput(attrs={"class": "oh-input w-100"}),
        }

    def __init__(self, *args, **kwargs):
        self.request = kwargs.pop("request", None)
        super().__init__(*args, **kwargs)
        # Restrict employee field to current user unless HR
        if self.request and not self.request.user.has_perm("travel.view_all_travelrequest"):
            try:
                from employee.models import Employee
                emp = Employee.objects.get(employee_user_id=self.request.user)
                self.fields["employee"].initial   = emp
                self.fields["employee"].queryset  = Employee.objects.filter(pk=emp.pk)
                self.fields["employee"].disabled  = True
            except Exception:
                pass

        # Mark international-only field as not required by default
        self.fields["passport_number"].required = False

    def clean(self):
        cleaned = super().clean()
        travel_type = cleaned.get("travel_type")
        passport    = cleaned.get("passport_number")
        if travel_type == "international" and not passport:
            self.add_error(
                "passport_number",
                _("Passport number is required for international travel."),
            )
        advance_required = cleaned.get("advance_required")
        advance_amount   = cleaned.get("advance_amount", 0)
        if advance_required and (not advance_amount or advance_amount <= 0):
            self.add_error(
                "advance_amount",
                _("Enter the advance amount required."),
            )
        # Bug fix: departure must be before return date
        departure = cleaned.get("departure_date")
        return_dt = cleaned.get("return_date")
        if departure and return_dt and departure >= return_dt:
            self.add_error(
                "return_date",
                _("Return date/time must be after the departure date/time."),
            )
        return cleaned


class TravelRequestApproveForm(forms.Form):
    """
    Minimal form used when HR / Manager takes action on a pending request.
    The view handles the status transition; this just captures remarks.
    """
    ACTION_CHOICES = [
        ("approve", _("Approve")),
        ("reject",  _("Reject")),
        ("hold",    _("Hold / Follow-up")),
    ]
    action  = forms.ChoiceField(choices=ACTION_CHOICES, label=_("Action"))
    remarks = forms.CharField(
        widget=forms.Textarea(attrs={"rows": 3, "class": "oh-input w-100"}),
        required=False,
        label=_("Remarks"),
    )

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("action") == "reject" and not cleaned.get("remarks"):
            self.add_error("remarks", _("Remarks are required when rejecting a request."))
        return cleaned


# ── Travel Booking ────────────────────────────────────────────────────────────

class TravelBookingForm(HorillaModelForm):
    class Meta:
        model   = TravelBooking
        exclude = ["created_by", "modified_by", "is_active", "booked_on"]
        widgets = {
            "notes": forms.Textarea(attrs={"rows": 3, "class": "oh-input w-100"}),
            "pnr":   forms.TextInput(attrs={"class": "oh-input w-100", "placeholder": "PNR123456"}),
        }


class HotelBookingForm(HorillaModelForm):
    class Meta:
        model   = HotelBooking
        exclude = ["created_by", "modified_by", "is_active"]
        widgets = {
            "check_in":  forms.DateInput(attrs={"type": "date", "class": "oh-input w-100"}),
            "check_out": forms.DateInput(attrs={"type": "date", "class": "oh-input w-100"}),
            "hotel_address": forms.Textarea(attrs={"rows": 2, "class": "oh-input w-100"}),
        }


# ── Employee Advance ──────────────────────────────────────────────────────────

class EmployeeAdvanceForm(HorillaModelForm):
    class Meta:
        model   = EmployeeAdvance
        exclude = ["created_by", "modified_by", "is_active", "claimed_amount", "returned_amount"]
        widgets = {
            "disbursed_on": forms.DateInput(attrs={"type": "date", "class": "oh-input w-100"}),
            "purpose":      forms.TextInput(attrs={"class": "oh-input w-100"}),
        }


# ── Expense Claim ─────────────────────────────────────────────────────────────

class ExpenseClaimForm(HorillaModelForm):
    class Meta:
        model   = ExpenseClaim
        exclude = [
            "total_claimed", "advance_adjusted",
            "approved_by", "created_by", "modified_by", "is_active",
        ]
        widgets = {
            "claim_date": forms.DateInput(attrs={"type": "date", "class": "oh-input w-100"}),
            "remarks":    forms.Textarea(attrs={"rows": 3, "class": "oh-input w-100"}),
        }

    def __init__(self, *args, **kwargs):
        self.request = kwargs.pop("request", None)
        super().__init__(*args, **kwargs)
        if self.request and not self.request.user.has_perm("travel.view_all_travelrequest"):
            try:
                from employee.models import Employee
                emp = Employee.objects.get(employee_user_id=self.request.user)
                self.fields["employee"].initial  = emp
                self.fields["employee"].queryset = Employee.objects.filter(pk=emp.pk)
                self.fields["employee"].disabled = True
                # Restrict travel_request to this employee's completed requests
                self.fields["travel_request"].queryset = (
                    emp.travel_requests.filter(status__in=("approved", "booked", "completed"))
                )
            except Exception:
                pass


class ExpenseClaimDetailForm(forms.ModelForm):
    class Meta:
        model  = ExpenseClaimDetail
        fields = [
            "expense_date", "expense_type", "description",
            "amount_claimed", "receipt", "billable",
        ]
        widgets = {
            "expense_date": forms.DateInput(attrs={"type": "date", "class": "oh-input w-100"}),
            "description":  forms.TextInput(attrs={"class": "oh-input w-100"}),
        }


ExpenseClaimDetailFormSet = forms.inlineformset_factory(
    ExpenseClaim,
    ExpenseClaimDetail,
    form=ExpenseClaimDetailForm,
    extra=3,
    can_delete=True,
)


# ── Travel Invoice ────────────────────────────────────────────────────────────

class TravelInvoiceForm(HorillaModelForm):
    class Meta:
        model   = TravelInvoice
        exclude = ["created_by", "modified_by", "is_active"]
        widgets = {
            "invoice_date": forms.DateInput(attrs={"type": "date", "class": "oh-input w-100"}),
            "payment_date": forms.DateInput(attrs={"type": "date", "class": "oh-input w-100"}),
            "notes":        forms.Textarea(attrs={"rows": 3, "class": "oh-input w-100"}),
        }


# ── Admin / Configuration Forms ───────────────────────────────────────────────

class PurposeOfTravelForm(HorillaModelForm):
    class Meta:
        model   = PurposeOfTravel
        exclude = ["created_by", "modified_by", "is_active", "company_id"]
        widgets = {
            "description": forms.Textarea(attrs={"rows": 2, "class": "oh-input w-100"}),
            "name":        forms.TextInput(attrs={"class": "oh-input w-100"}),
        }


class TravelEntitlementForm(HorillaModelForm):
    class Meta:
        model   = TravelEntitlement
        exclude = ["created_by", "modified_by", "is_active", "company_id"]
        widgets = {
            "max_advance": forms.NumberInput(attrs={"class": "oh-input w-100", "step": "0.01"}),
        }
