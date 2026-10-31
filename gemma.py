"""Ollama calls, prompts and validation. Calls run in background threads via Job."""
import json
import os
import random
import re
import threading
import time

import config as C

try:
    import requests
except ImportError:  # pragma: no cover
    requests = None

SYSTEM = (
    f"You write for {C.COMPANION_NAME}, a zombie's spider-shaped radio companion "
    "in a 1944 outbreak. Reply with JSON only."
)
BANNED = ["face", "skin", "hair", "body", "fat", "thin", "old", "young", "ugly", "pretty", "age", "race"]
MESSAGE_RE = re.compile(r"^[A-Z]+( [A-Z]+)?$")

_scenes = None


def scenes():
    global _scenes
    if _scenes is None:
        with open(C.SCENES_PATH, encoding="utf-8") as f:
            _scenes = json.load(f)
    return _scenes


def _words(s):
    return len(s.split())


def _has_banned(s):
    toks = re.findall(r"[a-z]+", s.lower())
    return any(t in BANNED for t in toks)


# ---------- themes ----------
def pick_theme():
    themes = list(scenes()["themes"])
    last = None
    if os.path.exists(C.LAST_THEME_PATH):
        with open(C.LAST_THEME_PATH, encoding="utf-8") as f:
            last = f.read().strip()
    pool = [t for t in themes if t != last] or themes
    theme = random.choice(pool)
    os.makedirs(C.DATA_DIR, exist_ok=True)
    with open(C.LAST_THEME_PATH, "w", encoding="utf-8") as f:
        f.write(theme)
    return theme


# ---------- prompts ----------
def job1_prompt(theme):
    return (
        f'Invent one short radio transmission for the theme "{theme}". It will be sent in Morse code.\n\n'
        f'"message": uppercase letters A to Z and single spaces only. At most {C.MESSAGE_MAX_WORDS} words '
        f'and {C.MESSAGE_MAX_LETTERS} letters in total. No digits or punctuation. Make it specific and a little '
        f'strange, not a generic phrase.\n'
        f'"spider_line": what {C.COMPANION_NAME} says after decoding it. At most {C.SPIDER_LINE_MAX_WORDS} words. '
        f'Nervous and loyal.\n\n'
        'Return exactly: {"message": "...", "spider_line": "..."}'
    )


def side_word(result):
    return result.nearest.side if result.nearest else "ahead"


def job2_prompt(message, theme, result):
    nearest_m = f"{result.nearest.dist_cm / 100:.1f}" if result.nearest else "0.0"
    contacts = [
        {"side": c.side, "metres": round(c.dist_cm / 100, 1), "people": c.people} for c in result.contacts
    ]
    sw = side_word(result)
    return (
        f"You are {C.COMPANION_NAME}. Your distance sensor just swept the room. The zombie you serve is afraid of "
        f"living humans.\n"
        f'Radio message received earlier: "{message}" (theme: {theme}).\n'
        f"Sweep result: threat {result.threat}. Estimated humans: {result.people_estimate}. "
        f"Nearest: {nearest_m} m to the {sw}.\n"
        f"Contacts: {json.dumps(contacts)}\n\n"
        "Write:\n"
        f'- "scene": at most {C.SCENE_MAX_WORDS} words. Say where the humans are and how close, using only the '
        f'readings above. Include the word "{sw}" unless the threat is CLEAR. Do not invent counts or distances.\n'
        f'- "reaction": at most {C.REACTION_MAX_WORDS} words, {C.COMPANION_NAME}\'s reaction. CLEAR: puzzled and '
        'wary. FEW: alarmed ("oh no" is fine). CROWD: panicked.\n'
        "You cannot see. You only measure distance, so never mention faces, bodies, skin, hair, age, size or looks.\n\n"
        'Return exactly: {"scene": "...", "reaction": "..."}'
    )


