"""Fullscreen pygame HUD: status band, Morse panel, radar, subtitle, details screen."""
import math

import pygame

import config as C
import morse
from state import READY, SCAN, PICTURE, END

AMBER, DIM, BG = C.HUD_AMBER, C.HUD_DIM, C.HUD_BG


class Hud:
    def __init__(self, windowed=False):
        pygame.init()
        if windowed:
            self.screen = pygame.display.set_mode((1280, 720))
        else:
            self.screen = pygame.display.set_mode((0, 0), pygame.FULLSCREEN)
        pygame.display.set_caption(C.COMPANION_NAME)
        self.w, self.h = self.screen.get_size()
        name = "consolas"
        self.f_big = pygame.font.SysFont(name, 60)
        self.f_huge = pygame.font.SysFont(name, 80)
        self.f_sub = pygame.font.SysFont(name, 40)
        self.f_small = pygame.font.SysFont(name, 22)
        self.f_detail = pygame.font.SysFont(name, 26)
        self.details = False
        self._pic_surf = None
        self._pic_img = None

    # ---- helpers ----
    def text(self, s, font, x, y, color=AMBER, center=False):
        surf = font.render(s, True, color)
        r = surf.get_rect()
        if center:
            r.center = (x, y)
        else:
            r.topleft = (x, y)
        self.screen.blit(surf, r)
        return r

    def wrap(self, s, font, maxw):
        words, lines, cur = s.split(), [], ""
        for w in words:
            t = (cur + " " + w).strip()
            if font.size(t)[0] > maxw and cur:
                lines.append(cur)
                cur = w
            else:
                cur = t
        if cur:
            lines.append(cur)
        return lines

    # ---- draw ----
    def draw(self, sm):
        s = sm.s
        self.screen.fill(BG)
        if self.details:
            self._draw_details(sm)
        else:
            self._draw_main(sm)
        pygame.display.flip()

    def _draw_main(self, sm):
        s = sm.s
        status = s.status
        if s.state == READY and sm.link.lost:
            status = "SERIAL LOST"
        self.text(status, self.f_huge, self.w // 2, 60, center=True)
        if s.status2:
            self.text(s.status2, self.f_sub, self.w // 2, 120, center=True)
        if s.notice:
            self.text(s.notice, self.f_small, self.w - 20 - self.f_small.size(s.notice)[0], 20, DIM)
        self.text(f"PAN {sm.pan_angle}  (joystick / l r c on the Uno)", self.f_small, 20, 20, DIM)

        # Morse panel (left half)
        px, py = 60, 160
        if s.state == READY:
            self.text("PRESS SPACE", self.f_big, self.w // 4, self.h // 2, center=True)
        else:
            x, y = px, py
            groups = s.morse_groups or []
            for g in groups:
                code = "".join(g)
                wdt = self.f_big.size(code + " ")[0]
                if x + wdt > self.w // 2 - 20:
                    x, y = px, y + 70
                self.text(code, self.f_big, x, y)
                x += wdt + 20
            if s.revealed:
                lines = self.wrap(s.message, self.f_huge, self.w // 2 - 80)
                for i, ln in enumerate(lines):
                    self.text(ln, self.f_huge, px, y + 110 + i * 90)

        # Radar (right half) or picture
        if s.state == PICTURE or (s.state == END and s.picture and s.picture.image and not s.picture.skip):
            self._draw_picture(s)
        else:
            readings = s.readings if s.readings else sm.last_readings
            result = s.result if s.readings else sm.last_result
            greyed = not s.readings
            self._draw_radar(readings, result, sm.pan_angle, greyed, s.state == SCAN)

        # Subtitle
        if s.subtitle:
            lines = self.wrap(s.subtitle, self.f_sub, self.w - 80)
            for i, ln in enumerate(lines[-3:]):
                self.text(ln, self.f_sub, self.w // 2, self.h - 120 + i * 44, center=True)

    def _draw_radar(self, readings, result, pan_angle, greyed, sweeping):
        col = DIM if greyed else AMBER
        cx = self.w * 3 // 4
        cy = self.h // 2 + 150
        radius = min(self.w // 4 - 40, self.h // 2 - 20)

        def pt(a, d):
            r = min(d, C.MAX_VALID_CM) / C.MAX_VALID_CM * radius
            th = math.radians(180 - a)
            return int(cx + r * math.cos(th)), int(cy - r * math.sin(th))

        for ring in (100, 200, 300):
            r = ring / 300 * radius
            rect = pygame.Rect(cx - r, cy - r, 2 * r, 2 * r)
            pygame.draw.arc(self.screen, DIM, rect, 0, math.pi, 1)
            self.text(f"{ring}", self.f_small, cx + int(r) - 30, cy - 24, DIM)
        pygame.draw.line(self.screen, DIM, (cx - radius, cy), (cx + radius, cy), 1)
        # spider
        pygame.draw.circle(self.screen, col, (cx, cy), 8)

        for a, d in readings:
            if d <= 0:
                pygame.draw.circle(self.screen, DIM, pt(a, C.MAX_VALID_CM), 3)
            else:
                pygame.draw.circle(self.screen, col, pt(a, d), 4)

        if result:
            for c in result.contacts:
                p = pt(c.angle, c.dist_cm)
                pygame.draw.circle(self.screen, col, p, 26, 2)
                self.text(f"~{c.people}", self.f_small, p[0], p[1], col, center=True)
                if c is result.nearest:
                    pygame.draw.circle(self.screen, col, p, 38, 2)

        if sweeping or greyed is False:
            x, y = pt(pan_angle, C.MAX_VALID_CM)
            pygame.draw.line(self.screen, AMBER if sweeping else DIM, (cx, cy), (x, y), 2)

    def _draw_picture(self, s):
        p = s.picture
        if p.image is not self._pic_img:
            self._pic_img = p.image
            data = p.image.convert("RGB").tobytes()
            self._pic_surf = pygame.image.fromstring(data, p.image.size, "RGB")
        rows = C.PICTURE_H if s.state == END else s.picture_rows
        scale = 2
        area = pygame.Rect(0, 0, C.PICTURE_W, rows)
        if rows > 0:
            sub = self._pic_surf.subsurface(area)
            big = pygame.transform.scale(sub, (C.PICTURE_W * scale, rows * scale))
            x = self.w * 3 // 4 - C.PICTURE_W * scale // 2
            y = self.h // 2 - C.PICTURE_H * scale // 2
            self.screen.blit(big, (x, y))
            pygame.draw.rect(self.screen, DIM, (x - 2, y - 2, C.PICTURE_W * scale + 4, C.PICTURE_H * scale + 4), 2)
        self.text("ROBOT36", self.f_small, self.w * 3 // 4, self.h // 2 + C.PICTURE_H + 30, DIM, center=True)

    def _draw_details(self, sm):
        s = sm.s
        lines = [f"state {s.state}   theme {s.theme}   message {s.message!r}"]
        for name, j in (("job1", s.job1), ("job2", s.job2)):
            if j is None:
                lines.append(f"{name}: not run")
            else:
                st = "pending" if not j.done else ("FALLBACK" if j.fallback else "ok")
                lines.append(f"{name}: {st}  {j.elapsed:.1f}s  {j.error or ''}")
        lines.append(f"spider_line: {s.spider_line}")
        lines.append(f"scene: {s.scene}")
        lines.append(f"reaction: {s.reaction}")
        if s.sensor_failed:
            lines.append("sensor_failed: True")
        lines.append("readings: " + "  ".join(f"{a}:{d}" for a, d in s.readings))
        if s.result:
            r = s.result
            lines.append(f"threat {r.threat}  people {r.people_estimate}  close {r.close}")
            for c in r.contacts:
                lines.append(f"  contact {c.angle:.0f}deg {c.dist_cm:.0f}cm w{c.width_deg:.0f} {c.side} ~{c.people}")
        if sm.baseline:
            lines.append(f"baseline: {len(sm.baseline)} angles")
        lines.append(f"morse: {morse.to_code(s.message)}")
        lines.append("")
        lines.append("CORNERS CUT: picture stage coded but unverified on hardware | no joystick VRy | tap key, leg servo, "
                     "TWITCH unused | firmware sensor test is one ping per reading | stepper position dead-reckoned, "
                     "recentre with c after a stall | stepper not verified above 10 RPM | Gemma, speech, Morse untested "
                     "on hardware | LCD and eyes removed | SWEEP_PASSES>1 not implemented | Notion packing list stale")
        y = 30
        for ln in lines:
            for sub in self.wrap(ln, self.f_detail, self.w - 60):
                self.text(sub, self.f_detail, 30, y)
                y += 30
