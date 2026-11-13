"""
1. Verify Horilla Model.save() bug is fixed (get_or_create now works)
2. Find HARISH P device entry and deactivate it as duplicate of Harish Sundhar (badge=106)
3. Find any other unmatched/orphan active employees to flag
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

from base.models import Department
from biometric.models import BiometricDevices, BiometricEmployees
from employee.models import Employee
from zk import ZK


def section(t):
    print("\n" + "=" * 78)
    print(f"  {t}")
    print("=" * 78)


# ─── 1. VERIFY THE Horilla BUG FIX ─────────────────────────────────────
section("1. VERIFY Model.save() FIX")
test_dept_name = "__test_get_or_create__"
try:
    obj, created = Department.objects.get_or_create(department=test_dept_name)
    if created:
        print(f"  [OK] get_or_create() created '{obj.department}' cleanly")
    else:
        print(f"  [OK] get_or_create() found existing '{obj.department}' cleanly")
    # Cleanup
    obj.delete()
    print(f"  [OK] Deleted test dept (cleanup)")
except Exception as e:
    print(f"  [FAIL] get_or_create still broken: {type(e).__name__}: {e}")
    sys.exit(1)

# ─── 2. INSPECT THE DEVICE FOR HARISH P ────────────────────────────────
section("2. FIND HARISH P ON DEVICE")
device = BiometricDevices.objects.get(machine_ip="192.168.1.252")
zk = ZK(device.machine_ip, port=device.port,
        password=int(device.zk_password), timeout=10, ommit_ping=True)
conn = zk.connect()
try:
    users = conn.get_users()
finally:
    conn.disconnect()

harish_users = [u for u in users if "harish" in (u.name or "").lower()]
print(f"  Device users matching 'harish':")
for u in harish_users:
    print(f"    user_id={u.user_id:<5} uid={u.uid:<5} name={u.name!r}")

# ─── 3. INSPECT HORILLA RECORDS FOR HARISH ─────────────────────────────
section("3. CURRENT HORILLA STATE FOR HARISH")
harish_emps = Employee.objects.filter(
    employee_first_name__icontains="harish"
).order_by("badge_id")
for e in harish_emps:
    info = e.additional_info or {}
    print(f"  badge={e.badge_id:<5} active={e.is_active}  "
          f"name='{e.employee_first_name} {e.employee_last_name or ''}'  "
          f"email={e.email}  source={info.get('source','-')}")

# Also search by exact "HARISH P"
harish_p_emp = Employee.objects.filter(employee_first_name="HARISH").first()
if harish_p_emp:
    print(f"\n  Found HARISH P-equivalent in Horilla:")
    print(f"    badge={harish_p_emp.badge_id} active={harish_p_emp.is_active}")

# ─── 4. DEACTIVATE HARISH P AS DUPLICATE OF Harish Sundhar (badge=106) ─
section("4. DEACTIVATE HARISH P (duplicate of badge=106 Harish Sundhar)")

# Locate the HARISH P device entry — by exact name
harish_p_device = next((u for u in users if u.name and u.name.strip().upper() == "HARISH P"), None)
if not harish_p_device:
    print("  [WARN] No device user with exactly name='HARISH P'.")
    print("  Candidates above — pick one by user_id and re-run.")
else:
    duplicate_uid = str(harish_p_device.user_id)
    print(f"  HARISH P found on device: user_id={duplicate_uid} uid={harish_p_device.uid}")

    # Find the Horilla Employee with this badge
    dup_emp = Employee.objects.filter(badge_id=duplicate_uid).first()
    if dup_emp:
        # Mark as inactive duplicate
        dup_emp.is_active = False
        info = dup_emp.additional_info or {}
        info["source"] = "duplicate_of_badge_106"
        info["note"] = ("Same person as Harish Sundhar (badge=106, harish@laboffuture.com). "
                        "Device has 2 enrollments for the same person — should be deleted on device.")
        dup_emp.additional_info = info
        dup_emp.save()
        print(f"  [OK] Deactivated Horilla Employee (badge={duplicate_uid})")

    # Drop the BiometricEmployees mapping for this duplicate
    deleted, _ = BiometricEmployees.objects.filter(
        device_id=device, user_id=duplicate_uid
    ).delete()
    if deleted:
        print(f"  [OK] Dropped {deleted} BiometricEmployees mapping(s) for duplicate")

# ─── 5. SCAN FOR ANY OTHER ORPHAN ACTIVE EMPLOYEES ─────────────────────
section("5. SCAN FOR OTHER UNHANDLED ACTIVE EMPLOYEES")
# Anyone active with placeholder email = was never updated in step 4 (GREEN)
orphans = Employee.objects.filter(
    is_active=True,
    email__contains="@lof.placeholder",
).order_by("badge_id")
if orphans:
    print(f"  Active employees still on placeholder data ({orphans.count()}):")
    for e in orphans:
        info = e.additional_info or {}
        print(f"    badge={e.badge_id:<5} '{e.employee_first_name} {e.employee_last_name}' "
              f"source={info.get('source','-')}")
else:
    print("  [OK] No active employees left on placeholder data.")

# ─── 6. FINAL HEADCOUNT ───────────────────────────────────────────────
section("6. FINAL HEADCOUNT")
print(f"  Active employees:               {Employee.objects.filter(is_active=True).count()}")
print(f"  Inactive employees:             {Employee.objects.filter(is_active=False).count()}")
print(f"  Active biometric mappings:      {BiometricEmployees.objects.filter(employee_id__is_active=True).count()}")

# Department breakdown
from employee.models import EmployeeWorkInformation
print(f"\n  Active by department:")
for d in Department.objects.all().order_by("department"):
    n = EmployeeWorkInformation.objects.filter(
        department_id=d, employee_id__is_active=True
    ).count()
    if n > 0:
        print(f"    {d.department:<20}  {n}")
