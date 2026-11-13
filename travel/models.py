"""
travel/models.py
────────────────
Travel & Expense module for Horilla HR.

Covers the full LOF ticketing SOP:
  1. PurposeOfTravel      — master list of travel purposes
  2. TravelEntitlement    — job role → Economy / Business class mapping
  3. TravelRequest        — employee travel requisition
  4. TravelItinerary      — legs of the journey (child of TravelRequest)
  5. TravelApproval       — approval trail (HR → Manager → HOD)
  6. TravelBooking        — travel desk fills after approval (PNR, ticket, vendor)
  7. HotelBooking         — hotel details linked to booking
  8. EmployeeAdvance      — cash advance issued to traveller
  9. ExpenseClaim         — post-travel reimbursement request
 10. ExpenseClaimDetail   — line items of expense claim
 11. TravelInvoice        — vendor invoice → Finance payment voucher tracking
"""

from django.core.exceptions import ValidationError
from django.db import models
from django.utils.translation import gettext_lazy as _

from base.horilla_company_manager import HorillaCompanyManager
from base.models import Company
from employee.models import Employee, EmployeeWorkInformation
from horilla.models import HorillaModel, upload_path


# ── 1. Purpose of Travel ──────────────────────────────────────────────────────

class PurposeOfTravel(HorillaModel):
    """Master list — Training, Client Visit, Conference, Audit, etc."""

    name        = models.CharField(max_length=100, unique=True, verbose_name=_("Purpose"))
    description = models.TextField(blank=True, null=True, verbose_name=_("Description"))
    company_id  = models.ManyToManyField(Company, blank=True, verbose_name=_("Company"))

    objects = HorillaCompanyManager()

    class Meta:
        verbose_name          = _("Purpose of Travel")
        verbose_name_plural   = _("Purposes of Travel")
        ordering              = ["name"]

    def __str__(self):
        return self.name


# ── 2. Travel Entitlement ─────────────────────────────────────────────────────

class TravelEntitlement(HorillaModel):
    """
    Maps a job role to a travel class entitlement and advance limit.
    HR admin configures this once; travel requests auto-fill entitlement.
    """

    TRAVEL_CLASS = [
        ("economy",   _("Economy")),
        ("business",  _("Business")),
        ("first",     _("First Class")),
    ]

    job_role      = models.ForeignKey(
        "base.JobRole",
        on_delete=models.CASCADE,
        verbose_name=_("Job Role"),
    )
    travel_class  = models.CharField(
        max_length=20, choices=TRAVEL_CLASS, default="economy",
        verbose_name=_("Travel Class"),
    )
    max_advance   = models.DecimalField(
        max_digits=12, decimal_places=2, default=0,
        verbose_name=_("Max Advance Amount (INR)"),
        help_text=_("Maximum cash advance allowed for this role"),
    )
    domestic_days_notice  = models.PositiveIntegerField(
        default=30, verbose_name=_("Domestic Notice (days)"),
        help_text=_("Minimum days before travel for domestic requests"),
    )
    international_days_notice = models.PositiveIntegerField(
        default=90, verbose_name=_("International Notice (days)"),
        help_text=_("Minimum days before travel for international requests"),
    )
    company_id    = models.ManyToManyField(Company, blank=True, verbose_name=_("Company"))

    objects = HorillaCompanyManager()

    class Meta:
        verbose_name        = _("Travel Entitlement")
        verbose_name_plural = _("Travel Entitlements")
        unique_together     = ("job_role",)

    def __str__(self):
        return f"{self.job_role} → {self.get_travel_class_display()}"


# ── 3. Travel Request ─────────────────────────────────────────────────────────

