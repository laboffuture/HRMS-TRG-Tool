"""
travel/views/travel_views.py
────────────────────────────
Views for:
  • Dashboard
  • Travel Request CRUD (create, list, detail, update, delete)
  • My Requests (self-service)
  • Pending Approvals (HR / Manager / HOD)
  • Approval action (approve / reject / hold)
  • Travel Booking (travel desk)
  • Hotel Booking
  • Employee Advance
  • Config (Purposes, Entitlements)
  • Booking List (travel desk)
  • Invoice List (finance)
"""

from datetime import date

from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.db.models import Count, Q, Sum
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from employee.models import Employee

from travel.filters import TravelBookingFilter, TravelInvoiceFilter, TravelRequestFilter
from travel.forms import (
    EmployeeAdvanceForm,
    HotelBookingForm,
    PurposeOfTravelForm,
    TravelBookingForm,
    TravelEntitlementForm,
    TravelRequestApproveForm,
    TravelRequestForm,
    TravelInvoiceForm,
)
from travel.models import (
    EmployeeAdvance,
    HotelBooking,
    PurposeOfTravel,
    TravelApproval,
    TravelBooking,
    TravelEntitlement,
    TravelInvoice,
    TravelItinerary,
    TravelRequest,
)


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _get_employee(request):
    """Return Employee for logged-in user, or None."""
    try:
        return Employee.objects.get(employee_user_id=request.user)
    except Employee.DoesNotExist:
        return None


# ─────────────────────────────────────────────────────────────────────────────
# Dashboard
# ─────────────────────────────────────────────────────────────────────────────

@login_required
def travel_dashboard(request):
    """
    Travel module home. Shows:
    - My in-flight requests
    - Pending-approval count (for managers)
    - Quick stats
    """
    employee = _get_employee(request)
    ctx = {
        "title": _("Travel Dashboard"),
        "my_requests": [],
        "pending_approvals_count": 0,
        "stats": {},
    }

    if employee:
        ctx["my_requests"] = TravelRequest.objects.filter(
            employee=employee,
            status__in=("draft", "pending_hr", "pending_manager", "pending_hod", "approved", "booked"),
        ).order_by("-created_at")[:5]

    # Approval counts for managers
    can_validate = request.user.has_perm("travel.validate_travelrequest")
    can_approve  = request.user.has_perm("travel.approve_travelrequest")
    if can_validate:
        ctx["pending_approvals_count"] += TravelRequest.objects.filter(
            status="pending_hr"
        ).count()
    if can_approve:
        ctx["pending_approvals_count"] += TravelRequest.objects.filter(
            status__in=("pending_manager", "pending_hod")
        ).count()

    # High-level stats (visible only to HR/managers)
    if request.user.has_perm("travel.view_all_travelrequest"):
        today = date.today()
        ctx["stats"] = {
            "total_this_month": TravelRequest.objects.filter(
                created_at__year=today.year,
                created_at__month=today.month,
            ).count(),
            "pending_count": TravelRequest.objects.filter(
                status__in=("pending_hr", "pending_manager", "pending_hod")
            ).count(),
            "booked_count": TravelRequest.objects.filter(status="booked").count(),
            "completed_count": TravelRequest.objects.filter(status="completed").count(),
        }

    return render(request, "travel/dashboard.html", ctx)


# ─────────────────────────────────────────────────────────────────────────────
# Travel Request — List
# ─────────────────────────────────────────────────────────────────────────────

@login_required
def travel_request_list(request):
    """All travel requests — requires view_all_travelrequest permission."""
    if not request.user.has_perm("travel.view_all_travelrequest"):
        messages.error(request, _("You do not have permission to view all travel requests."))
        return redirect("travel-dashboard")

    qs = TravelRequest.objects.select_related("employee", "purpose").order_by("-created_at")
    f  = TravelRequestFilter(request.GET, queryset=qs)
    return render(request, "travel/request_list.html", {
        "title":   _("All Travel Requests"),
        "filter":  f,
        "requests": f.qs,
    })


