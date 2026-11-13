"""
Reconcile HR's Excel employee roster (81 people) against the eSSL device's
enrolled users (95) using last-3-months attendance frequency.

Buckets:
  GREEN  — In Excel, on device, ACTIVE in last 3 months (current employees)
  YELLOW — In Excel but NOT on device (HR has them, device doesn't)
  ORANGE — On device, in Excel, but INACTIVE last 3 mo (data ambiguity)
  RED    — On device, NOT in Excel, no recent punches (likely ex-employees)
  GRAY   — On device, NOT in Excel, ACTIVE recently (mystery — investigate)

Saves the result as JSON for the next step (Horilla data update).
"""
import io
import sys
import re
import json
from collections import defaultdict, Counter
from datetime import date, timedelta, datetime
from difflib import SequenceMatcher

try:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
except Exception:
    pass

import openpyxl
from zk import ZK

XLSX_PATH = r"C:\Users\TRG-LOF-131-047\Downloads\Emp Details for CS.xlsx"
DEVICE_IP, DEVICE_PORT, COMM_KEY = "192.168.1.252", 4370, 0
import os as _os
JSON_OUT = _os.path.join(_os.path.dirname(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))), "reconciliation.json")  # project root; contains PII, git-ignored

TODAY = date.today()
THREE_MONTHS_AGO = TODAY - timedelta(days=90)

# Threshold: "active" means at least N punches in the last 90 days
ACTIVE_PUNCHES_THRESHOLD = 5


# ─── Helpers ──────────────────────────────────────────────────────────
def normalize_name(name: str) -> str:
    """Lowercase, strip punctuation, collapse spaces, remove single-letter initials."""
    if not name:
        return ""
    s = name.lower()
    # Remove dots, commas
    s = re.sub(r"[.,]", " ", s)
    # Collapse spaces
    s = re.sub(r"\s+", " ", s).strip()
    return s


def name_tokens(name: str) -> set:
    """Return word tokens of length >= 2 (skip single-letter initials)."""
    norm = normalize_name(name)
    return {t for t in norm.split() if len(t) >= 2}


def best_match(target: str, candidates: list[str]) -> tuple[str | None, float]:
    """Find the candidate with highest similarity to target."""
    best = None
    best_score = 0.0
    target_n = normalize_name(target)
    target_tokens = name_tokens(target)

    for c in candidates:
        c_n = normalize_name(c)
        c_tokens = name_tokens(c)
        if not target_n or not c_n:
            continue

        # 1) substring
        if target_n in c_n or c_n in target_n:
            substring_score = 0.92
        else:
            substring_score = 0.0

        # 2) token overlap
        if target_tokens and c_tokens:
            common = target_tokens & c_tokens
            token_score = len(common) / max(len(target_tokens), len(c_tokens))
        else:
            token_score = 0.0

        # 3) sequence ratio
        seq_score = SequenceMatcher(None, target_n, c_n).ratio()

        score = max(substring_score, token_score * 0.95, seq_score * 0.85)

        if score > best_score:
            best_score = score
            best = c

    return best, best_score


# ─── 1. Load Excel ────────────────────────────────────────────────────
print("=" * 78)
print("1. LOADING EXCEL")
print("=" * 78)
wb = openpyxl.load_workbook(XLSX_PATH, data_only=True)
ws = wb["Data"]

excel_employees = []
for row_idx in range(4, ws.max_row + 1):
    emp_id = ws.cell(row_idx, 2).value
    name = ws.cell(row_idx, 3).value
    designation = ws.cell(row_idx, 4).value
    dept = ws.cell(row_idx, 5).value
    email = ws.cell(row_idx, 6).value
    if emp_id and name:
        excel_employees.append({
            "emp_id": str(emp_id).strip(),
            "name": str(name).strip(),
            "designation": str(designation or "").strip(),
            "dept": str(dept or "").strip(),
            "email": str(email or "").strip().lower(),
        })

print(f"  Loaded {len(excel_employees)} employees from Excel")

# ─── 2. Pull device users + last 3 months of attendance ──────────────
print("\n" + "=" * 78)
print("2. PULLING DEVICE DATA")
print("=" * 78)
zk = ZK(DEVICE_IP, port=DEVICE_PORT, password=COMM_KEY, timeout=10, ommit_ping=True)
conn = zk.connect()
try:
    device_users = conn.get_users()
    print(f"  Got {len(device_users)} device users")
    print("  Pulling attendance (this takes ~30s)...")
    all_atts = conn.get_attendance()
    print(f"  Got {len(all_atts):,} attendance records (lifetime)")
finally:
    conn.disconnect()

# Filter to last 3 months
recent_atts = [a for a in all_atts if a.timestamp.date() >= THREE_MONTHS_AGO]
print(f"  Last 3 months ({THREE_MONTHS_AGO} to {TODAY}): {len(recent_atts):,} records")

# Count per user
recent_punch_count = Counter(a.user_id for a in recent_atts)

# ─── 3. Build device user lookup ──────────────────────────────────────
device_data = []
for u in device_users:
    last_punch = max((a.timestamp for a in all_atts if a.user_id == u.user_id),
                     default=None)
    first_punch = min((a.timestamp for a in all_atts if a.user_id == u.user_id),
                      default=None)
    device_data.append({
        "user_id": str(u.user_id),
        "uid": u.uid,
        "name": (u.name or "").strip(),
        "recent_punches": recent_punch_count.get(u.user_id, 0),
        "first_punch":  first_punch.isoformat() if first_punch  else None,
        "last_punch":   last_punch.isoformat()  if last_punch   else None,
    })