class TravelRequest(HorillaModel):
    """
    Core model — employee submits this to initiate the travel process.
    Status flows: draft → pending_hr → pending_manager → pending_hod
                → approved → booked → completed
                or → rejected / cancelled at any step.
    """

    STATUS = [
        ("draft",           _("Draft")),
        ("pending_hr",      _("Pending HR Validation")),
        ("pending_manager", _("Pending Manager Approval")),
        ("pending_hod",     _("Pending HOD Approval")),
        ("approved",        _("Approved — Forwarded to Travel Desk")),
        ("booked",          _("Booked — PNR Generated")),
        ("completed",       _("Completed")),
        ("rejected",        _("Rejected")),
        ("cancelled",       _("Cancelled")),
    ]

    TRAVEL_TYPE = [
        ("domestic",      _("Domestic")),
        ("international", _("International")),
    ]

    MODE = [
        ("air",     _("Air")),
        ("rail",    _("Rail")),
        ("surface", _("Surface / Road")),
    ]

    TRAVEL_CLASS = [
        ("economy",  _("Economy")),
        ("business", _("Business")),
        ("first",    _("First Class")),
    ]

    # ── Traveller identity ────────────────────────────────────────────────────
    employee        = models.ForeignKey(
        Employee, on_delete=models.CASCADE,
        related_name="travel_requests", verbose_name=_("Employee"),
    )
    employee_name   = models.CharField(
        max_length=200, blank=True, verbose_name=_("Employee Name"),
        help_text=_("Auto-filled from employee record"),
    )
    department      = models.CharField(
        max_length=200, blank=True, verbose_name=_("Department"),
    )
    designation     = models.CharField(
        max_length=200, blank=True, verbose_name=_("Designation"),
    )
    contact_number  = models.CharField(
        max_length=25, blank=True, verbose_name=_("Contact Number"),
    )
    passport_number = models.CharField(
        max_length=50, blank=True, null=True,
        verbose_name=_("Passport Number"),
        help_text=_("Required for international travel"),
    )

    # ── Trip details ──────────────────────────────────────────────────────────
    travel_type     = models.CharField(
        max_length=20, choices=TRAVEL_TYPE, default="domestic",
        verbose_name=_("Travel Type"),
    )
    purpose         = models.ForeignKey(
        PurposeOfTravel, on_delete=models.PROTECT,
        verbose_name=_("Purpose of Travel"),
    )
    description     = models.TextField(
        blank=True, verbose_name=_("Additional Details"),
    )
    mode_of_travel  = models.CharField(
        max_length=20, choices=MODE, default="air",
        verbose_name=_("Mode of Travel"),
    )
    travel_from     = models.CharField(max_length=200, verbose_name=_("Travelling From"))
    travel_to       = models.CharField(max_length=200, verbose_name=_("Travelling To"))
    departure_date  = models.DateTimeField(verbose_name=_("Departure Date & Time"))
    return_date     = models.DateTimeField(
        null=True, blank=True, verbose_name=_("Expected Return Date & Time"),
    )

    # ── Entitlement (auto-filled from TravelEntitlement) ─────────────────────
    travel_class    = models.CharField(
        max_length=20, choices=TRAVEL_CLASS, default="economy",
        verbose_name=_("Travel Class / Entitlement"),
    )

    # ── Lodging ───────────────────────────────────────────────────────────────
    lodging_required    = models.BooleanField(default=False, verbose_name=_("Lodging Required"))
    preferred_location  = models.CharField(
        max_length=200, blank=True, verbose_name=_("Preferred Area for Hotel"),
    )
    check_in_date   = models.DateField(null=True, blank=True, verbose_name=_("Check-in Date"))
    check_out_date  = models.DateField(null=True, blank=True, verbose_name=_("Check-out Date"))

    # ── Advance ───────────────────────────────────────────────────────────────
    advance_required    = models.BooleanField(default=False, verbose_name=_("Advance Required"))
    advance_amount      = models.DecimalField(
        max_digits=12, decimal_places=2, default=0,
        verbose_name=_("Advance Amount Requested (INR)"),
    )

    # ── Approval tracking ─────────────────────────────────────────────────────
    status              = models.CharField(
        max_length=30, choices=STATUS, default="draft",
        verbose_name=_("Status"),
    )
    rejection_reason    = models.TextField(
        blank=True, verbose_name=_("Rejection / Hold Reason"),
    )
    approval_mail_proof = models.FileField(
        upload_to=upload_path, null=True, blank=True,
        verbose_name=_("Approval Mail / Proof"),
    )

    company_id      = models.ForeignKey(
        Company, on_delete=models.PROTECT, null=True, blank=True,
        verbose_name=_("Company"),
    )

    objects = HorillaCompanyManager("company_id")

    class Meta:
        verbose_name        = _("Travel Request")
        verbose_name_plural = _("Travel Requests")
        ordering            = ["-created_at"]
        permissions         = [
            ("validate_travelrequest",  "Can validate travel requests (HR)"),
            ("approve_travelrequest",   "Can approve travel requests (Manager/HOD)"),
            ("book_travelrequest",      "Can book travel (Travel Desk)"),
            ("view_all_travelrequest",  "Can view all travel requests"),
        ]

    def __str__(self):
        return f"{self.employee_name} → {self.travel_to} ({self.get_status_display()})"

    def save(self, *args, **kwargs):
        # Auto-fill employee info from Horilla employee record
        if self.employee:
            self.employee_name = (
                f"{self.employee.employee_first_name} "
                f"{self.employee.employee_last_name or ''}".strip()
            )
            work_info = getattr(self.employee, "employee_work_info", None)
            if work_info:
                if work_info.department_id:
                    self.department = str(work_info.department_id.department)
                if work_info.job_role_id:
                    self.designation = str(work_info.job_role_id.job_role)
                    # Auto-set travel class from entitlement
                    entitlement = TravelEntitlement.objects.filter(
                        job_role=work_info.job_role_id
                    ).first()
                    if entitlement and not self.travel_class:
                        self.travel_class = entitlement.travel_class
            if self.employee.phone:
                self.contact_number = self.employee.phone
        super().save(*args, **kwargs)

    def clean(self):
        if (
            self.travel_type == "international"
            and not self.passport_number
            and self.status not in ("draft",)
        ):
            raise ValidationError(
                _("Passport number is required for international travel.")
            )
        if self.advance_required and self.advance_amount <= 0:
            raise ValidationError(
                _("Please enter the advance amount required.")
            )


