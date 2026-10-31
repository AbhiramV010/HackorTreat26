import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import morse  # noqa: E402
from config import MORSE_UNIT_S  # noqa: E402


def test_every_letter_round_trips():
    for ch, code in morse.TABLE.items():
        assert morse.decode(code) == ch
    text = "THE QUICK BROWN FOX JUMPS OVER THE LAZY DOG"
    assert morse.decode(morse.to_code(text)) == text


def test_segment_durations_are_unit_multiples():
    for is_tone, dur in morse.encode("SOS TEST"):
        units = round(dur / MORSE_UNIT_S)
        assert abs(dur - units * MORSE_UNIT_S) < 1e-9
        if is_tone:
            assert units in (1, 3)
        else:
            assert units in (1, 3, 7)


def test_horde_east_total_duration():
    u = MORSE_UNIT_S
    # H .... O --- R .-. D -.. E .  /  E . A .- S ... T -
    expected = 0.0
    for word in ["HORDE", "EAST"]:
        for i, ch in enumerate(word):
            code = morse.TABLE[ch]
            expected += sum((1 if s == "." else 3) * u for s in code)
            expected += (len(code) - 1) * u
            if i < len(word) - 1:
                expected += 3 * u
    expected += 7 * u
    assert abs(morse.total_duration("HORDE EAST") - expected) < 0.05


def test_events_end_matches_total():
    ev = morse.events("HORDE EAST")
    assert ev[-1][1] == "done"
    assert abs(ev[-1][0] - morse.total_duration("HORDE EAST")) < 1e-6
    assert sum(1 for e in ev if e[1] == "letter_start") == 9
