"""
Backfill only April 2026 — focused run to fill the gap.
Suppresses noisy print() warnings from Horilla's clock_in/out so output stays readable.
"""
import os, sys, io, contextlib
from datetime import date, time, datetime

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

from biometric.models import BiometricDevices
from biometric.views import zk_biometric_attendance_logs
from attendance.models import Attendance, AttendanceActivity

device = BiometricDevices.objects.get(machine_ip="192.168.1.252")

print(f"Resetting device.last_fetch to 2026-04-01 00:00:00 ...")
device.last_fetch_date = date(2026, 4, 1)
device.last_fetch_time = time(0, 0, 0)
device.save()

before_a = Attendance.objects.count()
before_act = AttendanceActivity.objects.count()
print(f"Before: Attendance={before_a}, Activity={before_act}\n")

# Suppress noisy stdout from clock_in/out
print("Running scheduler (silent — output suppressed for speed)...")
with open(os.devnull, "w") as devnull, contextlib.redirect_stdout(devnull):
    processed, errs = zk_biometric_attendance_logs(device)

# Restore stdout (we wrapped it earlier)
sys.stdout = io.TextIOWrapper(sys.stdout.buffer if hasattr(sys.stdout, 'buffer') else sys.__stdout__.buffer, encoding="utf-8", errors="replace")

after_a = Attendance.objects.count()
after_act = AttendanceActivity.objects.count()

print(f"\nProcessed records pulled: {processed}")
if errs:
    print(f"Errors: {errs}")
print(f"After:  Attendance={after_a} (+{after_a - before_a}), Activity={after_act} (+{after_act - before_act})")
print(f"Device last_fetch now: {device.last_fetch_date} {device.last_fetch_time}")

# Show April breakdown
from django.db.models import Count
print(f"\nApril 2026 attendance days now:")
days = (Attendance.objects.filter(attendance_date__year=2026, attendance_date__month=4)
        .values("attendance_date").annotate(n=Count("id")).order_by("attendance_date"))
for d in days:
    print(f"  {d['attendance_date']}  →  {d['n']} employees")
