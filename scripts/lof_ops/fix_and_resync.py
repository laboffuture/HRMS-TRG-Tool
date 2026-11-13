"""
Step 3 (corrective):
  1. Create Django User for each Employee that lacks one
  2. Reset device's last_fetch_time so we re-process today's punches
  3. Re-run Horilla's biometric scheduler (now using the patched views.py)
  4. Report exactly what landed
"""
import os
import sys
import io
from datetime import date, time

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

from django.contrib.auth import get_user_model
User = get_user_model()  # horilla_auth.HorillaUser in 2.x
from biometric.models import BiometricDevices
from biometric.views import zk_biometric_attendance_logs
from employee.models import Employee
from attendance.models import Attendance, AttendanceActivity
from collections import Counter


def section(t):
    print("\n" + "=" * 70)
    print(f"  {t}")
    print("=" * 70)


# ─── 1. Create Django Users for all 95 employees ─────────────────────
section("1. CREATE DJANGO USERS FOR EMPLOYEES")
emps_without_user = Employee.objects.filter(employee_user_id__isnull=True)
print(f"  Employees without User account: {emps_without_user.count()}")

created_users = 0
for emp in emps_without_user:
    username = f"essl_{emp.badge_id}"
    # Avoid colliding with existing usernames (e.g. "admin")
    counter = 0
    base_username = username
    while User.objects.filter(username=username).exists():
        counter += 1
        username = f"{base_username}_{counter}"

    user = User(
        username=username,
        email=emp.email,
        first_name=emp.employee_first_name[:30],
        last_name=(emp.employee_last_name or "")[:30],
        is_active=True,
    )
    user.set_unusable_password()  # they punch via biometric, not login
    user.save()
    emp.employee_user_id = user
    emp.save(update_fields=["employee_user_id"])
    created_users += 1

print(f"  [OK] Created {created_users} Django Users")

# ─── 2. Reset device last_fetch so we re-process today ───────────────
section("2. RESET DEVICE LAST_FETCH")
device = BiometricDevices.objects.get(machine_ip="192.168.1.252")
prev_date = device.last_fetch_date
prev_time = device.last_fetch_time
device.last_fetch_date = date.today()
device.last_fetch_time = time(0, 0, 0)
device.save()
print(f"  Reset:  {prev_date} {prev_time}  ->  {device.last_fetch_date} {device.last_fetch_time}")
print(f"  Will re-process all of TODAY's punches (~333 records)")

# ─── 3. Sample what Horilla looks like BEFORE ─────────────────────────
section("3. ATTENDANCE TABLES — BEFORE")
print(f"  Attendance rows:          {Attendance.objects.count()}")
print(f"  AttendanceActivity rows:  {AttendanceActivity.objects.count()}")

# ─── 4. Run the patched scheduler ─────────────────────────────────────
section("4. RUN PATCHED SCHEDULER")
processed_count, error_msg = zk_biometric_attendance_logs(device)
print(f"  Records pulled from device: {processed_count}")
if error_msg:
    print(f"  Errors: {error_msg}")

# ─── 5. Inspect the result ────────────────────────────────────────────
section("5. ATTENDANCE TABLES — AFTER")
att_count = Attendance.objects.count()
act_count = AttendanceActivity.objects.count()
print(f"  Attendance rows:          {att_count}")
print(f"  AttendanceActivity rows:  {act_count}")

if act_count == 0:
    print("\n  Still 0 activity rows. Inspect logs for errors.")
    sys.exit(1)

# Show breakdown by employee + sample
section("6. SAMPLE OF IMPORTED ACTIVITIES")
sample = AttendanceActivity.objects.select_related("employee_id").order_by(
    "-attendance_date", "-clock_in"
)[:20]
print(f"  {'Date':<12} {'Clock-in':<10} {'Clock-out':<10} Employee")
print("  " + "-" * 70)
for a in sample:
    e = a.employee_id
    name = f"{e.employee_first_name} {e.employee_last_name or ''}".strip()[:35]
    ci = str(a.clock_in)[:8] if a.clock_in else "-"
    co = str(a.clock_out)[:8] if a.clock_out else "-"
    print(f"  {a.attendance_date}  {ci:<10} {co:<10} {name}  badge={e.badge_id}")

# Counter — how many distinct employees have at least one activity today
today = date.today()
today_acts = AttendanceActivity.objects.filter(attendance_date=today)
distinct_today = today_acts.values_list("employee_id", flat=True).distinct().count()
print(f"\n  Distinct employees with attendance TODAY: {distinct_today}")
print(f"  Total activity rows for TODAY: {today_acts.count()}")

# Show count of clock-in vs clock-out today
in_count = today_acts.exclude(clock_in__isnull=True).count()
out_count = today_acts.exclude(clock_out__isnull=True).count()
print(f"  Clock-in rows today:  {in_count}")
print(f"  Clock-out rows today: {out_count}")

print("\n  Integration is now LIVE end-to-end.")
print(f"  Scheduler will continue every {device.scheduler_duration} from now.")