# ---------- validation ----------
def validate_job1(text):
    """Returns dict or None."""
    try:
        d = json.loads(text)
    except (TypeError, ValueError):
        return None
    if not isinstance(d, dict):
        return None
    msg, line = d.get("message"), d.get("spider_line")
    if not isinstance(msg, str) or not isinstance(line, str):
        return None
    msg = msg.strip()
    if not MESSAGE_RE.match(msg):
        return None
    if len(msg.replace(" ", "")) > C.MESSAGE_MAX_LETTERS or _words(msg) > C.MESSAGE_MAX_WORDS:
        return None
    line = line.strip()
    if not line or _words(line) > C.SPIDER_LINE_MAX_WORDS:
        return None
    return {"message": msg, "spider_line": line}


def validate_job2(text, threat, nearest_side):
    try:
        d = json.loads(text)
    except (TypeError, ValueError):
        return None
    if not isinstance(d, dict):
        return None
    scene, reaction = d.get("scene"), d.get("reaction")
    if not isinstance(scene, str) or not isinstance(reaction, str):
        return None
    scene, reaction = scene.strip(), reaction.strip()
    if not scene or not reaction:
        return None
    if _words(scene) > C.SCENE_MAX_WORDS or _words(reaction) > C.REACTION_MAX_WORDS:
        return None
    if _has_banned(scene) or _has_banned(reaction):
        return None
    if threat != "CLEAR":
        words = {"ahead": ["ahead", "front", "center", "centre"]}.get(nearest_side, [nearest_side])
        low = scene.lower()
        if not any(w in low for w in words):
            return None
    return {"scene": scene, "reaction": reaction}


# ---------- fallbacks ----------
def fallback_job1():
    return dict(random.choice(scenes()["fallback_transmissions"]))


def fallback_job2(result):
    s = scenes()
    people = result.people_estimate
    fill = {
        "people": people,
        "shape": "shape" if people == 1 else "shapes",
        "side": side_word(result),
        "nearest_m": f"{result.nearest.dist_cm / 100:.1f}" if result.nearest else "0.0",
    }
    return {
        "scene": s["fallback_scene"][result.threat].format(**fill),
        "reaction": s["fallback_reaction"][result.threat],
    }


# ---------- Ollama ----------
def chat(prompt, model, temperature, timeout):
    if requests is None:
        raise RuntimeError("requests not installed")
    r = requests.post(
        C.OLLAMA_URL,
        json={
            "model": model,
            "stream": False,
            "format": "json",
            "keep_alive": -1,
            "options": {"temperature": temperature},
            "messages": [{"role": "system", "content": SYSTEM}, {"role": "user", "content": prompt}],
        },
        timeout=timeout,
    )
    r.raise_for_status()
    return r.json()["message"]["content"]


def warmup(model):
    """One timed call. Returns seconds or raises."""
    t0 = time.monotonic()
    chat('Reply with {"ok": true}', model, 0.1, 60)
    return time.monotonic() - t0


class Job:
    """Background Gemma call with one retry inside the cap. Poll .result / .done."""

    def __init__(self, prompt, model, temperature, cap_s, validator, enabled=True):
        self.result = None
        self.done = not enabled
        self.fallback = not enabled
        self.elapsed = 0.0
        self.error = None
        self._t0 = time.monotonic()
        if enabled:
            threading.Thread(
                target=self._run, args=(prompt, model, temperature, cap_s, validator), daemon=True
            ).start()

    def _run(self, prompt, model, temperature, cap_s, validator):
        for _ in range(2):
            remaining = cap_s - (time.monotonic() - self._t0)
            if remaining <= 0.2:
                break
            try:
                text = chat(prompt, model, temperature, remaining)
                v = validator(text)
                if v:
                    self.result = v
                    break
                self.error = "validation failed"
            except Exception as e:  # timeout, connection, bad payload
                self.error = str(e)[:80]
                break
        self.elapsed = time.monotonic() - self._t0
        self.fallback = self.result is None
        self.done = True

    def expired(self, cap_s):
        return time.monotonic() - self._t0 >= cap_s
