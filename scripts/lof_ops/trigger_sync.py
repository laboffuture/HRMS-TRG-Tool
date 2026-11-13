"""
Step 3: Manually trigger Horilla's biometric scheduler ONCE
        (instead of waiting 15 min) and report what landed
        in the Attendance / AttendanceActivity tables.

Also dumps a sample of attendance records on the device to compare against.
"""
import os
import sys
import io
from datetime import date, datetime, timedelta

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

from biometric.models import BiometricDevices
from biometric.views import zk_biometric_attendance_logs
from attendance.models import Attendance, AttendanceActivity


def section(t):
    print("\n" + "=" * 70)
    print(f"  {t}")
    print("=" * 70)


# ─── 1. State BEFORE ────────────────────────────────────────────────
section("1. ATTENDANCE TABLES - BEFORE TRIGGER")
att_before     = Attendance.objects.count()
act_before     = AttendanceActivity.objects.count()
print(f"  Attendance rows:          {att_before}")
print(f"  AttendanceActivity rows:  {act_before}")

# Show device's last_fetch markers
device = BiometricDevices.objects.get(machine_ip="192.168.1.252")
print(f"\n  Device last_fetch_date:   {device.last_fetch_date}")
print(f"  Device last_fetch_time:   {device.last_fetch_time}")

# ─── 2. Run the scheduler ───────────────────────────────────────────
section("2. RUNNING zk_biometric_attendance_logs() ...")
try:
    processed_count, error_msg = zk_biometric_attendance_logs(device)
    print(f"  Processed: {processed_count} attendance records from device")
    if error_msg:
        print(f"  Errors:    {error_msg}")
    else:
        print(f"  Errors:    none")
except Exception as e:
    print(f"  EXCEPTION: {type(e).__name__}: {e}")
    import traceback
    traceback.print_exc()

# ─── 3. State AFTER ────────────────────────────────────────────────
section("3. ATTENDANCE TABLES - AFTER TRIGGER")
device.refresh_from_db()
att_after = Attendance.objects.count()
act_after = AttendanceActivity.objects.count()
print(f"  Attendance rows:          {att_after}    (+{att_after - att_before})")
print(f"  AttendanceActivity rows:  {act_after}    (+{act_after - act_before})")
print(f"\n  Device last_fetch_date:   {device.last_fetch_date}")
print(f"  Device last_fetch_time:   {device.last_fetch_time}")

# ─── 4. Show sample of new attendance records ─────────────────────
if act_after > act_before:
    section("4. SAMPLE OF IMPORTED ACTIVITIES")
    for a in AttendanceActivity.objects.order_by("-attendance_date", "-clock_in")[:15]:
        emp = a.employee_id
        name = f"{emp.employee_first_name} {emp.employee_last_name or ''}".strip()
        print(f"  {a.attendance_date}  {a.clock_in or '?'}  ->  {name[:30]}  badge={emp.badge_id}")
elif processed_count > 0:
    section("4. WARNING")
    print(f"  Scheduler reported processing {processed_count} records,")
    print(f"  but the AttendanceActivity table didn't grow.")
    print(f"  Likely cause: punch_code logic skipped them OR transaction rolled back.")
else:
    section("4. NO ACTIVITY IMPORTED")
    print(f"  Possible reasons:")
    print(f"   - last_fetch_date is set to today and no NEW punches yet")
    print(f"   - Employees missing employee_user_id (Django User link)")
    print(f"   - punch_code=255 is not handled by Horilla's clock_in/out switch")