@login_required
def travel_my_requests(request):
    """Self-service — employee sees only their own requests."""
    employee = _get_employee(request)
    if not employee:
        messages.warning(request, _("No employee record found for your account."))
        return redirect("travel-dashboard")

    qs = TravelRequest.objects.filter(employee=employee).order_by("-created_at")
    return render(request, "travel/request_list.html", {
        "title":    _("My Travel Requests"),
        "requests": qs,
        "my_view":  True,
    })


# ─────────────────────────────────────────────────────────────────────────────
# Travel Request — Create / Edit
# ─────────────────────────────────────────────────────────────────────────────

@login_required
def travel_request_create(request):
    """Employee submits a new travel request."""
    if request.method == "POST":
        form = TravelRequestForm(request.POST, request.FILES, request=request)
        if form.is_valid():
            travel_request = form.save(commit=False)
            travel_request.save()
            messages.success(request, _("Travel request submitted successfully."))
            return redirect("travel-request-detail", pk=travel_request.pk)
    else:
        form = TravelRequestForm(request=request)

    return render(request, "travel/request_form.html", {
        "title": _("New Travel Request"),
        "form":  form,
    })


@login_required
def travel_request_update(request, pk):
    """Edit a draft travel request."""
    travel_request = get_object_or_404(TravelRequest, pk=pk)

    # Only the owner (or HR) can edit; only draft requests can be edited
    employee = _get_employee(request)
    is_owner = employee and travel_request.employee_id == employee.pk
    is_hr    = request.user.has_perm("travel.validate_travelrequest")

    if not (is_owner or is_hr):
        messages.error(request, _("You cannot edit this request."))
        return redirect("travel-request-detail", pk=pk)

    if travel_request.status != "draft" and not is_hr:
        messages.error(request, _("Only draft requests can be edited."))
        return redirect("travel-request-detail", pk=pk)

    if request.method == "POST":
        form = TravelRequestForm(request.POST, request.FILES, instance=travel_request, request=request)
        if form.is_valid():
            form.save()
            messages.success(request, _("Travel request updated."))
            return redirect("travel-request-detail", pk=pk)
    else:
        form = TravelRequestForm(instance=travel_request, request=request)

    return render(request, "travel/request_form.html", {
        "title":          _("Edit Travel Request"),
        "form":           form,
        "travel_request": travel_request,
    })


@login_required
def travel_request_delete(request, pk):
    """Delete a draft request (own or HR)."""
    travel_request = get_object_or_404(TravelRequest, pk=pk)
    employee = _get_employee(request)
    is_owner = employee and travel_request.employee_id == employee.pk
    is_hr    = request.user.has_perm("travel.validate_travelrequest")

    if not (is_owner or is_hr):
        messages.error(request, _("Permission denied."))
        return redirect("travel-request-list")

    if travel_request.status != "draft":
        messages.error(request, _("Only draft requests can be deleted."))
        return redirect("travel-request-detail", pk=pk)

    travel_request.delete()
    messages.success(request, _("Travel request deleted."))
    return redirect("travel-my-requests")


# ─────────────────────────────────────────────────────────────────────────────
# Travel Request — Detail
# ─────────────────────────────────────────────────────────────────────────────

@login_required
def travel_request_detail(request, pk):
    """Detail view — shows full request with itinerary, approvals, booking."""
    travel_request = get_object_or_404(
        TravelRequest.objects.select_related("employee", "purpose", "company_id"),
        pk=pk,
    )
    employee = _get_employee(request)
    is_owner = employee and travel_request.employee_id == employee.pk
    can_view_all = request.user.has_perm("travel.view_all_travelrequest")

    if not (is_owner or can_view_all or request.user.is_superuser):
        messages.error(request, _("You do not have permission to view this request."))
        return redirect("travel-dashboard")

    itinerary = travel_request.itinerary.all()
    approvals  = travel_request.approvals.all()
    booking    = getattr(travel_request, "booking", None)
    advances   = travel_request.advances.all()
    claims     = travel_request.expense_claims.all()

    ctx = {
        "title":          f"Travel Request — {travel_request.employee_name}",
        "travel_request": travel_request,
        "itinerary":      itinerary,
        "approvals":      approvals,
        "booking":        booking,
        "advances":       advances,
        "claims":         claims,
        "can_validate":   request.user.has_perm("travel.validate_travelrequest"),
        "can_approve":    request.user.has_perm("travel.approve_travelrequest"),
        "can_book":       request.user.has_perm("travel.book_travelrequest"),
        "is_owner":       is_owner,
    }
    return render(request, "travel/request_detail.html", ctx)


