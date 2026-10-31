"""Sweep readings to contacts, people estimate and threat. Pure functions."""
import math
from dataclasses import dataclass, field
from statistics import median

import config as C


@dataclass
class Contact:
    angle: float
    dist_cm: float
    width_deg: float
    people: int
    side: str


@dataclass
class ScanResult:
    contacts: list = field(default_factory=list)
    people_estimate: int = 0
    nearest: Contact | None = None
    close: bool = False
    threat: str = "CLEAR"
    sensor_failed: bool = False


def _smooth(readings):
    vals = [cm for _, cm in readings]
    out = list(vals)
    for i in range(1, len(vals) - 1):
        out[i] = median(vals[i - 1:i + 2])
    return [(a, v) for (a, _), v in zip(readings, out)]


def _valid(cm):
    return C.MIN_VALID_CM <= cm <= C.MAX_VALID_CM


def _side(angle, mirror):
    if angle < C.LEFT_MAX_DEG:
        s = "left"
    elif angle > C.RIGHT_MIN_DEG:
        s = "right"
    else:
        return "ahead"
    if mirror:
        s = "right" if s == "left" else "left"
    return s


def analyse(readings, baseline=None, mirror=None, step_deg=None):
    """readings: list of (angle, cm). baseline: optional {angle: cm}."""
    mirror = C.MIRROR_ANGLES if mirror is None else mirror
    step_deg = C.SWEEP_STEP_DEG if step_deg is None else step_deg
    readings = sorted(readings, key=lambda r: r[0])
    if not readings:
        return ScanResult()
    sm = _smooth(readings)

    valid_vals = [cm for _, cm in sm if _valid(cm)]
    global_ref = median(valid_vals) if valid_vals else C.MAX_VALID_CM

    def ref(angle):
        if baseline and angle in baseline and _valid(baseline[angle]):
            return baseline[angle]
        return global_ref

    hits = [(a, cm) for a, cm in sm if _valid(cm) and cm <= ref(a) - C.CONTACT_MARGIN_CM]
    hit_set = {a: cm for a, cm in hits}
    angles = [a for a, _ in sm]

    # consecutive runs by index in the angle order
    runs = []
    cur = []
    for a in angles:
        if a in hit_set:
            cur.append(a)
        elif cur:
            runs.append(cur)
            cur = []
    if cur:
        runs.append(cur)

    # merge runs separated by <= MERGE_GAP_STEPS missing angles if distances are similar
    merged = []
    for run in runs:
        if merged:
            prev = merged[-1]
            gap = angles.index(run[0]) - angles.index(prev[-1]) - 1
            d_prev = median(hit_set[a] for a in prev)
            d_cur = median(hit_set[a] for a in run)
            if gap <= C.MERGE_GAP_STEPS and abs(d_prev - d_cur) <= C.MERGE_MAX_DIST_DIFF_CM:
                merged[-1] = prev + run
                continue
        merged.append(run)

    contacts = []
    for run in merged:
        angle = sum(run) / len(run)
        dist = median(hit_set[a] for a in run)
        width = len(run) * step_deg
        arc = dist * math.radians(width)
        people = max(1, min(4, round(arc / C.PERSON_WIDTH_CM)))
        contacts.append(Contact(angle, dist, width, people, _side(angle, mirror)))

    contacts.sort(key=lambda c: c.dist_cm)
    total = min(sum(c.people for c in contacts), 9)
    nearest = contacts[0] if contacts else None
    threat = "CLEAR" if total == 0 else ("FEW" if total <= C.THREAT_FEW_MAX else "CROWD")
    return ScanResult(
        contacts=contacts,
        people_estimate=total,
        nearest=nearest,
        close=bool(nearest and nearest.dist_cm < C.CLOSE_CM),
        threat=threat,
    )
