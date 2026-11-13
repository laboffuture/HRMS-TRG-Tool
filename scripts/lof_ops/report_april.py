"""
April 2026 attendance report for specific employees.
Pulls directly from the eSSL device (where historical data lives).

Office hours: IN by 09:45, OUT by 18:30 (6:30 PM), 8h minimum present.

Targets (substring match, case-insensitive):
  - gnana teja
  - vishnu
  - ranjith
  - jagath
"""
import io
import sys
from collections import defaultdict
from datetime import date, datetime, time, timedelta

try:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
except Exception:
    pass

from zk import ZK

DEVICE_IP, DEVICE_PORT, COMM_KEY = "192.168.1.252", 4370, 0

# Office hours
IN_BY  = time(9, 45)    # IN must be at or before this time
OUT_BY = time(18, 30)   # OUT must be at or after this time
MIN_HOURS = 8           # Minimum hours present (first punch -> last punch)

TARGETS = ["katepalli", "gnana", "teja", "gnan", "kate"]

# Status code -> label
STATUS_LABELS = {0: "IN", 1: "OUT", 2: "BrkOut", 3: "BrkIn",
                 4: "OT-In", 5: "OT-Out", 15: "Face"}

# April 2026 range
MONTH_START = date(2026, 4, 1)
MONTH_END   = date(2026, 4, 30)


def section(t):
    print("\n" + "=" * 78)
    print(f"  {t}")
    print("=" * 78)


def fmt_dur(seconds: int) -> str:
    h = seconds // 3600
    m = (seconds % 3600) // 60
    return f"{h:02d}h{m:02d}m"


def main():
    print(f"Connecting to {DEVICE_IP}:{DEVICE_PORT} ...", flush=True)
    zk = ZK(DEVICE_IP, port=DEVICE_PORT, password=COMM_KEY, timeout=10, ommit_ping=True)
    conn = zk.connect()
    try:
        all_users = conn.get_users()
        print(f"  Got {len(all_users)} users.")
        print("Pulling 125k attendance records (this takes ~30s)...", flush=True)
        all_atts = conn.get_attendance()
        print(f"  Got {len(all_atts):,} records.")
    finally:
        conn.disconnect()

    # ─── Build user_id -> name lookup, then find matches per target ─────
    name_lookup = {u.user_id: (u.name or "").strip() for u in all_users}

    section("0. MATCHED USERS")
    matches: dict[str, list] = {t: [] for t in TARGETS}
    for u in all_users:
        nm = (u.name or "").lower().strip()
        for tgt in TARGETS:
            if tgt in nm:
                matches[tgt].append(u)

    for tgt, found in matches.items():
        if not found:
            print(f"  '{tgt}': NO MATCH on device")
        else:
            for u in found:
                print(f"  '{tgt}' -> uid={u.uid:<4} user_id={u.user_id:<5} name='{u.name}'")

    # Flatten the matched user_ids
    target_user_ids = set()
    for found in matches.values():
        for u in found:
            target_user_ids.add(u.user_id)
    if not target_user_ids:
        print("\n  No targets matched. Exiting.")
        return

    # ─── Filter attendance to (a) target users and (b) April 2026 ───────
    relevant = [
        a for a in all_atts
        if a.user_id in target_user_ids
        and MONTH_START <= a.timestamp.date() <= MONTH_END
    ]
    print(f"\n  Total April 2026 punches for these users: {len(relevant)}")

    # ─── Group by (user_id, date) ───────────────────────────────────────
    by_user_day: dict[tuple, list] = defaultdict(list)
    for a in relevant:
        by_user_day[(a.user_id, a.timestamp.date())].append(a)

    # ─── Per-user report ────────────────────────────────────────────────
    for tgt, found in matches.items():
        if not found:
            continue
        for u in found:
            section(f"USER: {u.name}  (user_id={u.user_id}, badge={u.user_id})")

            # Get distinct dates in April for this user
            user_days = sorted(d for (uid, d), _ in by_user_day.items() if uid == u.user_id)
            if not user_days:
                print("  No punches in April 2026.")
                continue

            print(f"  Working days with punches in April: {len(user_days)}")
            print()
            print(f"  {'Date':<12} {'In':<8} {'Out':<8} {'Span':<8} "
                  f"{'IN late?':<13} {'OUT early?':<13} {'>=8h?':<6}")
            print("  " + "-" * 75)

            late_count   = 0
            early_count  = 0
            short_count  = 0
            total_span_seconds = 0

            for d in user_days:
                punches = sorted(by_user_day[(u.user_id, d)], key=lambda a: a.timestamp)
                first_punch = punches[0].timestamp
                last_punch  = punches[-1].timestamp
                span_seconds = int((last_punch - first_punch).total_seconds())

                in_time  = first_punch.time()
                out_time = last_punch.time()

                # Only one punch all day - special case
                if first_punch == last_punch:
                    span_str = "—"
                    in_late_str = "(single)"
                    out_early_str = "(single)"
                    eight_str = "?"
                    short_count += 1
                else:
                    span_str = fmt_dur(span_seconds)
                    if in_time > IN_BY:
                        late_min = int(((in_time.hour*60 + in_time.minute) -
                                        (IN_BY.hour*60 + IN_BY.minute)))
                        in_late_str = f"LATE {late_min}m"
                        late_count += 1
                    else:
                        in_late_str = "OK"

                    if out_time < OUT_BY:
                        early_min = int(((OUT_BY.hour*60 + OUT_BY.minute) -
                                         (out_time.hour*60 + out_time.minute)))
                        out_early_str = f"EARLY {early_min}m"
                        early_count += 1
                    else:
                        out_early_str = "OK"

                    if span_seconds < MIN_HOURS * 3600:
                        eight_str = "NO"
                        short_count += 1
                    else:
                        eight_str = "yes"

                total_span_seconds += span_seconds

                print(f"  {d}  {in_time.strftime('%H:%M'):<8} "
                      f"{out_time.strftime('%H:%M'):<8} {span_str:<8} "
                      f"{in_late_str:<13} {out_early_str:<13} {eight_str:<6}")

            # Summary
            avg_span = total_span_seconds // max(1, len(user_days))
            print()
            print(f"  --- Summary for {u.name} ---")
            print(f"    Working days:           {len(user_days)}")
            print(f"    Late arrivals (>9:45):  {late_count}")
            print(f"    Early leaves (<18:30):  {early_count}")
            print(f"    Days under 8 hours:     {short_count}")
            print(f"    Average daily span:     {fmt_dur(avg_span)}")


if __name__ == "__main__":
    main()
