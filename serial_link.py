"""Uno I/O thread with a message queue, plus a simulated link for --sim.

Messages on the queue are tuples: ("READY",), ("S", angle, cm), ("SWEEPDONE",), ("ACK",).
"""
import queue
import random
import threading
import time

import config as C


def parse(line):
    line = line.strip()
    if not line:
        return None
    if line == "READY":
        return ("READY",)
    if line == "SWEEPDONE":
        return ("SWEEPDONE",)
    if line == "ACK":
        return ("ACK",)
    if line.startswith("S,"):
        try:
            _, a, cm = line.split(",")
            return ("S", int(a), int(cm))
        except ValueError:
            return None
    return None


class SerialLink:
    def __init__(self, port=None):
        import serial  # noqa: pyserial, imported lazily so --sim works without it
        self._serial = serial
        self.port_name = port
        self.q = queue.Queue()
        self.connected = False
        self.lost = False
        self._port = None
        self._stop = False
        threading.Thread(target=self._run, daemon=True).start()

    # ---- public ----
    def send(self, line):
        p = self._port
        if p is None:
            return
        try:
            p.write((line + "\n").encode("ascii"))
        except Exception:
            self._drop()

    def close(self):
        self._stop = True
        self._drop()

    # ---- internals ----
    def _drop(self):
        self.connected = False
        self.lost = True
        try:
            if self._port:
                self._port.close()
        except Exception:
            pass
        self._port = None

    def _candidates(self):
        if self.port_name:
            return [self.port_name]
        from serial.tools import list_ports
        return [p.device for p in list_ports.comports()]

    def _try_open(self, name):
        try:
            p = self._serial.Serial(name, C.SERIAL_BAUD, timeout=0.05)
        except Exception:
            return None
        # Opening resets the Uno; wait for READY. Garbage before it is ignored.
        deadline = time.monotonic() + (5.0 if self.port_name else 3.0)
        buf = b""
        while time.monotonic() < deadline:
            try:
                buf += p.read(p.in_waiting or 1)
            except Exception:
                break
            if b"READY" in buf:
                return p
        if self.port_name:
            return p  # user said this port; trust it even without READY
        p.close()
        return None

    def _run(self):
        buf = b""
        while not self._stop:
            if self._port is None:
                for name in self._candidates():
                    p = self._try_open(name)
                    if p:
                        self._port = p
                        self.port_name = name
                        self.connected = True
                        self.lost = False
                        self.q.put(("READY",))
                        buf = b""
                        break
                if self._port is None:
                    time.sleep(2.0)
                continue
            try:
                buf += self._port.read(self._port.in_waiting or 1)
            except Exception:
                self._drop()
                continue
            while b"\n" in buf:
                raw, buf = buf.split(b"\n", 1)
                msg = parse(raw.decode("ascii", errors="ignore"))
                if msg:
                    self.q.put(msg)


class SimLink:
    """Answers the protocol with synthetic readings. No hardware needed."""

    def __init__(self, people=None):
        self.q = queue.Queue()
        self.connected = True
        self.lost = False
        self.people = people
        self.angle = C.PAN_CENTER_DEG
        self._abort = False
        self._room_cache = None
        self.q.put(("READY",))

    def close(self):
        pass

    def send(self, line):
        parts = line.strip().split(",")
        cmd = parts[0]
        if cmd == "SWEEP":
            self._abort = False
            threading.Thread(target=self._sweep, args=[int(x) for x in parts[1:4]], daemon=True).start()
        elif cmd == "STOP":
            self._abort = True
        elif cmd == "PING":
            if self._room_cache is None:
                self._room_cache = self._room()
            self.q.put(("S", self.angle, self._room_cache.get(self.angle, 250)))
        elif cmd == "PAN":
            target = int(parts[1])
            threading.Thread(target=self._pan, args=(target,), daemon=True).start()
        elif cmd in ("ZERO", "TWITCH"):  # D (LCD) is gone
            self.q.put(("ACK",))

    def _pan(self, target):
        time.sleep(min(1.5, abs(target - self.angle) / 70 * 1.5) + 0.15)
        self.angle = target
        self.q.put(("ACK",))

    def _room(self):
        n = self.people if self.people is not None else random.randint(0, 4)
        room = {a: 250 for a in range(0, 181, C.SWEEP_STEP_DEG)}
        for _ in range(n):
            centre = random.choice(range(C.SWEEP_FROM_DEG + 10, C.SWEEP_TO_DEG - 10 + 1, C.SWEEP_STEP_DEG))
            d = random.randint(80, 200)
            for a in (centre - C.SWEEP_STEP_DEG, centre, centre + C.SWEEP_STEP_DEG):
                room[a] = min(room.get(a, 250), d + random.randint(-5, 5))
        return room

    def _sweep(self, frm, to, step):
        room = self._room()
        self._room_cache = room
        step = step if frm <= to else -step
        a = frm
        while (a <= to) if step > 0 else (a >= to):
            if self._abort:
                break
            time.sleep(0.25)
            self.angle = a
            self.q.put(("S", a, room.get(a, 250)))
            a += step
        self.q.put(("SWEEPDONE",))
