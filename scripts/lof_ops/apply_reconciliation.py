"""
Master update — apply reconciliation decisions to Horilla.

Decisions:
  1. GREEN (77) — update Employee with real Excel data
       - 74 auto-matched + 3 manual fuzzy patches:
           JAGATHUGURU (uid=79, user_id=17)  <-> Jagathguru Jagadeesan
           MOHAMED HASIM (uid=101, user_id=10) <-> Mohamed Hashim Shahul Hameed
           nithyanadan (uid=107, user_id=81) <-> Nithyanandan Kothandaraman Mudaliar
       - And REMOVE the wrong ANAND<->Nithyanandan match
  2. YELLOW (1: Nijara Beham R) — SKIP, leave alone
  3. GRAY 12 people:
       - access card (user_id=1) + ADMIN (user_id=4) -> UNTRACK from biometric
       - other 10 -> assign to "Management" dept
  4. ORANGE (Murugan V, M. Karthik) -> deactivate + drop biometric mapping
  5. RED (NN-16, MONISH, Balavigneshraj Kasi, prabhanjan) -> same as ORANGE

Idempotent.
"""
import os
import sys
import io
import json

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

import re
import openpyxl
from django.core.validators import validate_email
from django.core.exceptions import ValidationError
from base.models import Company, Department, JobPosition
from biometric.models import BiometricDevices, BiometricEmployees
from employee.models import Employee, EmployeeWorkInformation


def sanitize_email(raw: str, fallback_uid: str) -> str:
    """Return a valid email or a placeholder if input is bad."""
    candidate = (raw or "").strip().lower()
    candidate = re.sub(r"\s+", "", candidate)  # strip any internal whitespace
    if candidate:
        try:
            validate_email(candidate)
            return candidate
        except ValidationError:
            pass
    return f"essl_user_{fallback_uid}@lof.placeholder"


def section(t):
    print("\n" + "=" * 78)
    print(f"  {t}")
    print("=" * 78)


# Manual fuzzy-match overrides — the 3 Excel names that didn't auto-match
MANUAL_FUZZY_FIXES = {
    # device user_id (string) -> excel name (exact)
    "17": "Jagathguru Jagadeesan",
    "10": "Mohamed Hashim Shahul Hameed",
    "81": "Nithyanandan Kothandaraman Mudaliar",
}

# Wrong matches we explicitly remove
WRONG_MATCHES = [
    # (device_user_id, excel_name_that_was_wrongly_matched)
    ("3", "Nithyanandan Kothandaraman Mudaliar"),  # ANAND was wrongly matched
]

# GRAY users: 10 -> Management; 2 -> untrack
GRAY_TO_MANAGEMENT_USER_IDS = {
    "2",   # ABI
    "23",  # DR MURALI CHAIRMAN
    "29",  # DR GOWTHAM
    "18",  # gopakumar
    "73",  # ARPIT
    "20",  # AVANTIKA
    "78",  # MUSHTAQ
    "79",  # vinod
    "52",  # VELUMURUGAN
    "83",  # Subash Chandra Bose S
}
GRAY_TO_UNTRACK_USER_IDS = {
    "1",  # access card
    "4",  # ADMIN
}

# ORANGE + RED: deactivate + drop mapping
DEACTIVATE_USER_IDS = {
    # ORANGE
    "Murugan V",
    "M. Karthik",
    # RED — by user_id since they're not in Excel
}
DEACTIVATE_DEVICE_USER_IDS = {
    "16",  # NN-16
    "54",  # MONISH
    "82",  # Balavigneshraj Kasi
    "93",  # prabhanjan
    # Will also pick up Murugan V + M. Karthik via Excel-name match below
}


# ─── Load reconciliation JSON ─────────────────────────────────────────
section("0. LOAD RECONCILIATION JSON")
with open(os.path.join(HORILLA_DIR, "reconciliation.json"), encoding="utf-8") as f:
    recon = json.load(f)
print(f"  GREEN: {len(recon['green'])}, YELLOW: {len(recon['yellow'])}, "
      f"ORANGE: {len(recon['orange'])}, GRAY: {len(recon['gray'])}, "
      f"RED: {len(recon['red'])}")

# ─── Load Excel for full employee details ─────────────────────────────
section("1. LOAD EXCEL")
XLSX = r"C:\Users\TRG-LOF-131-047\Downloads\Emp Details for CS.xlsx"
wb = openpyxl.load_workbook(XLSX, data_only=True)
ws = wb["Data"]
excel_rows = []
for row_idx in range(4, ws.max_row + 1):
    emp_id = ws.cell(row_idx, 2).value
    name   = ws.cell(row_idx, 3).value
    desig  = ws.cell(row_idx, 4).value
    dept   = ws.cell(row_idx, 5).value
    email  = ws.cell(row_idx, 6).value
    if emp_id and name:
        excel_rows.append({
            "emp_id": str(emp_id).strip(),
            "name":   str(name).strip(),
            "desig":  str(desig or "").strip(),
            "dept":   str(dept or "").strip() or "Unassigned",
            "email":  str(email or "").strip().lower(),
        })
