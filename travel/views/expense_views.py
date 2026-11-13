"""
travel/views/expense_views.py
─────────────────────────────
Expense claim views for the Travel & Expense module.

  • My expense claims   (employee)
  • All expense claims  (HR / Finance)
  • Create claim        (employee)
  • Detail / Edit claim (employee / HR)
  • Approve claim       (HR / Finance)
"""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import gettext_lazy as _

from employee.models import Employee

from travel.filters import ExpenseClaimFilter
from travel.forms import ExpenseClaimDetailFormSet, ExpenseClaimForm
from travel.models import ExpenseClaim, ExpenseClaimDetail


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _get_employee(request):
    try:
        return Employee.objects.get(employee_user_id=request.user)
    except Employee.DoesNotExist:
        return None


# ─────────────────────────────────────────────────────────────────────────────
# Expense Claim — List Views
# ─────────────────────────────────────────────────────────────────────────────

@login_required
def travel_expense_list(request):
    """HR / Finance view — all expense claims with filters."""
    if not (
        request.user.has_perm("travel.view_all_travelrequest")
        or request.user.is_superuser
    ):
        messages.error(request, _("You do not have permission to view all expense claims."))
        return redirect("travel-dashboard")

    qs = ExpenseClaim.objects.select_related(
        "employee", "travel_request", "approved_by"
    ).order_by("-claim_date")
    f  = ExpenseClaimFilter(request.GET, queryset=qs)

    return render(request, "travel/expense_list.html", {
        "title":  _("Expense Claims"),
        "filter": f,
        "claims": f.qs,
    })


@login_required
def travel_my_expense_claims(request):
    """Employee sees only their own expense claims."""
    employee = _get_employee(request)
    if not employee:
        messages.warning(request, _("No employee record found for your account."))
        return redirect("travel-dashboard")

    claims = ExpenseClaim.objects.filter(employee=employee).order_by("-claim_date")
    return render(request, "travel/expense_list.html", {
        "title":   _("My Expense Claims"),
        "claims":  claims,
        "my_view": True,
    })


# ─────────────────────────────────────────────────────────────────────────────
# Expense Claim — Create
# ─────────────────────────────────────────────────────────────────────────────

@login_required
def travel_expense_create(request):
    """
    Employee creates an expense claim after travel.
    Uses an inline formset for line items.
    """
    if request.method == "POST":
        form    = ExpenseClaimForm(request.POST, request.FILES, request=request)
        formset = ExpenseClaimDetailFormSet(request.POST, request.FILES)
        if form.is_valid() and formset.is_valid():
            claim           = form.save(commit=False)
            claim.save()
            formset.instance = claim
            formset.save()

            # Recalculate total from saved detail lines
            total = sum(d.amount_claimed for d in claim.details.all())
            claim.total_claimed = total
            claim.save(update_fields=["total_claimed"])

            messages.success(request, _("Expense claim submitted."))
            return redirect("travel-expense-detail", pk=claim.pk)
    else:
        form    = ExpenseClaimForm(request=request)
        formset = ExpenseClaimDetailFormSet()

    return render(request, "travel/expense_form.html", {
        "title":   _("New Expense Claim"),
        "form":    form,
        "formset": formset,
    })


# ─────────────────────────────────────────────────────────────────────────────
# Expense Claim — Detail
# ─────────────────────────────────────────────────────────────────────────────

@login_required
def travel_expense_detail(request, pk):
    """Detail / read view for a claim."""
    claim    = get_object_or_404(
        ExpenseClaim.objects.select_related("employee", "travel_request", "approved_by"),
        pk=pk,
    )
    employee = _get_employee(request)
    is_owner = employee and claim.employee_id == employee.pk
    can_hr   = request.user.has_perm("travel.view_all_travelrequest")

    if not (is_owner or can_hr or request.user.is_superuser):
        messages.error(request, _("Permission denied."))
        return redirect("travel-dashboard")

    details = claim.details.all()
    return render(request, "travel/expense_detail.html", {
        "title":    _("Expense Claim Detail"),
        "claim":    claim,
        "details":  details,
        "is_owner": is_owner,
        "can_hr":   can_hr,
    })


# ─────────────────────────────────────────────────────────────────────────────
# Expense Claim — Edit
# ─────────────────────────────────────────────────────────────────────────────

