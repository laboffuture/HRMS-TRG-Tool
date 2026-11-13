"""Backfill the Apr 14-26 gap. Tiny window, should finish quickly."""
import os, sys, io, logging
from datetime import date, time

try:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
except Exception:
    pass

HORILLA_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # project root
sys.path.insert(0, HORILLA_DIR); os.chdir(HORILLA_DIR)
try:
    import environ; environ.Env.read_env(os.path.join(HORILLA_DIR, ".env"), overwrite=True)
except Exception:
    pass
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "horilla.settings")
import django; django.setup()

# Silence Horilla's logger noise (it logs every "no clock-in to close" warning)
logging.disable(logging.CRITICAL)

from biometric.models import BiometricDevices
from biometric.views import zk_biometric_attendance_logs
from attendance.models import Attendance

device = BiometricDevices.objects.get(machine_ip="192.168.1.252")
device.last_fetch_date = date(2026, 4, 13)  # day before gap starts
device.last_fetch_time = time(23, 59, 59)
device.save()
print(f"Reset last_fetch to {device.last_fetch_date} {device.last_fetch_time}")

before = Attendance.objects.filter(attendance_date__range=(date(2026,4,14), date(2026,4,26))).count()
print(f"April 14-26 rows BEFORE: {before}")

# Redirect any stray print() noise from Horilla to a temp file
log_path = os.path.join(HORILLA_DIR, "_backfill_noise.log")
with open(log_path, "w", encoding="utf-8") as logf:
    saved_stdout = sys.stdout
    sys.stdout = logf
    try:
        processed, errs = zk_biometric_attendance_logs(device)
    finally:
        sys.stdout = saved_stdout

print(f"Records pulled from device: {processed}")
if errs:
    print(f"Errors: {errs}")

after = Attendance.objects.filter(attendance_date__range=(date(2026,4,14), date(2026,4,26))).count()
print(f"April 14-26 rows AFTER:  {after}  (+{after - before})")

from django.db.models import Count
days = (Attendance.objects
        .filter(attendance_date__range=(date(2026,4,14), date(2026,4,26)))
        .values("attendance_date").annotate(n=Count("id")).order_by("attendance_date"))
print("\nGap-week breakdown:")
for d in days:
    print(f"  {d['attendance_date']} ({d['attendance_date'].strftime('%a')})  {d['n']:>3} employees")
