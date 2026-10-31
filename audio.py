"""Beeps, static and speech playback through pygame.mixer. Never raises on a missing device."""
import time

import numpy as np

import config as C
import morse

try:
    from scipy.signal import butter, sosfilt
except ImportError:  # pragma: no cover
    butter = sosfilt = None


def _bandpass(x):
    if butter is None:
        return x
    sos = butter(4, [300, 3000], btype="band", fs=C.SAMPLE_RATE, output="sos")
    return sosfilt(sos, x)


def make_sound(pcm):
    """int16 mono array -> Sound, widened to stereo if the mixer opened stereo (Windows often forces it)."""
    import pygame
    init = pygame.mixer.get_init()
    if init and init[2] == 2 and pcm.ndim == 1:
        pcm = np.column_stack([pcm, pcm])
    return pygame.sndarray.make_sound(np.ascontiguousarray(pcm))


def _to_sound(x, gain=0.8):
    x = np.clip(x * gain, -1, 1)
    return make_sound((x * 32767).astype(np.int16))


def render_beeps(text):
    """Whole transmission as one waveform so beeps and HUD events share one clock."""
    sr = C.SAMPLE_RATE
    parts = []
    fade = int(0.010 * sr)
    for is_tone, dur in morse.encode(text):
        n = max(1, int(round(dur * sr)))
        if is_tone:
            t = np.arange(n) / sr
            w = np.sin(2 * np.pi * C.MORSE_FREQ_HZ * t)
            env = np.ones(n)
            k = min(fade, n // 2)
            if k:
                env[:k] = np.linspace(0, 1, k)
                env[-k:] = np.linspace(1, 0, k)
            parts.append(w * env)
        else:
            parts.append(np.zeros(n))
    x = np.concatenate(parts) if parts else np.zeros(sr // 10)
    return _bandpass(x)


def render_static(seconds=10.0):
    rng = np.random.default_rng(1944)
    x = rng.standard_normal(int(seconds * C.SAMPLE_RATE)) * 0.3
    return _bandpass(x)


class Audio:
    CH_BEEPS, CH_STATIC, CH_SPEECH = 0, 1, 2

    def __init__(self, mute=False):
        self.ok = False
        self.mute = mute
        self._static = None
        self._beeps = None
        self._speech_until = 0.0
        if mute:
            return
        try:
            import pygame
            pygame.mixer.pre_init(C.SAMPLE_RATE, -16, 1, 1024)
            pygame.mixer.init(C.SAMPLE_RATE, -16, 1, 1024)
            pygame.mixer.set_num_channels(4)
            self.ok = True
        except Exception as e:
            print(f"[audio] disabled: {e}")

    # ---- helpers ----
    def _chan(self, i):
        import pygame
        return pygame.mixer.Channel(i)

    def prepare_static(self):
        if self.ok and self._static is None:
            self._static = _to_sound(render_static(), gain=1.0)

    # ---- beeps ----
    def play_morse(self, text):
        """Returns the monotonic start time. Events from morse.events() are relative to it."""
        t0 = time.monotonic()
        if not self.ok:
            return t0
        try:
            self._beeps = _to_sound(render_beeps(text))
            self._chan(self.CH_BEEPS).play(self._beeps)
        except Exception as e:
            print(f"[audio] beeps failed: {e}")
        return time.monotonic()

    # ---- static ----
    def start_static(self):
        if not self.ok:
            return
        try:
            self.prepare_static()
            ch = self._chan(self.CH_STATIC)
            ch.set_volume(C.STATIC_GAIN)
            ch.play(self._static, loops=-1)
        except Exception as e:
            print(f"[audio] static failed: {e}")

    def fade_static(self):
        if self.ok:
            self._chan(self.CH_STATIC).fadeout(int(C.STATIC_FADE_S * 1000))

    # ---- speech ----
    def speak(self, sound, text=""):
        """Play a pre-rendered Sound, or if None, hold for a word-count estimate so flow continues."""
        words = max(1, len(text.split()))
        if self.ok and sound is not None:
            try:
                self._chan(self.CH_SPEECH).play(sound)
                self._speech_until = time.monotonic() + sound.get_length()
                return
            except Exception as e:
                print(f"[audio] speech failed: {e}")
        # NOTE: no voice: pretend to speak at ~2.5 words/s so the HUD subtitle gets read.
        self._speech_until = time.monotonic() + 0.6 + words / 2.5

    def speaking(self):
        if self.ok:
            try:
                if self._chan(self.CH_SPEECH).get_busy():
                    return True
            except Exception:
                pass
        return time.monotonic() < self._speech_until

    def play_clip(self, sound, channel=3):
        if self.ok and sound is not None:
            try:
                self._chan(channel).play(sound)
            except Exception as e:
                print(f"[audio] clip failed: {e}")

    def stop_all(self):
        self._speech_until = 0.0
        if self.ok:
            try:
                import pygame
                pygame.mixer.stop()
            except Exception:
                pass
