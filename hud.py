"""Fullscreen pygame HUD: header band, Morse panel, radar panel, subtitle bar, details screen."""
import math

import pygame

import config as C
import morse
from state import READY, SCAN, PICTURE, END

AMBER, DIM, BG = C.HUD_AMBER, C.HUD_DIM, C.HUD_BG
FAINT = (50, 34, 0)
PANEL = (10, 7, 0)


class Hud:
    def __init__(self, windowed=False):
        pygame.init()
        if windowed:
            self.screen = pygame.display.set_mode((1280, 720))
        else:
            self.screen = pygame.display.set_mode((0, 0), pygame.FULLSCREEN)
        pygame.display.set_caption(C.COMPANION_NAME)
        self.w, self.h = self.screen.get_size()
        k = self.h / 1080  # scale fonts with the screen so 720p windows don't overflow
        name = "consolas"
        self.f_huge = pygame.font.SysFont(name, max(44, int(80 * k)), bold=True)
        self.f_big = pygame.font.SysFont(name, max(36, int(60 * k)))
        self.f_sub = pygame.font.SysFont(name, max(26, int(40 * k)))
        self.f_label = pygame.font.SysFont(name, max(18, int(24 * k)), bold=True)
        self.f_small = pygame.font.SysFont(name, max(14, int(20 * k)))
        self.f_detail = pygame.font.SysFont(name, max(16, int(24 * k)))
        self.details = False
        self._pic_surf = None
        self._pic_img = None
        self.margin = int(32 * k)
        self.header_h = int(150 * k)
        self.footer_h = int(170 * k)

    # ---- helpers ----
    def text(self, s, font, x, y, color=AMBER, center=False, right=False):
        surf = font.render(s, True, color)
        r = surf.get_rect()
        if center:
            r.center = (x, y)
        elif right:
            r.topright = (x, y)
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

    def panel(self, rect, title):
        pygame.draw.rect(self.screen, PANEL, rect)
        pygame.draw.rect(self.screen, DIM, rect, 2)
        # title tab
        tw = self.f_label.size(title)[0] + 24
        tab = pygame.Rect(rect.x + 16, rect.y - self.f_label.get_height() // 2 - 4, tw, self.f_label.get_height() + 8)
        pygame.draw.rect(self.screen, BG, tab)
        pygame.draw.rect(self.screen, DIM, tab, 2)
        self.text(title, self.f_label, tab.centerx, tab.centery, AMBER, center=True)

    # ---- draw ----
    def draw(self, sm):
        self.screen.fill(BG)
        if self.details:
            self._draw_details(sm)
        else:
            self._draw_main(sm)
        pygame.display.flip()

    def _layout(self):
        m = self.margin
        top = self.header_h + m
        bottom = self.h - self.footer_h
        half = (self.w - 3 * m) // 2
        left = pygame.Rect(m, top, half, bottom - top - m)
        right = pygame.Rect(2 * m + half, top, half, bottom - top - m)
        return left, right

    def _draw_header(self, sm):
        s = sm.s
        m = self.margin
        band = pygame.Rect(0, 0, self.w, self.header_h)
        pygame.draw.rect(self.screen, PANEL, band)
        pygame.draw.line(self.screen, DIM, (0, self.header_h), (self.w, self.header_h), 2)
        status = s.status
        if s.state == READY and sm.link.lost:
            status = "SERIAL LOST"
        self.text(status, self.f_huge, self.w // 2, self.header_h // 2 - (18 if s.status2 else 0), center=True)
        if s.status2:
            self.text(s.status2, self.f_sub, self.w // 2, self.header_h // 2 + 38, DIM, center=True)
        # corners
        self.text(f"{C.COMPANION_NAME.upper()}  //  1944", self.f_label, m, m // 2, DIM)
        self.text(f"PAN {sm.pan_angle:>3}°", self.f_label, self.w - m, m // 2, DIM, right=True)
        if s.notice:
            self.text(s.notice, self.f_small, self.w - m, m // 2 + self.f_label.get_height() + 4, AMBER, right=True)
        self.text(f"STATE {s.state}", self.f_small, m, m // 2 + self.f_label.get_height() + 4, FAINT)

    def _draw_footer(self, sm):
        s = sm.s
        m = self.margin
        box = pygame.Rect(m, self.h - self.footer_h + m // 2, self.w - 2 * m, self.footer_h - m)
        pygame.draw.rect(self.screen, PANEL, box)
        pygame.draw.rect(self.screen, DIM, box, 2)
        if s.subtitle:
            lines = self.wrap(s.subtitle, self.f_sub, box.w - 2 * m)[-2:]
            lh = self.f_sub.get_height() + 6
            y0 = box.centery - (len(lines) * lh) // 2 + lh // 2
            for i, ln in enumerate(lines):
                self.text(f"“{ln}”" if len(lines) == 1 else ln, self.f_sub, box.centerx, y0 + i * lh, center=True)
        else:
            hint = "SPACE start   R reset   TAB details   C baseline   Z zero   ESC quit"
            self.text(hint, self.f_small, box.centerx, box.centery, DIM, center=True)

    def _draw_main(self, sm):
        s = sm.s
        self._draw_header(sm)
        self._draw_footer(sm)
        left, right = self._layout()

        # ---- Morse panel ----
        self.panel(left, "RADIO")
        inner = left.inflate(-2 * self.margin, -2 * self.margin)
        if s.state == READY:
            self.text("PRESS SPACE", self.f_big, inner.centerx, inner.centery - 30, center=True)
            self.text("to receive a transmission", self.f_small, inner.centerx, inner.centery + 30, DIM, center=True)
        else:
            x, y = inner.x, inner.y
            gh = self.f_big.get_height() + 16
            for g in s.morse_groups or []:
                code = "".join(g).replace(".", "•").replace("-", "—")
                wdt = self.f_big.size(code)[0] + 28
                if x + wdt > inner.right and x > inner.x:
                    x, y = inner.x, y + gh
                self.text(code, self.f_big, x, y)
                x += wdt
            if s.revealed:
                y2 = y + gh + 20
                pygame.draw.line(self.screen, DIM, (inner.x, y2), (inner.right, y2), 1)
                self.text("DECODED", self.f_label, inner.x, y2 + 10, DIM)
                for i, ln in enumerate(self.wrap(s.message, self.f_huge, inner.w)):
                    self.text(ln, self.f_huge, inner.x, y2 + 40 + i * (self.f_huge.get_height() + 4))
            elif s.morse_groups:
                self.text("decoding…", self.f_small, inner.x, inner.bottom - self.f_small.get_height(), DIM)

        # ---- Radar / picture panel ----
        show_pic = s.state == PICTURE or (s.state == END and s.picture and s.picture.image and not s.picture.skip)
        self.panel(right, "SSTV" if show_pic else "SWEEP")
        if show_pic:
            self._draw_picture(s, right)
        else:
            if s.readings:
                readings, result, greyed, live = s.readings, s.result, False, False
            elif s.state == READY and sm.live:
                readings, result, greyed, live = sorted(sm.live.items()), None, False, True
            else:
                readings, result, greyed, live = sm.last_readings, sm.last_result, True, False
            self._draw_radar(right, readings, result, sm.pan_angle, greyed, s.state == SCAN, live)

    def _draw_radar(self, rect, readings, result, pan_angle, greyed, sweeping, live=False):
        col = DIM if greyed else AMBER
        inner = rect.inflate(-2 * self.margin, -2 * self.margin)
        radius = min(inner.w // 2 - 10, inner.h - self.f_small.get_height() - 20)
        cx = inner.centerx
        cy = inner.y + 10 + radius

        def pt(a, d):
            r = min(d, C.MAX_VALID_CM) / C.MAX_VALID_CM * radius
            th = math.radians(180 - a)
            return int(cx + r * math.cos(th)), int(cy - r * math.sin(th))

        # rings and spokes
        for ring in (100, 200, 300):
            r = ring / 300 * radius
            pygame.draw.arc(self.screen, DIM if ring == 300 else FAINT, pygame.Rect(cx - r, cy - r, 2 * r, 2 * r), 0, math.pi, 2)
            self.text(f"{ring / 100:.0f} m", self.f_small, cx + 6, cy - int(r) + 4, DIM)
        for a in (30, 60, 90, 120, 150):
            pygame.draw.line(self.screen, FAINT, (cx, cy), pt(a, C.MAX_VALID_CM), 1)
        pygame.draw.line(self.screen, DIM, (cx - radius, cy), (cx + radius, cy), 2)
        self.text("L", self.f_label, cx - radius, cy + 6, DIM)
        self.text("R", self.f_label, cx + radius, cy + 6, DIM, right=True)
        # spider
        pygame.draw.circle(self.screen, col, (cx, cy), 9)
        pygame.draw.circle(self.screen, BG, (cx, cy), 4)

        # the true map: join the readings into the room outline the sensor measured,
        # shading the open space between the spider and the first echo at each angle
        ordered = sorted(readings, key=lambda r: r[0])
        outline = [pt(a, d if d > 0 else C.MAX_VALID_CM) for a, d in ordered]
        if len(outline) >= 2:
            poly = [(cx, cy)] + outline
            fill = pygame.Surface(self.screen.get_size(), pygame.SRCALPHA)
            pygame.draw.polygon(fill, (255, 176, 0, 28 if greyed else 55), poly)
            self.screen.blit(fill, (0, 0))
            pygame.draw.lines(self.screen, col, False, outline, 3)
        for a, d in ordered:
            if d <= 0:
                pygame.draw.circle(self.screen, FAINT, pt(a, C.MAX_VALID_CM), 4)
            else:
                pygame.draw.circle(self.screen, col, pt(a, d), 5)
                pygame.draw.circle(self.screen, BG, pt(a, d), 2)

        if result:
            for c in result.contacts:
                p = pt(c.angle, c.dist_cm)
                pygame.draw.circle(self.screen, PANEL, p, 26)
                pygame.draw.circle(self.screen, col, p, 26, 3)
                self.text(f"~{c.people}", self.f_label, p[0], p[1], col, center=True)
                if c is result.nearest:
                    pygame.draw.circle(self.screen, col, p, 40, 2)
                    self.text(f"{c.dist_cm / 100:.1f} m", self.f_small, p[0], p[1] + 54, col, center=True)

        if sweeping or live:
            x, y = pt(pan_angle, C.MAX_VALID_CM)
            pygame.draw.line(self.screen, AMBER if sweeping else DIM, (cx, cy), (x, y), 3 if sweeping else 2)
        label = "SWEEPING" if sweeping else ("LIVE" if live else ("LAST RUN" if greyed and readings else ("NO DATA" if greyed else "CONTACTS")))
        self.text(label, self.f_small, inner.right, inner.y, DIM, right=True)

    def _draw_picture(self, s, rect):
        p = s.picture
        if p.image is not self._pic_img:
            self._pic_img = p.image
            data = p.image.convert("RGB").tobytes()
            self._pic_surf = pygame.image.fromstring(data, p.image.size, "RGB")
        inner = rect.inflate(-2 * self.margin, -2 * self.margin)
        scale = max(1, min(inner.w // C.PICTURE_W, inner.h // C.PICTURE_H))
        pw, ph = C.PICTURE_W * scale, C.PICTURE_H * scale
        x, y = inner.centerx - pw // 2, inner.centery - ph // 2
        rows = C.PICTURE_H if s.state == END else s.picture_rows
        pygame.draw.rect(self.screen, FAINT, (x, y, pw, ph))
        if rows > 0:
            sub = self._pic_surf.subsurface(pygame.Rect(0, 0, C.PICTURE_W, rows))
            self.screen.blit(pygame.transform.scale(sub, (pw, rows * scale)), (x, y))
            if rows < C.PICTURE_H:
                pygame.draw.line(self.screen, AMBER, (x, y + rows * scale), (x + pw, y + rows * scale), 2)
        pygame.draw.rect(self.screen, DIM, (x - 2, y - 2, pw + 4, ph + 4), 2)
        self.text("ROBOT36  •  hold the phone to the speaker", self.f_small, inner.centerx, y + ph + 20, DIM, center=True)

    def _draw_details(self, sm):
        s = sm.s
        m = self.margin
        self.text("DETAILS", self.f_label, m, m // 2, DIM)
        self.text("TAB to return", self.f_small, self.w - m, m // 2, DIM, right=True)
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
        y = m + self.f_label.get_height() + 10
        lh = self.f_detail.get_height() + 4
        for ln in lines:
            for sub in self.wrap(ln, self.f_detail, self.w - 2 * m) or [""]:
                self.text(sub, self.f_detail, m, y, DIM if ln.startswith("CORNERS") else AMBER)
                y += lh
