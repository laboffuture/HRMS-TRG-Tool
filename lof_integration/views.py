"""
lof_integration/views.py — LOF-only pages.

payroll_flow: the 7-stage India payroll pipeline overview (moved here from the
1.x fork's payroll/views/views.py so upstream payroll stays untouched).
"""

from django.contrib.auth.decorators import login_required, permission_required
from django.shortcuts import render
from django.utils.translation import gettext_lazy as _

from employee.models import Employee
from payroll.models.models import Contract, Deduction, Payslip


@login_required
@permission_required("payroll.view_contract", raise_exception=True)
def payroll_flow(request):
    """
    LOF Payroll Flow overview.

    Renders the 7-stage India payroll pipeline as a visual map. Each stage
    links to the existing Horilla feature behind it and shows a live count
    so the flow doubles as a status board. The stages are a skeleton — the
    detailed logic for each is filled in later.
    """
    contract_count = Contract.objects.count()
    employee_count = Employee.objects.filter(is_active=True).count()
    deduction_count = Deduction.objects.count()
    draft = Payslip.objects.filter(status="draft").count()
    review = Payslip.objects.filter(status="review_ongoing").count()
    confirmed = Payslip.objects.filter(status="confirmed").count()
    paid = Payslip.objects.filter(status="paid").count()

    stages = [
        {
            "num": 1,
            "title": _("Employee Master Creation"),
            "items": _("Personal details · DOJ · UAN · ESIC IP · PAN · Bank · Department · Designation"),
            "url": "employee-view",
            "action": _("Open employees"),
            "metric": employee_count,
            "metric_label": _("active employees"),
            "tone": "step",
        },
        {
            "num": 2,
            "title": _("Salary Structure Configuration"),
            "items": _("Basic · DA · HRA · Allowances · Deductions · CTC"),
            "url": "view-contract",
            "action": _("Open contracts"),
            "metric": contract_count,
            "metric_label": _("contracts"),
            "tone": "step",
        },
        {
            "num": 3,
            "title": _("Attendance & Leave Processing"),
            "items": _("Present · Absent · Weekly Off · Holidays · OT · LOP · Paid Leave"),
            "url": "attendance-view",
            "action": _("Open attendance"),
            "metric": None,
            "metric_label": "",
            "tone": "step",
        },
        {
            "num": 4,
            "title": _("Monthly Salary Calculation"),
            "items": _("Earned salary · Arrears · OT · Incentives · Reimbursements"),
            "url": "generate-payslip",
            "action": _("Generate payslips"),
            "metric": None,
            "metric_label": "",
            "tone": "step",
        },
        {
            "num": 5,
            "title": _("Statutory Deductions"),
            "items": _("Configured as payroll deduction components"),
            "url": "view-deduction",
            "action": _("Open deductions"),
            "metric": deduction_count,
            "metric_label": _("deduction rules"),
            "tone": "statutory",
            "chips": ["PF", "ESI", "PT / TDS"],
        },
        {
            "num": 6,
            "title": _("Payroll Validation & Approval"),
            "items": _("HR verification → Payroll Head → Finance → Authorised Approver"),
            "url": "view-payslip",
            "action": _("Open payslips"),
            "metric": None,
            "metric_label": "",
            "tone": "approval",
            "pipeline": [
                {"label": _("Draft"), "count": draft},
                {"label": _("Review"), "count": review},
                {"label": _("Confirmed"), "count": confirmed},
                {"label": _("Paid"), "count": paid},
            ],
        },
        {
            "num": 7,
            "title": _("Salary Disbursement"),
            "items": _("Bank transfer · Payslip · Payroll register · Bank advice"),
            "url": "view-payslip",
            "action": _("Open payslips"),
            "metric": paid,
            "metric_label": _("paid"),
            "tone": "disburse",
        },
    ]

    return render(request, "payroll/lof_flow.html", {"stages": stages})
