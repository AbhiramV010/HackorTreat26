"""Robot36 picture: webcam frame -> face crop -> SSTV audio + image for the HUD. All in memory.

build() runs in a background thread and never raises; on any failure it returns the fallback clip.
"""
import os
import random
import tempfile
import threading
import time

import numpy as np

import config as C

ROBOT36_TOTAL_S = 36.0  # full Robot36 frame time; the HUD reveals rows against this


class Picture:
    def __init__(self):
        self.image = None      # PIL image 320x240
        self.sound = None      # pygame Sound (first PICTURE_PLAY_S seconds)
        self.fallback = False
        self.done = False
        self.skip = False      # no faces: skip the picture entirely
        self.error = None
        self._t0 = time.monotonic()

    def start(self):
        threading.Thread(target=self._run, daemon=True).start()
        return self

    # ---- pipeline ----
    def _run(self):
        try:
            img = self._capture_face()
            if img is None and self.skip:
                self.done = True
                return
        except Exception as e:
            self.error = f"camera: {e}"[:80]
            img = None
        if img is None:
            img = self._fallback_image()
            self.fallback = True
        self.image = img
        try:
            self.sound = self._encode(img)
        except Exception as e:
            self.error = f"sstv: {e}"[:80]
            self.sound = None
        self.done = True

    def _capture_face(self):
        import cv2
        cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1920)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 1080)
        ok, frame = False, None
        for _ in range(5):  # first frames are often dark
            ok, frame = cap.read()
        cap.release()
        if not ok or frame is None:
            raise RuntimeError("no frame")
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        cascade = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
        faces = cascade.detectMultiScale(gray, 1.2, 5, minSize=(40, 40))
        if len(faces) == 0:
            self.skip = True
            return None
        big = [f for f in faces if f[2] >= 60]
        x, y, w, h = random.choice(big) if big else max(faces, key=lambda f: f[2])
        # head and shoulders crop, 4:3, face in the top 46%
        cw = int(w * 2.6)
        ch = int(cw * 3 / 4)
        cx = x + w // 2
        top = int(y + h * 0.5 - ch * 0.46)
        left = cx - cw // 2
        H, W = frame.shape[:2]
        left, top = max(0, min(left, W - cw)), max(0, min(top, H - ch))
        crop = frame[top:top + ch, left:left + cw]
        crop = cv2.resize(crop, (C.PICTURE_W, C.PICTURE_H), interpolation=cv2.INTER_AREA)
        rgb = cv2.cvtColor(crop, cv2.COLOR_BGR2RGB).astype(np.float32)
        rgb[..., 0] *= 0.92
        rgb[..., 2] *= 1.08
        from PIL import Image
        return self._band(Image.fromarray(np.clip(rgb, 0, 255).astype(np.uint8)), "CARRIER")

    def _band(self, img, text):
        from PIL import ImageDraw, ImageFont
        d = ImageDraw.Draw(img)
        d.rectangle([0, 0, C.PICTURE_W, 30], fill=(0, 0, 0))
        try:
            font = ImageFont.truetype("consola.ttf", 20)
        except Exception:
            font = ImageFont.load_default()
        d.text((8, 5), text, fill=(255, 176, 0), font=font)
        return img

    def _fallback_image(self):
        from PIL import Image, ImageDraw
        img = Image.new("RGB", (C.PICTURE_W, C.PICTURE_H), (0, 0, 0))
        d = ImageDraw.Draw(img)
        for x in range(0, C.PICTURE_W, 32):
            d.line([(x, 30), (x, C.PICTURE_H)], fill=(60, 40, 0))
        for y in range(30, C.PICTURE_H, 32):
            d.line([(0, y), (C.PICTURE_W, y)], fill=(60, 40, 0))
        return self._band(img, "CARRIER: LOST")

    def _encode(self, img):
        from pysstv.color import Robot36
        import pygame
        sstv = Robot36(img.convert("RGB"), C.SAMPLE_RATE, 16)
        # NOTE: pysstv only writes to a file path; it goes to a temp file and is deleted right after.
        fd, path = tempfile.mkstemp(suffix=".wav")
        os.close(fd)
        try:
            sstv.write_wav(path)
            snd = pygame.mixer.Sound(path)
        finally:
            try:
                os.remove(path)
            except OSError:
                pass
        # cut to the first PICTURE_PLAY_S seconds
        from audio import make_sound
        arr = pygame.sndarray.array(snd)
        n = int(C.PICTURE_PLAY_S * C.SAMPLE_RATE)
        return make_sound(np.ascontiguousarray(arr[:n]))
