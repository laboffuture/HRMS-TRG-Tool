"""
Define the LOF Standard work shift in Horilla, and assign all 86 active
employees to it.

Shift policy
  Monday-Saturday (Sunday off; 2nd Saturday handled via Holidays later)
  Start  09:30   End  18:30   Lunch  1 hr (not modeled here)
  Working hours: 8 net per day
  Grace: 15 minutes at check-in (counter-limited to 3/month — handled by
         our custom rule engine in next step, not by Horilla's GraceTime)

This script is idempotent.
"""
import os
import sys
import io
from datetime import time

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

from base.models import (
    Company,
    EmployeeShift,
    EmployeeShiftDay,
    EmployeeShiftSchedule,
)
from attendance.models import GraceTime
from employee.models import Employee, EmployeeWorkInformation


def section(t):
    print("\n" + "=" * 78)
    print(f"  {t}")
    print("=" * 78)


SHIFT_NAME = "LOF Standard 09:30 - 18:30"
START_TIME = time(9, 30)
END_TIME   = time(18, 30)
GRACE_MIN  = 15
GRACE_SEC  = GRACE_MIN * 60
WORKDAYS   = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday"]
MIN_WORK   = "08:00"  # net 8 hours/day
WEEKLY_FT  = "48:00"  # 6 days × 8h (we'll handle 2nd Sat via Holidays)


# ─── 1. Ensure 7 EmployeeShiftDay rows exist (one per day) ────────────
section("1. SEED EmployeeShiftDay (Monday-Sunday)")
day_objs = {}
for day_key in ["monday", "tuesday", "wednesday", "thursday", "friday",
                "saturday", "sunday"]:
    obj, created = EmployeeShiftDay.objects.get_or_create(day=day_key)
    day_objs[day_key] = obj
    print(f"  [{'NEW' if created else 'EX '}] {day_key}")

# ─── 2. Create or reuse GraceTime (15 minutes, default) ──────────────
section("2. CREATE GraceTime (15 min)")
grace, created = GraceTime.objects.get_or_create(
    allowed_time_in_secs=GRACE_SEC,
    defaults={
        "allowed_time": "00:15:00",
        "allowed_clock_in":  True,
        "allowed_clock_out": False,
        "is_default": True,
    },
)
print(f"  [{'NEW' if created else 'EX '}] GraceTime: {grace.allowed_time} "
      f"(allowed_in={grace.allowed_clock_in}, default={grace.is_default})")

# ─── 3. Create the EmployeeShift template ────────────────────────────
section("3. CREATE EmployeeShift template")
shift, created = EmployeeShift.objects.get_or_create(
    employee_shift=SHIFT_NAME,
    defaults={
        "weekly_full_time": WEEKLY_FT,
        "full_time":        "200:00",
        "grace_time_id":    grace,
    },
)
# Re-link grace + company even on existing shift (idempotent)
shift.grace_time_id = grace
shift.weekly_full_time = WEEKLY_FT
shift.save()

# Attach all companies (LOF Internal here)
companies = list(Company.objects.all())
shift.company_id.set(companies)
print(f"  [{'NEW' if created else 'EX '}] Shift: '{shift.employee_shift}'  "
      f"weekly={shift.weekly_full_time}  grace={shift.grace_time_id}")
print(f"        Companies linked: {[c.company for c in companies]}")

# ─── 4. Create per-day schedule rows (Mon-Sat) ───────────────────────
section("4. CREATE EmployeeShiftSchedule (Mon-Sat, 09:30 - 18:30)")
schedule_count = 0
for day_key in WORKDAYS:
    sched, created = EmployeeShiftSchedule.objects.get_or_create(
        shift_id=shift,
        day=day_objs[day_key],
        defaults={
            "minimum_working_hour": MIN_WORK,
            "start_time":           START_TIME,
            "end_time":             END_TIME,
            "is_night_shift":       False,
        },
    )
    # Idempotent update
    if (sched.start_time != START_TIME
        or sched.end_time != END_TIME
        or sched.minimum_working_hour != MIN_WORK):
        sched.start_time           = START_TIME
        sched.end_time             = END_TIME
        sched.minimum_working_hour = MIN_WORK
        sched.save()
    schedule_count += 1
    print(f"  [{'NEW' if created else 'EX '}] {day_key:<10} "
          f"{sched.start_time}-{sched.end_time}  min_work={sched.minimum_working_hour}")

# ─── 5. Assign all 86 active employees to this shift ─────────────────
section("5. ASSIGN ALL ACTIVE EMPLOYEES TO THIS SHIFT")
active_emps = Employee.objects.filter(is_active=True)
print(f"  Active employees: {active_emps.count()}")

assigned = 0
created_wi = 0
already = 0
for emp in active_emps:
    work_info = EmployeeWorkInformation.objects.filter(employee_id=emp).first()
    if work_info is None:
        # No WorkInfo yet — create one with shift assigned
        work_info = EmployeeWorkInformation(
            employee_id=emp,
            company_id=Company.objects.first(),
            shift_id=shift,
            email=emp.email,
        )
        work_info.save()
        created_wi += 1
        assigned += 1
    elif work_info.shift_id_id != shift.id:
        work_info.shift_id = shift
        work_info.save()
        assigned += 1
    else:
        already += 1

print(f"  [OK] {assigned} employees assigned to shift")
print(f"  [OK] {already} were already on this shift")
print(f"  [OK] {created_wi} new EmployeeWorkInformation rows created")

# ─── 6. Final state ──────────────────────────────────────────────────
section("6. FINAL STATE")
print(f"  EmployeeShifts:                  {EmployeeShift.objects.count()}")
print(f"  EmployeeShiftSchedules:          {EmployeeShiftSchedule.objects.count()}")
print(f"  GraceTimes:                      {GraceTime.objects.count()}")
print(f"  Employees on '{SHIFT_NAME}':")
n = EmployeeWorkInformation.objects.filter(shift_id=shift).count()
print(f"     {n}")

# Sample summary
print(f"\n  Sample shift assignments (first 8 active employees):")
for wi in EmployeeWorkInformation.objects.filter(
    shift_id=shift, employee_id__is_active=True
).select_related("employee_id")[:8]:
    e = wi.employee_id
    print(f"    badge={e.badge_id:<5} {e.employee_first_name} {e.employee_last_name or ''}")

print("\n  [OK] Work shift fully configured & assigned.")
print(f"  Next: encode the rule engine (3-tier lates, 2hr permission, half-day, OT, LOP-from-Feb).")
