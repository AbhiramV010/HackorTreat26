"""Text to Morse timing and back. Pure functions, no audio here."""
from config import MORSE_UNIT_S

TABLE = {
    "A": ".-", "B": "-...", "C": "-.-.", "D": "-..", "E": ".", "F": "..-.",
    "G": "--.", "H": "....", "I": "..", "J": ".---", "K": "-.-", "L": ".-..",
    "M": "--", "N": "-.", "O": "---", "P": ".--.", "Q": "--.-", "R": ".-.",
    "S": "...", "T": "-", "U": "..-", "V": "...-", "W": ".--", "X": "-..-",
    "Y": "-.--", "Z": "--..",
}
REVERSE = {v: k for k, v in TABLE.items()}

DOT, DASH, GAP_SYMBOL, GAP_LETTER, GAP_WORD = 1, 3, 1, 3, 7


def letters(text):
    """[(char, code)] for each letter, with (' ', None) for word gaps."""
    out = []
    for ch in text.upper():
        if ch == " ":
            out.append((" ", None))
        elif ch in TABLE:
            out.append((ch, TABLE[ch]))
    return out


def encode(text, unit=MORSE_UNIT_S):
    """List of (is_tone, duration_s) segments."""
    segs = []
    items = letters(text)
    for i, (ch, code) in enumerate(items):
        if code is None:
            # word gap replaces the preceding letter gap
            if segs and not segs[-1][0]:
                segs.pop()
            segs.append((False, GAP_WORD * unit))
            continue
        for j, sym in enumerate(code):
            segs.append((True, (DOT if sym == "." else DASH) * unit))
            if j < len(code) - 1:
                segs.append((False, GAP_SYMBOL * unit))
        if i < len(items) - 1 and items[i + 1][1] is not None:
            segs.append((False, GAP_LETTER * unit))
    return segs


def decode(code):
    """Inverse of letters(): '.... --- / ..' -> 'HO I'. Letters split by spaces, words by ' / '."""
    words = []
    for word in code.strip().split("/"):
        words.append("".join(REVERSE.get(sym, "?") for sym in word.split()))
    return " ".join(words)


def to_code(text):
    return " / ".join(" ".join(TABLE[c] for c in w if c in TABLE) for w in text.upper().split())


def total_duration(text, unit=MORSE_UNIT_S):
    return sum(d for _, d in encode(text, unit))


def events(text, unit=MORSE_UNIT_S):
    """Playback events as (t_offset_s, name, arg): letter_start(index), symbol(char),
    letter_end(index), done. Index counts letters only (spaces skipped)."""
    ev = []
    t = 0.0
    items = letters(text)
    idx = 0
    for i, (ch, code) in enumerate(items):
        if code is None:
            t += GAP_WORD * unit
            continue
        ev.append((t, "letter_start", idx))
        for j, sym in enumerate(code):
            ev.append((t, "symbol", sym))
            t += (DOT if sym == "." else DASH) * unit
            if j < len(code) - 1:
                t += GAP_SYMBOL * unit
        ev.append((t, "letter_end", idx))
        idx += 1
        if i < len(items) - 1 and items[i + 1][1] is not None:
            t += GAP_LETTER * unit
    ev.append((t, "done", None))
    return ev
