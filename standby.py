"""Standby steps: serial self-test, Ollama warm-up, voice pre-render, static, sleep block."""
import ctypes
import time

import config as C
import gemma
from voices import FIXED_LINES


def _ok(msg=""):
    print(f"[OK] {msg}".rstrip())


def _fail(reason):
    print(f"[FAIL] {reason}")


def _wait_msg(link, kind, timeout):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            msg = link.q.get(timeout=0.1)
        except Exception:
            continue
        if msg[0] == kind:
            return msg
        if msg[0] == "READY":
            link.q.put(msg)  # let the state machine see it too
    return None


def self_test(link, sim=False):
    if _wait_msg(link, "READY", 5.0) is None and not sim:
        _fail("no READY from Uno in 5 s")
        return False
    for deg in (20, 160, 90):
        link.send(f"PAN,{deg}")
        if _wait_msg(link, "ACK", 4.0) is None:
            _fail(f"no ACK for PAN,{deg}")
            return False
    link.send("PING")
    s = _wait_msg(link, "S", 2.0)
    if s is None:
        _fail("no reading from PING")
        return False
    _ok(f"serial self-test, PING {s[2]} cm")
    return True


def warm_ollama(model):
    try:
        t = gemma.warmup(model)
        _ok(f"ollama {model} warm-up {t:.1f}s")
        if t > 4.0:
            print("      advice: slow model, consider --model gemma3:1b")
        return True
    except Exception as e:
        _fail(f"ollama: {e}")
        return False


def prerender(voice):
    if voice.backend is None:
        _fail("no voice backend, HUD text only")
        return False
    sc = gemma.scenes()
    lines = list(FIXED_LINES)
    lines += [t["spider_line"] for t in sc["fallback_transmissions"]]
    lines += list(sc["fallback_reaction"].values())
    lines.append(sc["fallback_scene"]["CLEAR"])
    # NOTE: FEW/CROWD fallback scenes have numbers filled in at run time, so they render then.
    for ln in lines:
        voice.render(ln)
    _ok(f"voice {voice.backend}, {len(lines)} lines pre-rendered")
    return True


def make_static(audio):
    try:
        audio.prepare_static()
        _ok("static loop" if audio.ok else "static skipped (audio off)")
        return True
    except Exception as e:
        _fail(f"static: {e}")
        return False


def block_sleep():
    try:
        ctypes.windll.kernel32.SetThreadExecutionState(0x80000000 | 0x00000001 | 0x00000002)
        _ok("sleep blocked")
        return True
    except Exception as e:
        _fail(f"sleep block: {e}")
        return False


def restore_sleep():
    try:
        ctypes.windll.kernel32.SetThreadExecutionState(0x80000000)
    except Exception:
        pass


def run_all(link, audio, voice, model, sim=False, use_gemma=True):
    self_test(link, sim)
    if use_gemma:
        warm_ollama(model)
    prerender(voice)
    make_static(audio)
    block_sleep()