# ─────────────────────────────────────────────────────────────────────────────
# Submit / Withdraw actions (employee self-service)
# ─────────────────────────────────────────────────────────────────────────────

@login_required
def travel_request_submit(request, pk):
    """Employee submits a draft request for HR validation."""
    travel_request = get_object_or_404(TravelRequest, pk=pk)
    employee = _get_employee(request)

    if not (employee and travel_request.employee_id == employee.pk):
        messages.error(request, _("Permission denied."))
        return redirect("travel-dashboard")

    if travel_request.status != "draft":
        messages.error(request, _("Only draft requests can be submitted."))
        return redirect("travel-request-detail", pk=pk)

    travel_request.status = "pending_hr"
    travel_request.save(update_fields=["status"])
    messages.success(request, _("Request submitted for HR review."))
    return redirect("travel-request-detail", pk=pk)


@login_required
def travel_request_cancel(request, pk):
    """Employee or HR cancels a request."""
    travel_request = get_object_or_404(TravelRequest, pk=pk)
    employee = _get_employee(request)
    is_owner = employee and travel_request.employee_id == employee.pk
    is_hr    = request.user.has_perm("travel.validate_travelrequest")

    if not (is_owner or is_hr):
        messages.error(request, _("Permission denied."))
        return redirect("travel-request-detail", pk=pk)

    if travel_request.status in ("completed", "cancelled", "rejected"):
        messages.error(request, _("Cannot cancel a request in this state."))
        return redirect("travel-request-detail", pk=pk)

    travel_request.status = "cancelled"
    travel_request.save(update_fields=["status"])
    messages.success(request, _("Travel request cancelled."))
    return redirect("travel-my-requests" if is_owner else "travel-request-list")


# ─────────────────────────────────────────────────────────────────────────────
# Pending Approvals
# ─────────────────────────────────────────────────────────────────────────────

@login_required
def travel_pending_approvals(request):
    """
    Shows requests waiting for this user's action:
    - HR sees pending_hr
    - Managers see pending_manager
    - HOD sees pending_hod
    """
    can_validate = request.user.has_perm("travel.validate_travelrequest")
    can_approve  = request.user.has_perm("travel.approve_travelrequest")

    if not (can_validate or can_approve):
        messages.error(request, _("You do not have approval permissions."))
        return redirect("travel-dashboard")

    status_filter = []
    if can_validate:
        status_filter.append("pending_hr")
    if can_approve:
        status_filter.extend(["pending_manager", "pending_hod"])

    qs = TravelRequest.objects.filter(
        status__in=status_filter
    ).select_related("employee", "purpose").order_by("departure_date")

    return render(request, "travel/pending_approvals.html", {
        "title":    _("Pending Approvals"),
        "requests": qs,
    })