# ─── 4. Fuzzy match ──────────────────────────────────────────────────
print("\n" + "=" * 78)
print("3. FUZZY MATCHING (excel <-> device)")
print("=" * 78)

excel_name_to_emp = {e["name"]: e for e in excel_employees}
excel_names = list(excel_name_to_emp.keys())

device_name_to_user = {d["name"]: d for d in device_data if d["name"]}
device_names = list(device_name_to_user.keys())

# For each excel employee, find best device match
excel_to_device: dict[str, dict | None] = {}
device_to_excel: dict[str, dict | None] = {}
match_score: dict[str, float] = {}

# First pass — for each excel employee find best device candidate
for e in excel_employees:
    best, score = best_match(e["name"], device_names)
    if best and score >= 0.55:
        excel_to_device[e["name"]] = device_name_to_user[best]
        device_to_excel[best] = e
        match_score[e["name"]] = score
    else:
        excel_to_device[e["name"]] = None

# ─── 5. Categorize ────────────────────────────────────────────────────
green = []   # in both, active
yellow = []  # excel only
orange = []  # in both, but inactive on device
red = []     # device only, NO recent activity (likely ex-emp)
gray = []    # device only, with recent activity (mystery)

for e in excel_employees:
    matched = excel_to_device[e["name"]]
    if matched is None:
        yellow.append({"excel": e, "score": 0})
    else:
        if matched["recent_punches"] >= ACTIVE_PUNCHES_THRESHOLD:
            green.append({"excel": e, "device": matched,
                          "score": match_score[e["name"]]})
        else:
            orange.append({"excel": e, "device": matched,
                           "score": match_score[e["name"]]})

for d in device_data:
    if d["name"] not in device_to_excel:
        if d["recent_punches"] >= ACTIVE_PUNCHES_THRESHOLD:
            gray.append(d)
        else:
            red.append(d)

# ─── 6. Print report ──────────────────────────────────────────────────
print(f"\nGREEN  (Excel & device, active in last 3 mo):   {len(green)}")
print(f"YELLOW (Excel only — not enrolled on device):    {len(yellow)}")
print(f"ORANGE (in both, but inactive last 3 mo):        {len(orange)}")
print(f"GRAY   (device only — currently active):         {len(gray)}")
print(f"RED    (device only — likely ex-employees):      {len(red)}")

print("\n" + "=" * 78)
print("YELLOW — EXCEL EMPLOYEES NOT ON DEVICE  (need enrollment)")
print("=" * 78)
for entry in yellow:
    e = entry["excel"]
    print(f"  {e['emp_id']:<22} {e['name']:<32} dept={e['dept']:<14} {e['email']}")

print("\n" + "=" * 78)
print("ORANGE — IN BOTH, BUT NO RECENT PUNCHES  (verify status)")
print("=" * 78)
for entry in orange:
    e, d = entry["excel"], entry["device"]
    print(f"  excel={e['name']:<28} device={d['name']:<22} "
          f"last_punch={d['last_punch']}  recent={d['recent_punches']}")

print("\n" + "=" * 78)
print("GRAY — DEVICE-ONLY BUT ACTIVE  (who are these?)")
print("=" * 78)
for d in gray:
    print(f"  uid={d['uid']:<5} user_id={d['user_id']:<5} name={d['name']!r:<35} "
          f"recent={d['recent_punches']:<5} last={d['last_punch']}")

print("\n" + "=" * 78)
print("RED — DEVICE-ONLY, INACTIVE  (likely ex-employees, candidates for removal)")
print("=" * 78)
for d in red:
    print(f"  uid={d['uid']:<5} user_id={d['user_id']:<5} name={d['name']!r:<35} "
          f"recent={d['recent_punches']:<5} last={d['last_punch']}")

# Show a sample of green for confidence (lowest-score matches first)
print("\n" + "=" * 78)
print("GREEN — sample (10 lowest-confidence matches — verify these visually)")
print("=" * 78)
green_sorted = sorted(green, key=lambda g: g["score"])
for entry in green_sorted[:10]:
    e, d = entry["excel"], entry["device"]
    print(f"  score={entry['score']:.2f}  excel={e['name']!r:<35} <-> device={d['name']!r:<25}")

# ─── 7. Save JSON for next step ──────────────────────────────────────
print("\n" + "=" * 78)
print("4. SAVING JSON")
print("=" * 78)
output = {
    "as_of": TODAY.isoformat(),
    "three_months_ago": THREE_MONTHS_AGO.isoformat(),
    "active_threshold": ACTIVE_PUNCHES_THRESHOLD,
    "totals": {
        "excel_employees": len(excel_employees),
        "device_users": len(device_users),
        "green":  len(green),
        "yellow": len(yellow),
        "orange": len(orange),
        "gray":   len(gray),
        "red":    len(red),
    },
    "green":  green,
    "yellow": yellow,
    "orange": orange,
    "gray":   gray,
    "red":    red,
}
with open(JSON_OUT, "w", encoding="utf-8") as f:
    json.dump(output, f, indent=2, ensure_ascii=False)
print(f"  Wrote: {JSON_OUT}")
