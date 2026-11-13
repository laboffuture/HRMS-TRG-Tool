"""
Calendar setup + April backfill:
  1. Move Sumathi R from Support -> Management (per user)
  2. Import 15 official 2026 holidays into base.Holidays
  3. Configure CompanyLeave: every Sunday + 2nd Saturday off
  4. Backfill attendance: reset device.last_fetch to 2026-02-01 and re-run
     the patched scheduler so February-April lands in Horilla
"""
import os
import sys
import io
from datetime import date, time, datetime

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

from base.models import Company, Department, Holidays
from leave.models import CompanyLeave
from biometric.models import BiometricDevices
from biometric.views import zk_biometric_attendance_logs
from employee.models import Employee, EmployeeWorkInformation
from attendance.models import Attendance, AttendanceActivity


def section(t):
    print("\n" + "=" * 78)
    print(f"  {t}")
    print("=" * 78)


COMPANY = Company.objects.first()

# ─── 1. Move Sumathi R -> Management ──────────────────────────────────
section("1. MOVE SUMATHI R TO MANAGEMENT")
sumathi = Employee.objects.filter(badge_id="7").first()
if sumathi:
    info = sumathi.additional_info or {}
    print(f"  Before: {sumathi.employee_first_name} {sumathi.employee_last_name or ''}  "
          f"dept={info.get('dept_excel', '?')}")

    info["dept_excel"] = "Management"
    info["note"] = "Moved to Management (per user — sumathi mam from management)"
    sumathi.additional_info = info
    sumathi.save()

    mgmt_dept = Department.objects.get(department="Management")
    wi = EmployeeWorkInformation.objects.filter(employee_id=sumathi).first()
    if wi:
        wi.department_id = mgmt_dept
        wi.save()
        print(f"  After:  dept=Management ✅")

# ─── 2. Import 15 holidays for 2026 ───────────────────────────────────
section("2. IMPORT 2026 HOLIDAYS")
HOLIDAYS_2026 = [
    ("New Year",                   date(2026,  1,  1)),
    ("Thai Pongal",                date(2026,  1, 15)),
    ("Pongal & Thiruvalluvar Day", date(2026,  1, 16)),
    ("Uzhavar Thirunaal",          date(2026,  1, 17)),
    ("Republic Day",               date(2026,  1, 26)),
    ("Eid-ul-Fitr (Ramzan)",       date(2026,  3, 21)),
    ("Tamil New Year",             date(2026,  4, 14)),
    ("May Day",                    date(2026,  5,  1)),
    ("Eid-al-Adha (Bakrid)",       date(2026,  5, 28)),
    ("Independence Day",           date(2026,  8, 15)),
    ("Ganesh Chaturthi",           date(2026,  9, 14)),
    ("Mahatma Gandhi's Birthday",  date(2026, 10,  2)),
    ("Ayudha Pooja",               date(2026, 10, 19)),
    ("Diwali (Deepavali)",         date(2026, 11,  8)),
    ("Christmas Day",              date(2026, 12, 25)),
]

created_h = 0
for name, dt in HOLIDAYS_2026:
    h, was_created = Holidays.objects.get_or_create(
        name=name[:30],
        start_date=dt,
        defaults={
            "end_date":   dt,
            "recurring":  False,  # India holidays vary by year, don't auto-repeat
            "company_id": COMPANY,
        }
    )
    if was_created:
        created_h += 1
    print(f"  [{'NEW' if was_created else 'EX '}] {dt}  {dt.strftime('%a'):<3}  {name}")
print(f"\n  Created {created_h} new Holidays records "
      f"({Holidays.objects.count()} total in DB)")

# ─── 3. CompanyLeave: every Sunday + 2nd Saturday ─────────────────────
section("3. CONFIGURE COMPANY-WIDE WEEKLY OFFS")

# Every Sunday — based_on_week is None / blank means EVERY week
sunday_off, created = CompanyLeave.objects.get_or_create(
    based_on_week=None,
    based_on_week_day="sunday",
    defaults={"company_id": COMPANY},
)
print(f"  [{'NEW' if created else 'EX '}] Every Sunday off")

# 2nd Saturday only
sat_off, created = CompanyLeave.objects.get_or_create(
    based_on_week="1",   # 0=first, 1=second, ... in Horilla's WEEKS
    based_on_week_day="saturday",
    defaults={"company_id": COMPANY},
)
print(f"  [{'NEW' if created else 'EX '}] 2nd Saturday off")

print(f"\n  CompanyLeave records: {CompanyLeave.objects.count()}")

# ─── 4. Backfill: reset device.last_fetch to Feb 1, run scheduler ─────
section("4. BACKFILL ATTENDANCE FROM 2026-02-01")
device = BiometricDevices.objects.get(machine_ip="192.168.1.252")
prev_d = device.last_fetch_date
prev_t = device.last_fetch_time
device.last_fetch_date = date(2026, 2, 1)
device.last_fetch_time = time(0, 0, 0)
device.save()
print(f"  Reset last_fetch:  {prev_d} {prev_t}  ->  "
      f"{device.last_fetch_date} {device.last_fetch_time}")

before_att = Attendance.objects.count()
before_act = AttendanceActivity.objects.count()
print(f"\n  BEFORE backfill — Attendance={before_att}, AttendanceActivity={before_act}")

print("\n  Running patched scheduler (this may take 1-3 min)...", flush=True)
processed, errs = zk_biometric_attendance_logs(device)
print(f"  Records pulled from device: {processed}")
if errs:
    print(f"  Errors:  {errs}")

after_att = Attendance.objects.count()
after_act = AttendanceActivity.objects.count()
print(f"\n  AFTER backfill — Attendance={after_att} (+{after_att-before_att}), "
      f"AttendanceActivity={after_act} (+{after_act-before_act})")

# ─── 5. Per-month breakdown of what landed ────────────────────────────
section("5. ATTENDANCE BY MONTH IN HORILLA")
from django.db.models.functions import TruncMonth
from django.db.models import Count
months = Attendance.objects.annotate(m=TruncMonth("attendance_date")).values("m") \
                            .annotate(n=Count("id")).order_by("m")
for row in months:
    print(f"  {row['m']:%Y-%m}  Attendance rows: {row['n']}")

# Distinct employees with at least 1 attendance row
dist = Attendance.objects.values("employee_id").distinct().count()
print(f"\n  Distinct employees with attendance: {dist} / 86 active")

print("\n  ✅ Backfill done. Horilla now has ~3 months of attendance.")