@login_required
def travel_request_approve_action(request, pk):
    """
    HR / Manager / HOD takes an action (approve / reject / hold) on a request.
    Drives the status machine forward.
    """
    travel_request = get_object_or_404(TravelRequest, pk=pk)
    can_validate = request.user.has_perm("travel.validate_travelrequest")
    can_approve  = request.user.has_perm("travel.approve_travelrequest")

    if not (can_validate or can_approve):
        messages.error(request, _("Permission denied."))
        return redirect("travel-request-detail", pk=pk)

    # Determine level
    if travel_request.status == "pending_hr" and can_validate:
        level = "hr"
    elif travel_request.status == "pending_manager" and can_approve:
        level = "manager"
    elif travel_request.status == "pending_hod" and can_approve:
        level = "hod"
    else:
        messages.error(request, _("No pending action at your level for this request."))
        return redirect("travel-request-detail", pk=pk)

    if request.method == "POST":
        form = TravelRequestApproveForm(request.POST)
        if form.is_valid():
            action  = form.cleaned_data["action"]
            remarks = form.cleaned_data.get("remarks", "")
            employee = _get_employee(request)

            # Update approval trail
            # NB: do not unpack into "_" — that shadows gettext for the whole
            # function and makes every _("...") call in this view crash.
            approval, _created = TravelApproval.objects.get_or_create(
                travel_request=travel_request,
                level=level,
                defaults={"approver": employee},
            )
            approval.approver   = employee
            approval.remarks    = remarks
            approval.actioned_at = timezone.now()

            # Drive status machine
            if action == "approve":
                approval.status = "approved"
                if level == "hr":
                    travel_request.status = "pending_manager"
                elif level == "manager":
                    travel_request.status = "pending_hod"
                elif level == "hod":
                    travel_request.status = "approved"
                msg = _("Request approved and forwarded.")
            elif action == "reject":
                approval.status = "rejected"
                travel_request.status      = "rejected"
                travel_request.rejection_reason = remarks
                msg = _("Request rejected.")
            else:  # hold
                approval.status = "hold"
                msg = _("Request placed on hold.")

            approval.save()
            travel_request.save(update_fields=["status", "rejection_reason"])
            messages.success(request, msg)
            return redirect("travel-pending-approvals")
    else:
        form = TravelRequestApproveForm()

    return render(request, "travel/approve_action.html", {
        "title":          _("Review Travel Request"),
        "form":           form,
        "travel_request": travel_request,
        "level":          level,
    })


# ─────────────────────────────────────────────────────────────────────────────
# Travel Booking (Travel Desk)
# ─────────────────────────────────────────────────────────────────────────────

@login_required
def travel_booking_list(request):
    """Travel desk view — all approved/booked requests."""
    if not request.user.has_perm("travel.book_travelrequest"):
        messages.error(request, _("Permission denied."))
        return redirect("travel-dashboard")

    qs = TravelBooking.objects.select_related(
        "travel_request__employee", "booked_by"
    ).order_by("-booked_on")
    f  = TravelBookingFilter(request.GET, queryset=qs)

    # Also show approved (unbooked) requests
    unbooked = TravelRequest.objects.filter(status="approved").select_related("employee")

    return render(request, "travel/booking_list.html", {
        "title":    _("Travel Bookings"),
        "filter":   f,
        "bookings": f.qs,
        "unbooked": unbooked,
    })


@login_required
def travel_booking_create(request, request_pk):
    """Travel desk books a ticket for an approved request."""
    if not request.user.has_perm("travel.book_travelrequest"):
        messages.error(request, _("Permission denied."))
        return redirect("travel-dashboard")

    travel_request = get_object_or_404(TravelRequest, pk=request_pk, status="approved")

    if hasattr(travel_request, "booking"):
        messages.warning(request, _("This request is already booked."))
        return redirect("travel-booking-detail", pk=travel_request.booking.pk)

    if request.method == "POST":
        form = TravelBookingForm(request.POST, request.FILES)
        if form.is_valid():
            booking = form.save(commit=False)
            booking.travel_request = travel_request  # always set from URL, not form
            booking.booked_on      = timezone.now()
            booking.booked_by      = _get_employee(request)
            booking.save()
            messages.success(request, _("Booking created. PNR recorded."))
            return redirect("travel-booking-detail", pk=booking.pk)
    else:
        form = TravelBookingForm()
        # Remove travel_request from form — it's set automatically from the URL
        form.fields.pop("travel_request", None)

    return render(request, "travel/booking_form.html", {
        "title":          _("Create Booking"),
        "form":           form,
        "travel_request": travel_request,
    })


