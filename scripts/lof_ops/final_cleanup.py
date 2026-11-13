"""
Final cleanup:
  1. Deactivate ANAND (badge=3) — orphaned ORANGE entry, last punch Oct 2025
  2. Surface Sumathi R details for HR to fix Excel
  3. Final clean roster ready for shift/policy work
"""
import os
import sys
import io

try:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
except Exception:
    pass

HORILLA_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # project root
sys.path.insert(0, HORILLA_DIR)
os.chdir(HORILLA_DIR)
try:
    import environ
    environ.Env.read_env(os.path.join(HORILLA_DIR, ".env"), overwrite=True)
except Exception:
    pass
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "horilla.settings")
import django
django.setup()

from biometric.models import BiometricDevices, BiometricEmployees
from employee.models import Employee


def section(t):
    print("\n" + "=" * 78)
    print(f"  {t}")
    print("=" * 78)


# ─── 1. Deactivate ANAND (badge=3) ─────────────────────────────────────
section("1. DEACTIVATE ANAND (orphan from wrongly-matched ORANGE)")
device = BiometricDevices.objects.get(machine_ip="192.168.1.252")
emp = Employee.objects.filter(badge_id="3").first()
if emp:
    emp.is_active = False
    info = emp.additional_info or {}
    info["source"] = "deactivated_leaver"
    info["note"] = "Last punch 2025-10-15 (6+ months inactive); not in current Excel roster."
    emp.additional_info = info
    emp.save()
    print(f"  [OK] Deactivated {emp.employee_first_name} (badge=3)")

deleted, _ = BiometricEmployees.objects.filter(
    device_id=device, user_id="3"
).delete()
print(f"  [OK] Dropped {deleted} BiometricEmployees mapping for badge=3")

# ─── 2. Sumathi R diagnostic ───────────────────────────────────────────
section("2. SUMATHI R — placeholder email — HR action needed")
sumathi = Employee.objects.filter(badge_id="7").first()
if sumathi:
    info = sumathi.additional_info or {}
    print(f"  badge:          {sumathi.badge_id}")
    print(f"  Name:           {sumathi.employee_first_name} {sumathi.employee_last_name or ''}")
    print(f"  Current email:  {sumathi.email}  (placeholder)")
    print(f"  EMP ID:         {info.get('trg_emp_id', '?')}")
    print(f"  Designation:    {info.get('designation', '?')}")
    print(f"  Department:     {info.get('dept_excel', '?')}")
    print()
    print("  HR action: Update her email in the Excel + re-run apply_reconciliation.py.")
    print("  Or, if you give me her real email now, I can patch it directly.")

# ─── 3. Final state ────────────────────────────────────────────────────
section("3. FINAL CLEAN STATE")
active = Employee.objects.filter(is_active=True).count()
inactive = Employee.objects.filter(is_active=False).count()
mappings = BiometricEmployees.objects.filter(
    employee_id__is_active=True, device_id=device
).count()

print(f"  Active employees:           {active}")
print(f"  Inactive employees:         {inactive}")
print(f"  Active biometric mappings:  {mappings}")

# Active employees with placeholder emails (informational)
placeholder_active = Employee.objects.filter(
    is_active=True, email__contains="@lof.placeholder"
).order_by("badge_id")
print(f"\n  Active employees on placeholder email: {placeholder_active.count()}")
print(f"  (10 Management + 1 Sumathi R = expected — HR can fill in over time)")
for e in placeholder_active:
    info = e.additional_info or {}
    print(f"    badge={e.badge_id:<4} {e.employee_first_name} {e.employee_last_name or ''}  "
          f"({info.get('source', '-')})")

# Inactive employees breakdown
print(f"\n  Inactive employees ({inactive}):")
for e in Employee.objects.filter(is_active=False).order_by("badge_id"):
    info = e.additional_info or {}
    print(f"    badge={e.badge_id:<4} {e.employee_first_name} {e.employee_last_name or ''}  "
          f"({info.get('source', '-')})")