# ── 4. Travel Itinerary ───────────────────────────────────────────────────────

class TravelItinerary(models.Model):
    """
    Individual leg of a journey — child table of TravelRequest.
    One request can have multiple legs (e.g., Chennai → Dubai → Riyadh).
    """

    MODE = [
        ("air",     _("Air")),
        ("rail",    _("Rail")),
        ("surface", _("Surface / Road")),
    ]

    travel_request  = models.ForeignKey(
        TravelRequest, on_delete=models.CASCADE,
        related_name="itinerary", verbose_name=_("Travel Request"),
    )
    travel_from     = models.CharField(max_length=200, verbose_name=_("From"))
    travel_to       = models.CharField(max_length=200, verbose_name=_("To"))
    mode_of_travel  = models.CharField(
        max_length=20, choices=MODE, default="air",
        verbose_name=_("Mode"),
    )
    departure       = models.DateTimeField(verbose_name=_("Departure"))
    arrival         = models.DateTimeField(null=True, blank=True, verbose_name=_("Arrival"))
    lodging_required        = models.BooleanField(default=False, verbose_name=_("Lodging"))
    preferred_hotel_area    = models.CharField(
        max_length=200, blank=True, verbose_name=_("Preferred Hotel Area"),
    )
    check_in        = models.DateField(null=True, blank=True, verbose_name=_("Check-in"))
    check_out       = models.DateField(null=True, blank=True, verbose_name=_("Check-out"))
    estimated_cost  = models.DecimalField(
        max_digits=10, decimal_places=2, default=0,
        verbose_name=_("Estimated Cost (INR)"),
    )

    class Meta:
        verbose_name        = _("Travel Itinerary")
        verbose_name_plural = _("Travel Itineraries")
        ordering            = ["departure"]

    def __str__(self):
        return f"{self.travel_from} → {self.travel_to} on {self.departure.date()}"


# ── 5. Travel Approval ────────────────────────────────────────────────────────

class TravelApproval(models.Model):
    """
    Full approval trail — every level recorded with timestamp and remarks.
    Levels: HR Validation → Manager → HOD → (Management for urgent/exceptions)
    """

    LEVEL = [
        ("hr",         _("HR Validation")),
        ("manager",    _("Reporting Manager")),
        ("hod",        _("HOD")),
        ("management", _("Management")),
    ]

    STATUS = [
        ("pending",  _("Pending")),
        ("approved", _("Approved")),
        ("rejected", _("Rejected")),
        ("hold",     _("Hold / Follow-up")),
    ]

    travel_request  = models.ForeignKey(
        TravelRequest, on_delete=models.CASCADE,
        related_name="approvals", verbose_name=_("Travel Request"),
    )
    level           = models.CharField(
        max_length=20, choices=LEVEL, verbose_name=_("Approval Level"),
    )
    approver        = models.ForeignKey(
        Employee, on_delete=models.SET_NULL, null=True,
        verbose_name=_("Approver"),
    )
    status          = models.CharField(
        max_length=20, choices=STATUS, default="pending",
        verbose_name=_("Status"),
    )
    remarks         = models.TextField(blank=True, verbose_name=_("Remarks"))
    actioned_at     = models.DateTimeField(
        null=True, blank=True, verbose_name=_("Actioned At"),
    )

    class Meta:
        verbose_name        = _("Travel Approval")
        verbose_name_plural = _("Travel Approvals")
        ordering            = ["travel_request", "level"]

    def __str__(self):
        return (
            f"{self.travel_request} | {self.get_level_display()} "
            f"— {self.get_status_display()}"
        )