@login_required
def travel_booking_detail(request, pk):
    """Detail view for a travel booking — includes hotel bookings."""
    booking = get_object_or_404(
        TravelBooking.objects.select_related("travel_request__employee", "booked_by"),
        pk=pk,
    )
    if not (
        request.user.has_perm("travel.book_travelrequest")
        or request.user.has_perm("travel.view_all_travelrequest")
    ):
        messages.error(request, _("Permission denied."))
        return redirect("travel-dashboard")

    hotel_form = HotelBookingForm(initial={"travel_booking": booking})
    if request.method == "POST":
        hotel_form = HotelBookingForm(request.POST, request.FILES)
        if hotel_form.is_valid():
            hotel = hotel_form.save(commit=False)
            hotel.travel_booking = booking
            hotel.save()
            messages.success(request, _("Hotel booking added."))
            return redirect("travel-booking-detail", pk=pk)

    return render(request, "travel/booking_detail.html", {
        "title":      _("Booking Detail"),
        "booking":    booking,
        "hotels":     booking.hotel_bookings.all(),
        "hotel_form": hotel_form,
        "invoices":   booking.invoices.all(),
    })


@login_required
def travel_booking_update(request, pk):
    """Travel desk edits an existing booking."""
    if not request.user.has_perm("travel.book_travelrequest"):
        messages.error(request, _("Permission denied."))
        return redirect("travel-dashboard")

    booking = get_object_or_404(TravelBooking, pk=pk)
    if request.method == "POST":
        form = TravelBookingForm(request.POST, request.FILES, instance=booking)
        if form.is_valid():
            form.save()
            messages.success(request, _("Booking updated."))
            return redirect("travel-booking-detail", pk=pk)
    else:
        form = TravelBookingForm(instance=booking)

    return render(request, "travel/booking_form.html", {
        "title":   _("Edit Booking"),
        "form":    form,
        "booking": booking,
    })


# ─────────────────────────────────────────────────────────────────────────────
# Employee Advance
# ─────────────────────────────────────────────────────────────────────────────

@login_required
def travel_advance_create(request, request_pk):
    """Finance creates an advance for a travel request."""
    travel_request = get_object_or_404(TravelRequest, pk=request_pk)

    if request.method == "POST":
        form = EmployeeAdvanceForm(request.POST)
        if form.is_valid():
            advance = form.save(commit=False)
            advance.travel_request = travel_request
            if not advance.employee_id:
                advance.employee = travel_request.employee
            advance.save()
            messages.success(request, _("Advance record created."))
            return redirect("travel-request-detail", pk=request_pk)
    else:
        form = EmployeeAdvanceForm(initial={
            "travel_request": travel_request,
            "employee":       travel_request.employee,
            "amount":         travel_request.advance_amount,
        })

    return render(request, "travel/advance_form.html", {
        "title":          _("Create Employee Advance"),
        "form":           form,
        "travel_request": travel_request,
    })


@login_required
def travel_advance_update(request, pk):
    """Update advance status (paid, adjusted, returned)."""
    advance = get_object_or_404(EmployeeAdvance, pk=pk)

    if request.method == "POST":
        form = EmployeeAdvanceForm(request.POST, instance=advance)
        if form.is_valid():
            form.save()
            messages.success(request, _("Advance updated."))
            return redirect("travel-request-detail", pk=advance.travel_request_id)
    else:
        form = EmployeeAdvanceForm(instance=advance)

    return render(request, "travel/advance_form.html", {
        "title":   _("Update Advance"),
        "form":    form,
        "advance": advance,
    })


# ─────────────────────────────────────────────────────────────────────────────
# Purposes of Travel (Admin config)
# ─────────────────────────────────────────────────────────────────────────────

@login_required
@permission_required("travel.add_purposeoftravel", raise_exception=True)
def travel_purpose_list(request):
    purposes = PurposeOfTravel.objects.all()
    form     = PurposeOfTravelForm()
    if request.method == "POST":
        form = PurposeOfTravelForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, _("Purpose added."))
            return redirect("travel-purpose-list")
    return render(request, "travel/purpose_list.html", {
        "title":    _("Purposes of Travel"),
        "purposes": purposes,
        "form":     form,
    })


