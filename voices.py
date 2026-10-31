"""Spider voice: Piper first, then pyttsx3 (SAPI), then nothing. Renders to pygame Sounds, cached by text."""
import io
import os
import tempfile
import threading
import wave

import numpy as np

import config as C

FIXED_LINES = ["Scanning.", "Sensors tingling.", "My sensors are down."]


class Voice:
    def __init__(self, enabled=True):
        self.backend = None
        self._cache = {}
        self._lock = threading.Lock()
        self._pending = set()
        if not enabled:
            return
        self._init_piper() or self._init_pyttsx3()
        print(f"[voice] backend: {self.backend or 'none (HUD text only)'}")

    # ---- backends ----
    def _init_piper(self):
        try:
            from piper import PiperVoice
            if not os.path.exists(C.SPIDER_VOICE):
                print(f"[voice] piper model missing at {C.SPIDER_VOICE}")
                return False
            self._piper = PiperVoice.load(C.SPIDER_VOICE)
            self.backend = "piper"
            return True
        except Exception as e:
            print(f"[voice] piper unavailable: {e}")
            return False

    def _init_pyttsx3(self):
        try:
            import pyttsx3
            self._pyttsx3 = pyttsx3
            self._pyttsx3_lock = threading.Lock()
            self.backend = "pyttsx3"
            return True
        except Exception as e:
            print(f"[voice] pyttsx3 unavailable: {e}")
            return False

    # ---- rendering ----
    def _render_wav_bytes(self, text):
        if self.backend == "piper":
            buf = io.BytesIO()
            with wave.open(buf, "wb") as w:
                try:
                    from piper import SynthesisConfig
                    cfg = SynthesisConfig(length_scale=C.PIPER_LENGTH_SCALE)
                    self._piper.synthesize_wav(text, w, syn_config=cfg)
                except Exception:
                    # NOTE: older piper-tts API
                    self._piper.synthesize(text, w, length_scale=C.PIPER_LENGTH_SCALE)
            return buf.getvalue()
        if self.backend == "pyttsx3":
            # NOTE: pyttsx3 is not thread safe and needs a fresh engine per run on Windows.
            with self._pyttsx3_lock:
                fd, path = tempfile.mkstemp(suffix=".wav")
                os.close(fd)
                try:
                    eng = self._pyttsx3.init()
                    eng.setProperty("rate", 165)
                    eng.save_to_file(text, path)
                    eng.runAndWait()
                    try:
                        eng.stop()
                    except Exception:
                        pass
                    with open(path, "rb") as f:
                        return f.read()
                finally:
                    try:
                        os.remove(path)
                    except OSError:
                        pass
        return None

    def _wav_to_sound(self, data):
        import pygame
        with wave.open(io.BytesIO(data), "rb") as w:
            sr, ch, sw, n = w.getframerate(), w.getnchannels(), w.getsampwidth(), w.getnframes()
            raw = w.readframes(n)
        if sw == 2:
            x = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768
        else:
            x = (np.frombuffer(raw, dtype=np.uint8).astype(np.float32) - 128) / 128
        if ch > 1:
            x = x.reshape(-1, ch).mean(axis=1)
        if sr != C.SAMPLE_RATE:
            idx = np.linspace(0, len(x) - 1, int(len(x) * C.SAMPLE_RATE / sr))
            x = np.interp(idx, np.arange(len(x)), x)
        pcm = (np.clip(x, -1, 1) * 32767).astype(np.int16)
        return pygame.sndarray.make_sound(np.ascontiguousarray(pcm))

    def render(self, text):
        """Blocking. Returns a Sound or None. Cached by text."""
        if not text or self.backend is None:
            return None
        with self._lock:
            if text in self._cache:
                return self._cache[text]
        snd = None
        try:
            data = self._render_wav_bytes(text)
            if data:
                snd = self._wav_to_sound(data)
        except Exception as e:
            print(f"[voice] render failed: {e}")
        with self._lock:
            self._cache[text] = snd
            self._pending.discard(text)
        return snd

    def prerender(self, text):
        """Start rendering in the background."""
        if not text or self.backend is None:
            return
        with self._lock:
            if text in self._cache or text in self._pending:
                return
            self._pending.add(text)
        threading.Thread(target=self.render, args=(text,), daemon=True).start()

    def get(self, text):
        """Non-blocking: Sound if ready, else None."""
        with self._lock:
            return self._cache.get(text)

    def ready(self, text):
        with self._lock:
            return text in self._cache
