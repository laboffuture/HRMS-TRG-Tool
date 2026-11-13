"""
Full data dump from the eSSL device — what Horilla can see and pull.
"""
import io
import sys
from collections import Counter
from datetime import datetime, date

# Force UTF-8 for Windows console
try:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
except Exception:
    pass

from zk import ZK

DEVICE_IP, DEVICE_PORT, COMM_KEY = "192.168.1.252", 4370, 0

# ZK protocol attendance status codes
STATUS_LABELS = {
    0:  "Check In",
    1:  "Check Out",
    2:  "Break Out",
    3:  "Break In",
    4:  "Overtime In",
    5:  "Overtime Out",
    15: "Face/Generic",   # newer eSSL face devices use 15
}

# ZK protocol verification mode (how the punch was made)
PUNCH_LABELS = {
    0:   "Password",
    1:   "Fingerprint",
    2:   "Card",
    3:   "Card+Fingerprint",
    4:   "Mifare/Card",
    15:  "Face",
    255: "Unspecified",
}

PRIVILEGE_LABELS = {
    0:  "User",
    2:  "Admin",
    3:  "Super Admin",
    14: "Super Admin (alt)",
}


def section(title):
    print("\n" + "=" * 70)
    print(f"  {title}")
    print("=" * 70)


def main():
    zk = ZK(DEVICE_IP, port=DEVICE_PORT, password=COMM_KEY, timeout=10, ommit_ping=True)
    conn = zk.connect()
    try:
        # ─── 1. Device identity ────────────────────────────────────────────
        section("1. DEVICE IDENTITY")
        print(f"  Name:           {conn.get_device_name()}")
        print(f"  Serial:         {conn.get_serialnumber()}")
        print(f"  Firmware:       {conn.get_firmware_version()}")
        print(f"  Platform:       {conn.get_platform()}")
        print(f"  MAC:            {conn.get_mac()}")
        print(f"  Device time:    {conn.get_time()}")
        print(f"  Server time:    {datetime.now()}")
        try:
            print(f"  Network info:   {conn.get_network_params()}")
        except Exception:
            pass

        # ─── 2. Storage / capacity ─────────────────────────────────────────
        section("2. CAPACITY & USAGE")
        try:
            conn.read_sizes()
            print(f"  Users:          {conn.users}/{conn.users_cap}")
            print(f"  Fingerprints:   {conn.fingers}/{conn.fingers_cap}")
            print(f"  Records:        {conn.records}/{conn.rec_cap}")
            print(f"  Faces:          {getattr(conn, 'faces', '?')}/{getattr(conn, 'faces_cap', '?')}")
        except Exception as e:
            print(f"  (storage read partial: {e})")

        # ─── 3. Users ──────────────────────────────────────────────────────
        section("3. ENROLLED USERS")
        users = conn.get_users()
        print(f"  Total users on device: {len(users)}\n")
        # Privilege breakdown
        priv_counts = Counter(u.privilege for u in users)
        print("  Privilege breakdown:")
        for priv, n in sorted(priv_counts.items()):
            print(f"    {PRIVILEGE_LABELS.get(priv, f'priv={priv}'):<25} {n}")

        # Show first 20 users in full
        print("\n  First 20 users:")
        print(f"  {'UID':<6} {'User ID':<10} {'Name':<28} {'Priv':<14} {'Card':<12} Group")
        print("  " + "-" * 78)
        for u in users[:20]:
            priv = PRIVILEGE_LABELS.get(u.privilege, f"priv={u.privilege}")
            name = (u.name or "").strip() or "(no name)"
            print(f"  {u.uid:<6} {u.user_id:<10} {name[:28]:<28} {priv:<14} {str(u.card)[:12]:<12} {u.group_id}")
        if len(users) > 20:
            print(f"  ... and {len(users) - 20} more users")

        # ─── 4. Attendance — overview ─────────────────────────────────────
        section("4. ATTENDANCE LOG OVERVIEW")
        atts = conn.get_attendance()
        print(f"  Total punch records on device: {len(atts):,}")
        if not atts:
            return

        # Date range
        timestamps = [a.timestamp for a in atts]
        print(f"  Earliest punch:  {min(timestamps)}")
        print(f"  Latest punch:    {max(timestamps)}")

        # By status code
        status_counts = Counter(a.status for a in atts)
        print(f"\n  Status code breakdown (what kind of punch):")
        for s, n in sorted(status_counts.items(), key=lambda x: -x[1]):
            label = STATUS_LABELS.get(s, f"status={s} (unknown)")
            print(f"    {label:<25} {n:>8,}")

        # By punch type (verification method)
        punch_counts = Counter(a.punch for a in atts)
        print(f"\n  Verification method breakdown:")
        for p, n in sorted(punch_counts.items(), key=lambda x: -x[1]):
            label = PUNCH_LABELS.get(p, f"punch={p} (unknown)")
            print(f"    {label:<25} {n:>8,}")

        # Today's activity
        today = date.today()
        today_atts = [a for a in atts if a.timestamp.date() == today]
        unique_today = len(set(a.user_id for a in today_atts))
        print(f"\n  Today ({today}):")
        print(f"    Punches:                {len(today_atts)}")
        print(f"    Distinct people:        {unique_today}")
        if today_atts:
            print(f"    First punch today:      {min(a.timestamp for a in today_atts)}")
            print(f"    Last punch today:       {max(a.timestamp for a in today_atts)}")

        # Most active people overall (top 10)
        user_counts = Counter(a.user_id for a in atts)
        print(f"\n  Top 10 most active users (lifetime punches):")
        # Build user_id -> name lookup
        name_lookup = {u.user_id: (u.name or "").strip() or "?" for u in users}
        for uid, n in user_counts.most_common(10):
            print(f"    user_id={uid:<6}  {name_lookup.get(uid, '?')[:30]:<30} {n:>6,} punches")

        # Last 15 punches in detail
        print(f"\n  Last 15 punches in detail:")
        print(f"  {'Timestamp':<22} {'UID':<8} {'Name':<25} {'Status':<14} Method")
        print("  " + "-" * 78)
        for a in atts[-15:]:
            name = name_lookup.get(a.user_id, "?")[:25]
            status_label = STATUS_LABELS.get(a.status, f"s={a.status}")
            punch_label = PUNCH_LABELS.get(a.punch, f"p={a.punch}")
            print(f"  {str(a.timestamp):<22} {a.user_id:<8} {name:<25} {status_label:<14} {punch_label}")

    finally:
        conn.disconnect()
        print("\n[Disconnected from device]")


if __name__ == "__main__":
    main()
