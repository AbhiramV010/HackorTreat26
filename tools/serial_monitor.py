"""Print every line from the Uno with a timestamp, send anything typed.

Usage: python tools/serial_monitor.py --port COM3
"""
import argparse
import sys
import threading
import time

import serial


def reader(port):
    buf = b""
    while True:
        try:
            buf += port.read(port.in_waiting or 1)
        except serial.SerialException as e:
            print(f"[serial lost] {e}")
            return
        while b"\n" in buf:
            line, buf = buf.split(b"\n", 1)
            text = line.decode("ascii", errors="replace").strip()
            if text:
                print(f"{time.strftime('%H:%M:%S')}.{int(time.time() * 1000) % 1000:03d}  {text}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", required=True)
    ap.add_argument("--baud", type=int, default=115200)
    args = ap.parse_args()

    port = serial.Serial(args.port, args.baud, timeout=0.05)
    threading.Thread(target=reader, args=(port,), daemon=True).start()
    print(f"open {args.port} @ {args.baud}. Type a command and press Enter (Ctrl+C to quit).")
    try:
        for line in sys.stdin:
            port.write((line.strip() + "\n").encode("ascii"))
    except KeyboardInterrupt:
        pass
    finally:
        port.close()


if __name__ == "__main__":
    main()