excel_by_name = {r["name"]: r for r in excel_rows}
print(f"  Loaded {len(excel_rows)} rows from Excel")

# Detect Top Rock Interiors entries — to skip
SKIP_EXCEL_NAMES = {r["name"] for r in excel_rows
                    if r["emp_id"].startswith("TRI-")
                    or "toprockinteriors.com" in r["email"]}
print(f"  Skipping Top Rock Interiors entries: {SKIP_EXCEL_NAMES}")

# ─── Apply manual fuzzy fixes to the recon model in-memory ───────────
# (just for our own bookkeeping — we drive updates off our own decision tables)
print()
for dev_uid, excel_name in MANUAL_FUZZY_FIXES.items():
    print(f"  Manual fuzzy fix: device user_id={dev_uid}  <->  Excel '{excel_name}'")

# ─── Step 1: Build the canonical "device_user_id -> excel_row" map ───
section("2. BUILD CANONICAL MATCH MAP")
canon_map: dict[str, dict] = {}  # device_user_id -> excel_row

# From auto-GREEN matches
for entry in recon["green"]:
    d_uid = entry["device"]["user_id"]
    e_name = entry["excel"]["name"]
    # Skip wrong matches
    if (d_uid, e_name) in WRONG_MATCHES:
        continue
    if e_name in SKIP_EXCEL_NAMES:
        continue
    canon_map[d_uid] = excel_by_name[e_name]

# Add manual fuzzy fixes
for d_uid, excel_name in MANUAL_FUZZY_FIXES.items():
    canon_map[d_uid] = excel_by_name[excel_name]

print(f"  Canonical matches: {len(canon_map)}")

# ─── Step 2: Make sure all needed Departments exist ──────────────────
section("3. ENSURE DEPARTMENTS EXIST")
needed_depts = {row["dept"] for row in canon_map.values()}
needed_depts.add("Management")  # for GRAY people
print(f"  Departments needed: {sorted(needed_depts)}")

dept_objs = {}
created_depts = 0
# Horilla's overridden Model.save() chokes on kwargs that Django passes during
# get_or_create -> use plain construct + save() to avoid that codepath.
for d_name in needed_depts:
    obj = Department.objects.filter(department=d_name).first()
    if obj is None:
        obj = Department(department=d_name)
        obj.save()
        created_depts += 1
    dept_objs[d_name] = obj
print(f"  Created {created_depts} new Department records "
      f"({len(dept_objs)} total)")

# ─── Step 3: Update each GREEN Employee with real data ───────────────
section("4. UPDATE GREEN EMPLOYEES (real data)")
device = BiometricDevices.objects.get(machine_ip="192.168.1.252")
update_count = 0
skip_count = 0

for d_uid, excel_row in canon_map.items():
    # Find the Horilla Employee by badge_id (== device user_id)
    emp = Employee.objects.filter(badge_id=str(d_uid)).first()
    if not emp:
        skip_count += 1
        continue

    # Split name: first word -> first_name, rest -> last_name
    parts = excel_row["name"].split(" ", 1)
    first_name = parts[0]
    last_name  = parts[1] if len(parts) > 1 else ""

    # Update fields — sanitize first, respect email uniqueness
    new_email = sanitize_email(excel_row["email"], d_uid)
    email_clash = Employee.objects.filter(email=new_email).exclude(id=emp.id).first()
    if email_clash:
        # Append a discriminator (Gmail-style aliasing — still valid format)
        local, domain = new_email.split("@", 1)
        new_email = f"{local}+{d_uid}@{domain}"

    emp.employee_first_name = first_name[:200]
    emp.employee_last_name  = last_name[:200] or ""
    emp.email               = new_email
    emp.is_active           = True

    # Store EMP ID + designation in additional_info
    info = emp.additional_info or {}
    info["trg_emp_id"]    = excel_row["emp_id"]
    info["designation"]   = excel_row["desig"]
    info["dept_excel"]    = excel_row["dept"]
    info["source"]        = "excel_reconciled"
    emp.additional_info   = info

    emp.save()

    # EmployeeWorkInformation: link to Department + Company
    company = Company.objects.first()
    work_info = EmployeeWorkInformation.objects.filter(employee_id=emp).first()
    if work_info is None:
        work_info = EmployeeWorkInformation(
            employee_id=emp,
            company_id=company,
            department_id=dept_objs[excel_row["dept"]],
            email=new_email,
        )
        work_info.save()
    elif work_info.department_id_id != dept_objs[excel_row["dept"]].id:
        work_info.department_id = dept_objs[excel_row["dept"]]
        work_info.company_id    = company
        work_info.email         = new_email
        work_info.save()

    update_count += 1