# ── 6. Travel Booking ─────────────────────────────────────────────────────────

class TravelBooking(HorillaModel):
    """
    Travel Desk fills this after the request is approved.
    Records PNR, ticket number, vendor, cost, e-ticket.
    """

    travel_request  = models.OneToOneField(
        TravelRequest, on_delete=models.CASCADE,
        related_name="booking", verbose_name=_("Travel Request"),
    )
    pnr             = models.CharField(
        max_length=20, blank=True, verbose_name=_("PNR Number"),
        help_text=_("Passenger Name Record — airline reservation number"),
    )
    ticket_number   = models.CharField(
        max_length=50, blank=True, verbose_name=_("Ticket Number"),
    )
    vendor          = models.CharField(
        max_length=200, blank=True, verbose_name=_("Vendor / Agency"),
    )
    vendor_invoice_ref = models.CharField(
        max_length=100, blank=True, verbose_name=_("Vendor Invoice Reference"),
    )
    ticket_cost     = models.DecimalField(
        max_digits=12, decimal_places=2, default=0,
        verbose_name=_("Ticket Cost (INR)"),
    )
    service_charge  = models.DecimalField(
        max_digits=10, decimal_places=2, default=0,
        verbose_name=_("Service Charge (INR)"),
    )
    e_ticket        = models.FileField(
        upload_to=upload_path, null=True, blank=True,
        verbose_name=_("E-Ticket"),
    )
    booked_on       = models.DateTimeField(
        null=True, blank=True, verbose_name=_("Booked On"),
    )
    booked_by       = models.ForeignKey(
        Employee, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="bookings_made", verbose_name=_("Booked By (Travel Desk)"),
    )
    notes           = models.TextField(blank=True, verbose_name=_("Notes"))

    objects = models.Manager()

    class Meta:
        verbose_name        = _("Travel Booking")
        verbose_name_plural = _("Travel Bookings")

    def __str__(self):
        return f"Booking for {self.travel_request} — PNR: {self.pnr or 'Pending'}"

    @property
    def total_cost(self):
        return self.ticket_cost + self.service_charge


# ── 7. Hotel Booking ──────────────────────────────────────────────────────────

class HotelBooking(HorillaModel):
    """Hotel details — linked to a TravelBooking."""

    travel_booking  = models.ForeignKey(
        TravelBooking, on_delete=models.CASCADE,
        related_name="hotel_bookings", verbose_name=_("Travel Booking"),
    )
    hotel_name      = models.CharField(max_length=200, verbose_name=_("Hotel Name"))
    hotel_address   = models.TextField(blank=True, verbose_name=_("Hotel Address"))
    contact_number  = models.CharField(
        max_length=25, blank=True, verbose_name=_("Hotel Contact"),
    )
    confirmation_number = models.CharField(
        max_length=100, blank=True, verbose_name=_("Booking Confirmation Number"),
    )
    check_in        = models.DateField(verbose_name=_("Check-in Date"))
    check_out       = models.DateField(verbose_name=_("Check-out Date"))
    room_type       = models.CharField(
        max_length=100, blank=True, verbose_name=_("Room Type"),
        help_text=_("Standard / Deluxe / Suite — as per entitlement"),
    )
    hotel_cost      = models.DecimalField(
        max_digits=12, decimal_places=2, default=0,
        verbose_name=_("Hotel Cost (INR)"),
    )
    voucher         = models.FileField(
        upload_to=upload_path, null=True, blank=True,
        verbose_name=_("Hotel Voucher"),
    )

    objects = models.Manager()

    class Meta:
        verbose_name        = _("Hotel Booking")
        verbose_name_plural = _("Hotel Bookings")

    def __str__(self):
        return f"{self.hotel_name} ({self.check_in} → {self.check_out})"

    @property
    def nights(self):
        if self.check_in and self.check_out:
            return (self.check_out - self.check_in).days
        return 0


