"""
Step 1 of eSSL <-> Horilla integration:
  - Register the device in BiometricDevices
  - Configure scheduled pull every 15 min
  - Set last_fetch_date = today so we DON'T re-import 125k historical records
  - Inventory existing Horilla state (Employees, Companies)

Idempotent: re-running updates the existing device row, doesn't duplicate.
"""
import os
import sys
import io
from datetime import date, time

# UTF-8 stdout for Windows console
try:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
except Exception:
    pass

# Bootstrap Django from this directory
HORILLA_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # project root
sys.path.insert(0, HORILLA_DIR)
os.chdir(HORILLA_DIR)

# Load .env (django-environ shim) — Horilla's settings.py already does this,
# but we set the override here for safety.
try:
    import environ
    environ.Env.read_env(os.path.join(HORILLA_DIR, ".env"), overwrite=True)
except Exception:
    pass

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "horilla.settings")

import django
django.setup()

from biometric.models import BiometricDevices, BiometricEmployees
from base.models import Company
from employee.models import Employee


def section(t):
    print("\n" + "=" * 70)
    print(f"  {t}")
    print("=" * 70)


# ─── 1. Pick or create the LOF company ──────────────────────────────────
section("1. COMPANY")
company = Company.objects.first()
if not company:
    print("  No Company found. Creating 'LOF Internal'...")
    company = Company.objects.create(
        company="LOF Internal",
        hq=True,
        address="Lab of Future, Coimbatore",
        country="India",
        state="Tamil Nadu",
        city="Coimbatore",
        zip="641001",
    )
    print(f"  [CREATED] Company '{company.company}' (id={company.id})")
else:
    print(f"  Using existing: {company.company}  (id={company.id})")

# ─── 2. Register / update the eSSL device ───────────────────────────────
section("2. REGISTER eSSL DEVICE")

device, created = BiometricDevices.objects.update_or_create(
    name="LOF eSSL x2008 - Main Gate",
    defaults={
        "machine_type":       "zk",
        "machine_ip":         "192.168.1.252",
        "port":               4370,
        "zk_password":        "0",
        "device_direction":   "system",
        "company_id":         company,
        "is_scheduler":       True,
        "scheduler_duration": "00:15",
        "is_live":            False,
        "last_fetch_date":    date.today(),
        "last_fetch_time":    time(0, 0),
    },
)
verb = "CREATED" if created else "UPDATED"
print(f"  [{verb}] {device.name}")
print(f"    Internal id:     {device.id}")
print(f"    IP : Port:       {device.machine_ip}:{device.port}")
print(f"    Type:            {device.machine_type} (ZKTeco / eSSL)")
print(f"    Comm Key:        {device.zk_password}")
print(f"    Direction:       {device.device_direction} (first punch=IN, last=OUT)")
print(f"    Sync mode:       SCHEDULED every {device.scheduler_duration}")
print(f"    Last fetch date: {device.last_fetch_date}  (start fresh from today)")
print(f"    Company:         {device.company_id.company}")

# ─── 3. Inventory current Horilla state ─────────────────────────────────
section("3. CURRENT HORILLA STATE")
print(f"  Companies:            {Company.objects.count()}")
print(f"  Employees:            {Employee.objects.count()}")
print(f"  Biometric devices:    {BiometricDevices.objects.count()}")
print(f"  Biometric mappings:   {BiometricEmployees.objects.count()}")

emp_count = Employee.objects.count()
print()
if emp_count == 0:
    print("  No employees yet. We'll auto-create from the 95 device users in Step 2.")
elif emp_count <= 5:
    print(f"  Existing employees ({emp_count}):")
    for e in Employee.objects.all():
        try:
            badge = e.badge_id or "-"
        except Exception:
            badge = "-"
        full_name = f"{e.employee_first_name or ''} {e.employee_last_name or ''}".strip()
        print(f"    id={e.id:<3}  badge={badge:<10}  {full_name:<30}  {e.email or '-'}")
    print()
    print("  We will MERGE: keep these as-is, and add the 95 device users as new employees.")
else:
    print(f"  Horilla has {emp_count} existing employees — too many to list.")
    print("  We'll need a mapping strategy (badge ID match / name match / CSV).")

# ─── 4. Done — what's next ──────────────────────────────────────────────
section("4. NEXT STEPS")
print("  Step 1 (this script):  device registered in Horilla")
print("  Step 2 (next):         test connection through Horilla, then pull")
print("                         the 95 device users into Horilla Employee +")
print("                         BiometricEmployees mapping records")
print("  Step 3 (final):        verify scheduler picks up new punches every 15 min")
