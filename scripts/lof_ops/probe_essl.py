"""
ESSL probe -- tries common default COMM Keys against the device
and reports device info + a summary of users/attendance on success.

Usage:
    python probe_essl.py
"""
import io
import sys as _sys
# Force UTF-8 stdout on Windows so the unicode arrows render
try:
    _sys.stdout = io.TextIOWrapper(_sys.stdout.buffer, encoding="utf-8", errors="replace")
except Exception:
    pass
from zk import ZK
from zk import exception as zk_exception
import socket
import sys

DEVICE_IP   = "192.168.1.252"
DEVICE_PORT = 4370
TIMEOUT     = 5  # seconds per attempt

# Candidate COMM Keys, in order of likelihood
CANDIDATES = [0, 123456, 111111, 12345, 1234, 654321, 999999]


def try_key(key: int) -> dict | None:
    """Returns device info dict on success, None on failure."""
    zk = ZK(DEVICE_IP, port=DEVICE_PORT, timeout=TIMEOUT, password=key, force_udp=False, ommit_ping=True)
    conn = None
    try:
        conn = zk.connect()
        if conn is None:
            return None
        info = {
            "comm_key":      key,
            "serial":        conn.get_serialnumber(),
            "firmware":      conn.get_firmware_version(),
            "device_name":   conn.get_device_name(),
            "platform":      conn.get_platform(),
            "user_count":    len(conn.get_users()),
            "attendance":    len(conn.get_attendance()),
            "current_time":  str(conn.get_time()),
        }
        # Try to grab last few punches as a sanity check
        try:
            atts = conn.get_attendance()
            if atts:
                info["last_punches"] = [
                    f"user_id={a.user_id}  ts={a.timestamp}  status={a.status}  punch={a.punch}"
                    for a in atts[-5:]
                ]
        except Exception:
            pass
        return info
    except (zk_exception.ZKErrorResponse, zk_exception.ZKNetworkError) as e:
        return None
    except (socket.timeout, OSError) as e:
        # Network issue — bail out completely
        print(f"  ⚠ Network error: {e}")
        return None
    except Exception as e:
        # pyzk sometimes raises generic Exception on auth fail
        return None
    finally:
        if conn is not None:
            try:
                conn.disconnect()
            except Exception:
                pass


def main():
    print(f"Target: {DEVICE_IP}:{DEVICE_PORT}")
    print(f"Trying {len(CANDIDATES)} candidate COMM Keys...\n")

    for key in CANDIDATES:
        print(f">> trying COMM Key = {key} ...", end=" ", flush=True)
        info = try_key(key)
        if info:
            print("[OK] SUCCESS!\n")
            print("=" * 60)
            print(f"  COMM Key:       {info['comm_key']}")
            print(f"  Device Name:    {info.get('device_name', '?')}")
            print(f"  Serial Number:  {info.get('serial', '?')}")
            print(f"  Firmware:       {info.get('firmware', '?')}")
            print(f"  Platform:       {info.get('platform', '?')}")
            print(f"  Device Time:    {info.get('current_time', '?')}")
            print(f"  Users on device:    {info.get('user_count', '?')}")
            print(f"  Punch records:      {info.get('attendance', '?')}")
            if info.get("last_punches"):
                print(f"\n  Last {len(info['last_punches'])} punches:")
                for p in info["last_punches"]:
                    print(f"    {p}")
            print("=" * 60)
            sys.exit(0)
        else:
            print("rejected")

    print("\n[FAIL] None of the common defaults worked.")
    print("   Either the COMM Key is custom, or the device locked us out after too many attempts.")
    print("   Easiest fix: on the device, go Menu -> COMM -> PC Connection -> Comm Key -> set to 0.")
    sys.exit(1)


if __name__ == "__main__":
    main()
