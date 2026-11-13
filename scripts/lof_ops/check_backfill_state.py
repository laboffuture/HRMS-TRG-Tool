"""Check what the backfill actually wrote to Horilla."""
import os, sys, io
try: sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
except: pass

HORILLA_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # project root
sys.path.insert(0, HORILLA_DIR); os.chdir(HORILLA_DIR)
try:
    import environ; environ.Env.read_env(os.path.join(HORILLA_DIR, ".env"), overwrite=True)
except: pass
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "horilla.settings")
import django; django.setup()

from biometric.models import BiometricDevices
from attendance.models import Attendance, AttendanceActivity
from base.models import Holidays
from leave.models import CompanyLeave
from django.db.models import Count
from django.db.models.functions import TruncMonth

print("=" * 70)
print("  CURRENT HORILLA STATE")
print("=" * 70)

print(f"\n  Holidays:                       {Holidays.objects.count()}")
print(f"  CompanyLeave (Sun + 2nd Sat):   {CompanyLeave.objects.count()}")
print(f"  Attendance rows:                {Attendance.objects.count()}")
print(f"  AttendanceActivity rows:        {AttendanceActivity.objects.count()}")

device = BiometricDevices.objects.get(machine_ip="192.168.1.252")
print(f"\n  Device last_fetch_date:         {device.last_fetch_date}")
print(f"  Device last_fetch_time:         {device.last_fetch_time}")

print(f"\n  Attendance rows BY MONTH:")
months = (Attendance.objects
          .annotate(m=TruncMonth("attendance_date"))
          .values("m").annotate(n=Count("id")).order_by("m"))
for row in months:
    print(f"    {row['m']:%Y-%m}  →  {row['n']:>5} rows")

print(f"\n  Distinct employees with at least 1 day of attendance:")
print(f"    {Attendance.objects.values('employee_id').distinct().count()} / 86 active")