# ── 8. Employee Advance ───────────────────────────────────────────────────────

class EmployeeAdvance(HorillaModel):
    """
    Cash advance issued to employee before travel.
    Finance releases this; post-travel it is adjusted against expense claim.
    """

    STATUS = [
        ("pending",  _("Pending Finance Approval")),
        ("approved", _("Approved")),
        ("paid",     _("Paid / Disbursed")),
        ("adjusted", _("Adjusted Against Expense Claim")),
        ("returned", _("Returned by Employee")),
    ]

    travel_request  = models.ForeignKey(
        TravelRequest, on_delete=models.CASCADE,
        related_name="advances", verbose_name=_("Travel Request"),
    )
    employee        = models.ForeignKey(
        Employee, on_delete=models.CASCADE,
        related_name="travel_advances", verbose_name=_("Employee"),
    )
    amount          = models.DecimalField(
        max_digits=12, decimal_places=2,
        verbose_name=_("Advance Amount (INR)"),
    )
    purpose         = models.CharField(
        max_length=255, blank=True, verbose_name=_("Purpose"),
    )
    status          = models.CharField(
        max_length=20, choices=STATUS, default="pending",
        verbose_name=_("Status"),
    )
    disbursed_on    = models.DateField(null=True, blank=True, verbose_name=_("Disbursed On"))
    claimed_amount  = models.DecimalField(
        max_digits=12, decimal_places=2, default=0,
        verbose_name=_("Amount Claimed Against Advance"),
    )
    returned_amount = models.DecimalField(
        max_digits=12, decimal_places=2, default=0,
        verbose_name=_("Amount Returned by Employee"),
    )

    objects = models.Manager()

    class Meta:
        verbose_name        = _("Employee Advance")
        verbose_name_plural = _("Employee Advances")

    def __str__(self):
        return f"Advance ₹{self.amount} — {self.employee} ({self.get_status_display()})"

    @property
    def pending_amount(self):
        return self.amount - self.claimed_amount - self.returned_amount


# ── 9. Expense Claim ──────────────────────────────────────────────────────────

class ExpenseClaim(HorillaModel):
    """
    Employee submits this after travel to claim reimbursements.
    Linked to travel request; advance is adjusted automatically.
    """

    STATUS = [
        ("draft",    _("Draft")),
        ("pending",  _("Pending Approval")),
        ("approved", _("Approved")),
        ("paid",     _("Paid / Reimbursed")),
        ("rejected", _("Rejected")),
    ]

    travel_request  = models.ForeignKey(
        TravelRequest, on_delete=models.CASCADE,
        related_name="expense_claims", verbose_name=_("Travel Request"),
        null=True, blank=True,
    )
    employee        = models.ForeignKey(
        Employee, on_delete=models.CASCADE,
        related_name="expense_claims", verbose_name=_("Employee"),
    )
    claim_date      = models.DateField(verbose_name=_("Claim Date"))
    status          = models.CharField(
        max_length=20, choices=STATUS, default="draft",
        verbose_name=_("Status"),
    )
    total_claimed   = models.DecimalField(
        max_digits=12, decimal_places=2, default=0,
        verbose_name=_("Total Claimed (INR)"),
    )
    total_approved  = models.DecimalField(
        max_digits=12, decimal_places=2, default=0,
        verbose_name=_("Total Approved (INR)"),
    )
    advance_adjusted = models.DecimalField(
        max_digits=12, decimal_places=2, default=0,
        verbose_name=_("Advance Adjusted (INR)"),
    )
    remarks         = models.TextField(blank=True, verbose_name=_("Remarks"))
    approved_by     = models.ForeignKey(
        Employee, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="claims_approved", verbose_name=_("Approved By"),
    )

    objects = models.Manager()

    class Meta:
        verbose_name        = _("Expense Claim")
        verbose_name_plural = _("Expense Claims")
        ordering            = ["-claim_date"]

    def __str__(self):
        return f"Claim by {self.employee} — ₹{self.total_claimed} ({self.get_status_display()})"

    @property
    def net_payable(self):
        return self.total_approved - self.advance_adjusted


# ── 10. Expense Claim Detail ──────────────────────────────────────────────────