@login_required
def travel_expense_update(request, pk):
    """Employee edits a draft claim (before submission)."""
    claim    = get_object_or_404(ExpenseClaim, pk=pk)
    employee = _get_employee(request)
    is_owner = employee and claim.employee_id == employee.pk
    is_hr    = request.user.has_perm("travel.view_all_travelrequest")

    if not (is_owner or is_hr):
        messages.error(request, _("Permission denied."))
        return redirect("travel-expense-detail", pk=pk)

    if claim.status != "draft" and not is_hr:
        messages.error(request, _("Only draft claims can be edited."))
        return redirect("travel-expense-detail", pk=pk)

    if request.method == "POST":
        form    = ExpenseClaimForm(request.POST, request.FILES, instance=claim, request=request)
        formset = ExpenseClaimDetailFormSet(request.POST, request.FILES, instance=claim)
        if form.is_valid() and formset.is_valid():
            claim = form.save()
            formset.save()
            total = sum(d.amount_claimed for d in claim.details.all())
            claim.total_claimed = total
            claim.save(update_fields=["total_claimed"])
            messages.success(request, _("Expense claim updated."))
            return redirect("travel-expense-detail", pk=claim.pk)
    else:
        form    = ExpenseClaimForm(instance=claim, request=request)
        formset = ExpenseClaimDetailFormSet(instance=claim)

    return render(request, "travel/expense_form.html", {
        "title":   _("Edit Expense Claim"),
        "form":    form,
        "formset": formset,
        "claim":   claim,
    })


# ─────────────────────────────────────────────────────────────────────────────
# Expense Claim — Submit / Approve / Reject / Pay
# ─────────────────────────────────────────────────────────────────────────────

@login_required
def travel_expense_submit(request, pk):
    """Employee submits a draft claim for approval."""
    claim    = get_object_or_404(ExpenseClaim, pk=pk)
    employee = _get_employee(request)

    if not (employee and claim.employee_id == employee.pk):
        messages.error(request, _("Permission denied."))
        return redirect("travel-dashboard")

    if claim.status != "draft":
        messages.error(request, _("Only draft claims can be submitted."))
        return redirect("travel-expense-detail", pk=pk)

    if not claim.details.exists():
        messages.error(request, _("Add at least one expense line before submitting."))
        return redirect("travel-expense-detail", pk=pk)

    claim.status = "pending"
    claim.save(update_fields=["status"])
    messages.success(request, _("Expense claim submitted for approval."))
    return redirect("travel-expense-detail", pk=pk)


@login_required
def travel_expense_approve(request, pk):
    """
    HR / Finance approves an expense claim.
    Sets per-line amount_approved and overall total_approved.
    """
    if not request.user.has_perm("travel.view_all_travelrequest"):
        messages.error(request, _("Permission denied."))
        return redirect("travel-dashboard")

    claim    = get_object_or_404(ExpenseClaim, pk=pk, status="pending")
    employee = _get_employee(request)

    if request.method == "POST":
        action = request.POST.get("action")
        if action == "approve":
            # Set approved amounts (use claimed amounts as default if not overridden)
            total_approved = 0
            for detail in claim.details.all():
                key = f"approved_{detail.pk}"
                approved_val = request.POST.get(key, "").strip()
                try:
                    approved_val = float(approved_val) if approved_val else float(detail.amount_claimed)
                    if approved_val < 0:
                        approved_val = 0.0
                except (ValueError, TypeError):
                    approved_val = float(detail.amount_claimed)
                ExpenseClaimDetail.objects.filter(pk=detail.pk).update(
                    amount_approved=approved_val
                )
                total_approved += approved_val

            claim.status        = "approved"
            claim.total_approved = total_approved
            claim.approved_by   = employee
            claim.save(update_fields=["status", "total_approved", "approved_by"])
            messages.success(request, _("Expense claim approved."))

        elif action == "reject":
            claim.status  = "rejected"
            claim.remarks = request.POST.get("remarks", "")
            claim.save(update_fields=["status", "remarks"])
            messages.success(request, _("Expense claim rejected."))

        elif action == "pay":
            # Mark as paid
            claim.status = "paid"
            claim.save(update_fields=["status"])
            messages.success(request, _("Expense claim marked as paid."))

        return redirect("travel-expense-detail", pk=pk)

    details = claim.details.all()
    return render(request, "travel/expense_approve.html", {
        "title":   _("Review Expense Claim"),
        "claim":   claim,
        "details": details,
    })


@login_required
def travel_expense_delete(request, pk):
    """Delete a draft expense claim."""
    claim    = get_object_or_404(ExpenseClaim, pk=pk)
    employee = _get_employee(request)
    is_owner = employee and claim.employee_id == employee.pk

    if not (is_owner or request.user.is_superuser):
        messages.error(request, _("Permission denied."))
        return redirect("travel-dashboard")

    if claim.status != "draft":
        messages.error(request, _("Only draft claims can be deleted."))
        return redirect("travel-expense-detail", pk=pk)

    claim.delete()
    messages.success(request, _("Expense claim deleted."))
    return redirect("travel-my-expense-claims")
