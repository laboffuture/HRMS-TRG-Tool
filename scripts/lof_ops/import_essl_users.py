"""
Step 2 of eSSL <-> Horilla integration:
  - Pull the 95 users from the device
  - Create a Horilla Employee for each (badge_id = device user_id)
  - Call Horilla's built-in find_employees_in_zk() to auto-create
    BiometricEmployees mapping rows

Idempotent: re-running won't duplicate. Existing employees (matched by email
or badge_id) are skipped.

Placeholder strategy:
  - email:      essl_user_<user_id>@lof.placeholder   (unique, valid format)
  - phone:      empty (HR fills later)
  - first/last: split device name on first space
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

from zk import ZK
from biometric.models import BiometricDevices, BiometricEmployees
from biometric.views import find_employees_in_zk
from base.models import Company
from employee.models import Employee


def parse_name(raw_name: str) -> tuple[str, str]:
    """Split 'rahul radhakrishanan' -> ('rahul', 'radhakrishanan')
       'USHA' -> ('USHA', '')
       '' -> ('Unknown', '')"""
    raw = (raw_name or "").strip()
    if not raw:
        return ("Unknown", "")
    parts = raw.split(" ", 1)
    if len(parts) == 1:
        return (parts[0], "")
    return (parts[0], parts[1])


def section(t):
    print("\n" + "=" * 70)
    print(f"  {t}")
    print("=" * 70)


# ─── 1. Locate the device row ─────────────────────────────────────────
section("1. LOCATE DEVICE")
device = BiometricDevices.objects.filter(machine_ip="192.168.1.252").first()
if not device:
    print("  [ERROR] No device with IP 192.168.1.252 in BiometricDevices.")
    print("  Run setup_essl.py first.")
    sys.exit(1)
print(f"  Device: {device.name}  (id={device.id})")

# ─── 2. Pull users from device ────────────────────────────────────────
section("2. PULL 95 USERS FROM eSSL DEVICE")
zk_device = ZK(device.machine_ip, port=device.port,
               password=int(device.zk_password), timeout=10, ommit_ping=True)
conn = zk_device.connect()
try:
    device_users = conn.get_users()
finally:
    conn.disconnect()
print(f"  Got {len(device_users)} users from device.")

# ─── 3. Inventory existing Horilla state ──────────────────────────────
section("3. EXISTING HORILLA EMPLOYEES")
existing_emails  = set(Employee.objects.values_list("email", flat=True))
existing_badges  = set(Employee.objects.exclude(badge_id__isnull=True)
                                       .values_list("badge_id", flat=True))
print(f"  Existing employees in Horilla: {Employee.objects.count()}")
print(f"  Existing emails: {len(existing_emails)}")
print(f"  Existing badge IDs: {len(existing_badges)}")

# ─── 4. Bulk create Horilla Employees ─────────────────────────────────
section("4. CREATE HORILLA EMPLOYEES FROM DEVICE USERS")

created_count = 0
skipped_count = 0
new_employees = []

for u in device_users:
    user_id = str(u.user_id).strip()
    if not user_id:
        print(f"  [SKIP] Device user with empty user_id (uid={u.uid})")
        skipped_count += 1
        continue

    placeholder_email = f"essl_user_{user_id}@lof.placeholder"
    first, last = parse_name(u.name)

    # Skip if badge_id or email already taken (idempotent re-run)
    if user_id in existing_badges:
        skipped_count += 1
        continue
    if placeholder_email in existing_emails:
        skipped_count += 1
        continue

    # Special handling for the "access card" generic user (id=1)
    if user_id == "1" and first.lower() == "access":
        first, last = "Access", "Card (Generic)"

    # Anonymous user (no name on device) — flag explicitly
    if first == "Unknown":
        last = f"User #{user_id}"

    new_employees.append(
        Employee(
            badge_id=user_id,
            employee_first_name=first[:200],
            employee_last_name=last[:200],
            email=placeholder_email,
            phone="",
            is_active=True,
            additional_info={
                "imported_from": "essl_x2008",
                "device_uid": u.uid,
                "device_user_id": user_id,
                "original_device_name": u.name,
            },
        )
    )

# Bulk insert (much faster than .save() loop)
if new_employees:
    Employee.objects.bulk_create(new_employees)
    created_count = len(new_employees)
print(f"  [OK] Created {created_count} new employees")
print(f"  [OK] Skipped {skipped_count} (already existed)")

# ─── 5. Auto-link BiometricEmployees mappings via Horilla's helper ────
section("5. CREATE BiometricEmployees MAPPINGS")
before = BiometricEmployees.objects.filter(device_id=device).count()
find_employees_in_zk(device.id)
after = BiometricEmployees.objects.filter(device_id=device).count()
print(f"  Mappings before: {before}")
print(f"  Mappings after:  {after}")
print(f"  [OK] Created {after - before} new mappings")

# ─── 6. Final summary ─────────────────────────────────────────────────
section("6. FINAL STATE")
print(f"  Companies:                    {Company.objects.count()}")
print(f"  Employees:                    {Employee.objects.count()}")
print(f"  Biometric devices:            {BiometricDevices.objects.count()}")
print(f"  BiometricEmployees mappings:  {BiometricEmployees.objects.count()}")

print("\n  Sample of newly mapped users (first 10):")
for be in BiometricEmployees.objects.filter(device_id=device).select_related("employee_id")[:10]:
    e = be.employee_id
    name = f"{e.employee_first_name} {e.employee_last_name}".strip()
    print(f"    user_id={be.user_id:<6}  uid={be.uid:<6}  ->  {name}  (badge={e.badge_id})")

print("\n  Done. Next: enable scheduler and watch first sync.")