class ExpenseClaimDetail(models.Model):
    """Line item of an expense claim — each receipt is one row."""

    EXPENSE_TYPE = [
        ("ticket",       _("Air / Rail Ticket")),
        ("hotel",        _("Hotel / Accommodation")),
        ("meals",        _("Meals & Refreshments")),
        ("transport",    _("Local Transport / Taxi")),
        ("visa",         _("Visa / Documentation")),
        ("communication",_("Phone / Internet")),
        ("other",        _("Other")),
    ]

    expense_claim   = models.ForeignKey(
        ExpenseClaim, on_delete=models.CASCADE,
        related_name="details", verbose_name=_("Expense Claim"),
    )
    expense_date    = models.DateField(verbose_name=_("Date"))
    expense_type    = models.CharField(
        max_length=30, choices=EXPENSE_TYPE, verbose_name=_("Expense Type"),
    )
    description     = models.CharField(max_length=255, verbose_name=_("Description"))
    amount_claimed  = models.DecimalField(
        max_digits=10, decimal_places=2, verbose_name=_("Amount Claimed (INR)"),
    )
    amount_approved = models.DecimalField(
        max_digits=10, decimal_places=2, default=0,
        verbose_name=_("Amount Approved (INR)"),
    )
    receipt         = models.FileField(
        upload_to=upload_path, null=True, blank=True,
        verbose_name=_("Receipt / Document"),
    )
    billable        = models.BooleanField(default=True, verbose_name=_("Billable to Company"))

    class Meta:
        verbose_name        = _("Expense Detail")
        verbose_name_plural = _("Expense Details")

    def __str__(self):
        return f"{self.get_expense_type_display()} — ₹{self.amount_claimed}"


# ── 11. Travel Invoice ────────────────────────────────────────────────────────

class TravelInvoice(HorillaModel):
    """
    Finance side — tracks vendor invoices from Travel Desk through to payment.
    Monthly reconciliation is done using these records.
    """

    STATUS = [
        ("pending",    _("Pending — Invoice Not Received")),
        ("received",   _("Invoice Received")),
        ("verified",   _("Verified by Finance")),
        ("pv_created", _("Payment Voucher Created")),
        ("paid",       _("Paid")),
        ("reconciled", _("Reconciled")),
    ]

    travel_booking      = models.ForeignKey(
        TravelBooking, on_delete=models.CASCADE,
        related_name="invoices", verbose_name=_("Travel Booking"),
    )
    vendor              = models.CharField(
        max_length=200, verbose_name=_("Vendor / Agent Name"),
    )
    invoice_number      = models.CharField(
        max_length=100, blank=True, verbose_name=_("Invoice Number"),
    )
    invoice_date        = models.DateField(
        null=True, blank=True, verbose_name=_("Invoice Date"),
    )
    invoice_amount      = models.DecimalField(
        max_digits=12, decimal_places=2, default=0,
        verbose_name=_("Invoice Amount (INR)"),
    )
    gst_amount          = models.DecimalField(
        max_digits=10, decimal_places=2, default=0,
        verbose_name=_("GST Amount (INR)"),
    )
    invoice_document    = models.FileField(
        upload_to=upload_path, null=True, blank=True,
        verbose_name=_("Invoice Document"),
    )
    status              = models.CharField(
        max_length=20, choices=STATUS, default="pending",
        verbose_name=_("Status"),
    )
    payment_voucher_no  = models.CharField(
        max_length=100, blank=True, verbose_name=_("Payment Voucher Number"),
    )
    payment_date        = models.DateField(
        null=True, blank=True, verbose_name=_("Payment Date"),
    )
    advance_adjusted    = models.DecimalField(
        max_digits=12, decimal_places=2, default=0,
        verbose_name=_("Advance Adjusted (INR)"),
    )
    agent_acknowledged  = models.BooleanField(
        default=False, verbose_name=_("Agent Acknowledged PV"),
    )
    reconciliation_month = models.CharField(
        max_length=20, blank=True,
        verbose_name=_("Reconciliation Month (YYYY-MM)"),
    )
    notes               = models.TextField(blank=True, verbose_name=_("Finance Notes"))

    objects = models.Manager()

    class Meta:
        verbose_name        = _("Travel Invoice")
        verbose_name_plural = _("Travel Invoices")
        ordering            = ["-invoice_date"]

    def __str__(self):
        return (
            f"Invoice {self.invoice_number or 'Pending'} — "
            f"{self.vendor} (₹{self.invoice_amount})"
        )

    @property
    def net_payable(self):
        return self.invoice_amount + self.gst_amount - self.advance_adjusted