@login_required
@permission_required("travel.change_purposeoftravel", raise_exception=True)
def travel_purpose_delete(request, pk):
    purpose = get_object_or_404(PurposeOfTravel, pk=pk)
    purpose.delete()
    messages.success(request, _("Purpose deleted."))
    return redirect("travel-purpose-list")


# ─────────────────────────────────────────────────────────────────────────────
# Travel Entitlements (Admin config)
# ─────────────────────────────────────────────────────────────────────────────

@login_required
@permission_required("travel.add_travelentitlement", raise_exception=True)
def travel_entitlement_list(request):
    entitlements = TravelEntitlement.objects.select_related("job_role").all()
    form         = TravelEntitlementForm()
    if request.method == "POST":
        form = TravelEntitlementForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, _("Entitlement saved."))
            return redirect("travel-entitlement-list")
    return render(request, "travel/entitlement_list.html", {
        "title":        _("Travel Entitlements"),
        "entitlements": entitlements,
        "form":         form,
    })


@login_required
@permission_required("travel.change_travelentitlement", raise_exception=True)
def travel_entitlement_update(request, pk):
    entitlement = get_object_or_404(TravelEntitlement, pk=pk)
    if request.method == "POST":
        form = TravelEntitlementForm(request.POST, instance=entitlement)
        if form.is_valid():
            form.save()
            messages.success(request, _("Entitlement updated."))
            return redirect("travel-entitlement-list")
    else:
        form = TravelEntitlementForm(instance=entitlement)
    return render(request, "travel/entitlement_form.html", {
        "title": _("Edit Entitlement"),
        "form":  form,
    })


# ─────────────────────────────────────────────────────────────────────────────
# Travel Invoice (Finance)
# ─────────────────────────────────────────────────────────────────────────────

@login_required
def travel_invoice_list(request):
    """Finance team views all vendor invoices."""
    if not (
        request.user.has_perm("travel.add_travelinvoice")
        or request.user.has_perm("travel.view_all_travelrequest")
        or request.user.is_superuser
    ):
        messages.error(request, _("Permission denied."))
        return redirect("travel-dashboard")

    qs = TravelInvoice.objects.select_related(
        "travel_booking__travel_request__employee"
    ).order_by("-invoice_date")
    f  = TravelInvoiceFilter(request.GET, queryset=qs)
    return render(request, "travel/invoice_list.html", {
        "title":    _("Travel Invoices"),
        "filter":   f,
        "invoices": f.qs,
    })


@login_required
@permission_required("travel.add_travelinvoice", raise_exception=True)
def travel_invoice_create(request, booking_pk):
    """Finance records an invoice for a booking."""
    booking = get_object_or_404(TravelBooking, pk=booking_pk)
    if request.method == "POST":
        form = TravelInvoiceForm(request.POST, request.FILES)
        if form.is_valid():
            invoice = form.save(commit=False)
            invoice.travel_booking = booking
            invoice.save()
            messages.success(request, _("Invoice recorded."))
            return redirect("travel-booking-detail", pk=booking_pk)
    else:
        form = TravelInvoiceForm(initial={"travel_booking": booking, "vendor": booking.vendor})

    return render(request, "travel/invoice_form.html", {
        "title":   _("Record Invoice"),
        "form":    form,
        "booking": booking,
    })


@login_required
@permission_required("travel.change_travelinvoice", raise_exception=True)
def travel_invoice_update(request, pk):
    """Finance updates invoice status (verified → PV created → paid → reconciled)."""
    invoice = get_object_or_404(TravelInvoice, pk=pk)
    if request.method == "POST":
        form = TravelInvoiceForm(request.POST, request.FILES, instance=invoice)
        if form.is_valid():
            form.save()
            messages.success(request, _("Invoice updated."))
            return redirect("travel-invoice-list")
    else:
        form = TravelInvoiceForm(instance=invoice)

    return render(request, "travel/invoice_form.html", {
        "title":   _("Update Invoice"),
        "form":    form,
        "invoice": invoice,
    })