print(f"  Updated {update_count} GREEN employees")
print(f"  Skipped {skip_count} (no Horilla Employee row matched their badge)")

# ─── Step 4: Move GRAY 10 to Management dept ─────────────────────────
section("5. MOVE GRAY 10 TO MANAGEMENT DEPT")
mgmt_dept = dept_objs["Management"]
mgmt_count = 0
company = Company.objects.first()

for d_uid in GRAY_TO_MANAGEMENT_USER_IDS:
    emp = Employee.objects.filter(badge_id=str(d_uid)).first()
    if not emp:
        continue

    info = emp.additional_info or {}
    info["dept_excel"] = "Management"
    info["source"]     = "device_only_management"
    emp.additional_info = info
    emp.is_active = True
    emp.save()

    work_info = EmployeeWorkInformation.objects.filter(employee_id=emp).first()
    if work_info is None:
        work_info = EmployeeWorkInformation(
            employee_id=emp, company_id=company,
            department_id=mgmt_dept, email=emp.email,
        )
        work_info.save()
    elif work_info.department_id_id != mgmt_dept.id:
        work_info.department_id = mgmt_dept
        work_info.company_id    = company
        work_info.email         = emp.email
        work_info.save()
    mgmt_count += 1

print(f"  Assigned {mgmt_count} people to Management dept")

# ─── Step 5: Untrack 'access card' + 'ADMIN' from biometric mapping ──
section("6. UNTRACK GENERIC USERS (access card, ADMIN)")
untracked = 0
for d_uid in GRAY_TO_UNTRACK_USER_IDS:
    deleted, _ = BiometricEmployees.objects.filter(
        device_id=device, user_id=str(d_uid)
    ).delete()
    if deleted:
        untracked += 1
        # Also deactivate the auto-created Employee record
        emp = Employee.objects.filter(badge_id=str(d_uid)).first()
        if emp:
            emp.is_active = False
            info = emp.additional_info or {}
            info["source"] = "untracked_generic_user"
            emp.additional_info = info
            emp.save()
print(f"  Untracked {untracked} biometric mappings (access card + ADMIN)")

# ─── Step 6: Deactivate ORANGE + RED leavers ─────────────────────────
section("7. DEACTIVATE LEAVERS (ORANGE + RED)")
# ORANGE: lookup by Excel name
orange_red_uids = set(DEACTIVATE_DEVICE_USER_IDS)
# Lookup MURUGAN VELU + M KARTHIK by name match in our reconciliation file
for entry in recon["orange"]:
    excel_name = entry["excel"]["name"]
    if excel_name in DEACTIVATE_USER_IDS:
        orange_red_uids.add(entry["device"]["user_id"])

deactivated = 0
mappings_dropped = 0
for d_uid in orange_red_uids:
    emp = Employee.objects.filter(badge_id=str(d_uid)).first()
    if emp:
        emp.is_active = False
        info = emp.additional_info or {}
        info["source"] = "deactivated_leaver"
        emp.additional_info = info
        emp.save()
        deactivated += 1

    deleted, _ = BiometricEmployees.objects.filter(
        device_id=device, user_id=str(d_uid)
    ).delete()
    if deleted:
        mappings_dropped += 1

print(f"  Deactivated {deactivated} Employee records")
print(f"  Dropped    {mappings_dropped} BiometricEmployees mappings")

# ─── Step 7: Final summary ───────────────────────────────────────────
section("8. FINAL HORILLA STATE")
print(f"  Companies:                    {Company.objects.count()}")
print(f"  Departments:                  {Department.objects.count()}")
print(f"  Employees (total):            {Employee.objects.count()}")
print(f"  Employees (active):           {Employee.objects.filter(is_active=True).count()}")
print(f"  Employees (inactive):         {Employee.objects.filter(is_active=False).count()}")
print(f"  Biometric devices:            {BiometricDevices.objects.count()}")
print(f"  BiometricEmployees mappings:  {BiometricEmployees.objects.count()}")
print(f"  EmployeeWorkInformation rows: {EmployeeWorkInformation.objects.count()}")

# Show department breakdown
print(f"\n  Department breakdown (active employees):")
for d in Department.objects.all().order_by("department"):
    n = EmployeeWorkInformation.objects.filter(
        department_id=d, employee_id__is_active=True
    ).count()
    if n > 0:
        print(f"    {d.department:<20}  {n}")

# Sample of GREEN updates
print(f"\n  Sample of updated GREEN employees:")
sample = Employee.objects.filter(
    additional_info__source="excel_reconciled"
).order_by("badge_id")[:8]
for e in sample:
    info = e.additional_info or {}
    print(f"    badge={e.badge_id:<5}  {e.employee_first_name} {e.employee_last_name or ''}  "
          f"<{e.email}>  EMP_ID={info.get('trg_emp_id', '?')}  "
          f"({info.get('designation', '?')})")
