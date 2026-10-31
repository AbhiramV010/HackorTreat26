"""The run state machine. Non-blocking: call tick() every frame. Gemma only supplies words."""
import time

import config as C
import gemma
import morse
import scan
from picture import Picture, ROBOT36_TOTAL_S

READY, WAKE, RECEIVE, SCAN, REACT, PICTURE, END = "READY", "WAKE", "RECEIVE", "SCAN", "REACT", "PICTURE", "END"

# Former LCD labels, now the HUD status line (changes.md section 3)
STATUS = {READY: "SPIDER STANDBY", WAKE: "RIGOR WAKING", RECEIVE: "RADIO IN", SCAN: "SCANNING", REACT: "THINKING"}


class Session:
    """Everything the HUD draws. Reset wipes it."""

    def __init__(self):
        self.state = READY
        self.status = "SPIDER STANDBY"
        self.status2 = "PRESS SPACE"
        self.theme = None
        self.message = ""
        self.spider_line = ""
        self.scene = ""
        self.reaction = ""
        self.job1 = None
        self.job2 = None
        self.morse_groups = []
        self.revealed = False
        self.readings = []
        self.result = None
        self.subtitle = ""
        self.sensor_failed = False
        self.picture = None
        self.picture_rows = 0
        self.notice = ""


class StateMachine:
    def __init__(self, link, audio, voice, model=C.DEFAULT_MODEL, use_gemma=True):
        self.link, self.audio, self.voice = link, audio, voice
        self.model, self.use_gemma = model, use_gemma
        self.s = Session()
        self.pan_angle = C.PAN_CENTER_DEG
        self.baseline = None
        self.last_readings, self.last_result = [], None
        self.live = {}             # angle -> cm, continuous poll while READY
        self._live_dir = 1
        self._live_angle = C.PAN_CENTER_DEG
        self._live_next = 0.0
        self._ready_seen = False
        self._baseline_collect = None
        self._ack = False
        self._t = time.monotonic()
        self._phase = None
        self._events = []
        self._t_morse = 0.0
        self._t_done = None
        self._speech_queue = []
        self._sweep_sent = 0
        self._t_sweep = 0.0
        self._pan_wait_until = 0.0
        self.lcd("SPIDER STANDBY", "PRESS SPACE")

    # ---------- helpers ----------
    def now(self):
        return time.monotonic()

    def since(self):
        return self.now() - self._t

    def lcd(self, l1, l2=""):
        """The LCD is gone; the former LCD text goes to the HUD status lines."""
        self.s.status, self.s.status2 = l1, l2

    def goto(self, state):
        self.s.state = state
        self.s.status = STATUS.get(state, self.s.status)
        if state in STATUS:
            self.s.status2 = ""
        self._t = self.now()
        self._phase = None

    def say(self, text):
        """Queue a line to speak; subtitle follows it."""
        self._speech_queue.append(text)

    def _pump_speech(self):
        if self.audio.speaking() or not self._speech_queue:
            return
        text = self._speech_queue.pop(0)
        self.s.subtitle = text
        self.audio.speak(self.voice.get(text), text)

    def speech_idle(self):
        return not self._speech_queue and not self.audio.speaking()

    # ---------- external input ----------
    def key(self, name):
        st = self.s.state
        if name == "r":
            self.reset()
        elif name == "space" and st == READY:
            self.start_run()
        elif name == "c" and st == READY and self._baseline_collect is None:
            self._baseline_collect = []
            self.s.notice = "BASELINE SWEEP"
            self.link.send(f"PAN,{C.SWEEP_FROM_DEG}")
            self._pan_wait_until = self.now() + 3.0
            self._ack = False
            self._phase = "baseline_pan"
        elif name == "z" and st == READY:
            self.link.send("ZERO")
            self.pan_angle = C.PAN_CENTER_DEG
            self.s.notice = "ZEROED"

    def reset(self):
        self.audio.stop_all()
        self._speech_queue.clear()
        self.link.send("STOP")
        self.link.send(f"PAN,{C.PAN_CENTER_DEG}")
        self.pan_angle = C.PAN_CENTER_DEG
        self._live_angle = C.PAN_CENTER_DEG
        self._live_next = self.now() + 1.5  # let PAN,90 finish first
        if self.s.readings:
            self.last_readings, self.last_result = self.s.readings, self.s.result
        self.s = Session()
        self._baseline_collect = None
        self.goto(READY)
        self.lcd("SPIDER STANDBY", "PRESS SPACE")

    # ---------- queue ----------
    def _drain(self):
        q = self.link.q
        while not q.empty():
            msg = q.get_nowait()
            kind = msg[0]
            if kind == "READY":
                if self._ready_seen:
                    self.s.notice = "UNO RESET"
                    self.reset()
                self._ready_seen = True
            elif kind == "ACK":
                self._ack = True
            elif kind == "S":
                _, a, cm = msg
                self.pan_angle = a
                if self._baseline_collect is not None:
                    self._baseline_collect.append((a, cm))
                elif self.s.state == READY:
                    self.live[a] = cm
                elif self.s.state == SCAN:
                    self.s.readings.append((a, cm))
                    self.lcd("SCANNING", f"ANGLE {a}")
            elif kind == "SWEEPDONE":
                if self._baseline_collect is not None:
                    self.baseline = {a: cm for a, cm in self._baseline_collect}
                    self._baseline_collect = None
                    self.s.notice = f"BASELINE SAVED ({len(self.baseline)})"
                    self.link.send(f"PAN,{C.PAN_CENTER_DEG}")
                    self._phase = None
                elif self.s.state == SCAN:
                    self._phase = "sweep_done"

    # ---------- run ----------
    def start_run(self):
        self.s = Session()
        self.s.theme = gemma.pick_theme()
        self.s.job1 = gemma.Job(
            gemma.job1_prompt(self.s.theme), self.model, 0.9, C.JOB1_CAP_S, gemma.validate_job1,
            enabled=self.use_gemma,
        )
        self.audio.start_static()
        self.goto(WAKE)
        self.lcd("RIGOR WAKING", "")

    def tick(self):
        self._drain()
        self._pump_speech()
        if self.link.lost:
            self.s.notice = "SERIAL LOST"
        st = self.s.state
        handler = getattr(self, f"_tick_{st.lower()}", None)
        if handler:
            handler()

    def _tick_ready(self):
        if self._phase == "baseline_pan" and (self._ack or self.now() > self._pan_wait_until):
            self.link.send(f"SWEEP,{C.SWEEP_FROM_DEG},{C.SWEEP_TO_DEG},{C.SWEEP_STEP_DEG}")
            self._phase = "baseline_sweep"
            return
        if self._baseline_collect is not None or self.now() < self._live_next:
            return
        # continuous poll: step one angle, ping, repeat every LIVE_POLL_S, bouncing at the sweep ends
        self._live_next = self.now() + C.LIVE_POLL_S
        nxt = self._live_angle + self._live_dir * C.SWEEP_STEP_DEG
        if nxt > C.SWEEP_TO_DEG or nxt < C.SWEEP_FROM_DEG:
            self._live_dir = -self._live_dir
            nxt = self._live_angle + self._live_dir * C.SWEEP_STEP_DEG
        self._live_angle = nxt
        self.pan_angle = nxt
        self.link.send(f"PAN,{nxt}")
        self.link.send("PING")

    def _tick_wake(self):
        j = self.s.job1
        if self.since() < C.WAKE_MIN_S:
            return
        if not (j.done or j.expired(C.JOB1_CAP_S)):
            return
        r = j.result if j.done and j.result else gemma.fallback_job1()
        j.fallback = j.result is None
        self.s.message, self.s.spider_line = r["message"], r["spider_line"]
        self.voice.prerender(self.s.spider_line)
        self.goto(RECEIVE)
        self._events = morse.events(self.s.message)
        self._t_morse = self.audio.play_morse(self.s.message)
        self._t_done = None
        self.lcd("RADIO IN", "")

    def _tick_receive(self):
        s = self.s
        if self._phase == "speak":
            if self.speech_idle():
                self.goto(SCAN)
                self._enter_scan()
            return
        t = self.now() - self._t_morse
        while self._events and self._events[0][0] <= t:
            _, name, arg = self._events.pop(0)
            if name == "letter_start":
                s.morse_groups.append([])
            elif name == "symbol":
                s.morse_groups[-1].append(arg)
                self.lcd("RADIO IN", "".join(s.morse_groups[-1]))
            elif name == "done":
                self._t_done = self.now()
        if self._t_done and self.now() - self._t_done >= C.DECODE_REVEAL_DELAY_S:
            s.revealed = True
            self.lcd("RADIO:", s.message)
            self.audio.fade_static()
            self.say(s.spider_line)
            self._phase = "speak"

    def _enter_scan(self):
        self.say("Scanning.")
        self.link.send(f"PAN,{C.SWEEP_FROM_DEG}")
        self._ack = False
        self._pan_wait_until = self.now() + 3.0
        self._phase = "pan"
        self._sweep_sent = 0
        self.lcd("SCANNING", "ANGLE --")

    def _send_sweep(self):
        self.link.send(f"SWEEP,{C.SWEEP_FROM_DEG},{C.SWEEP_TO_DEG},{C.SWEEP_STEP_DEG}")
        self._sweep_sent += 1
        self._t_sweep = self.now()
        self._phase = "sweep"
        # NOTE: SWEEP_PASSES > 1 is not implemented; one pass is enough for the demo.

    def _tick_scan(self):
        s = self.s
        if self._phase == "pan":
            if self._ack or self.now() > self._pan_wait_until:
                self._send_sweep()
        elif self._phase == "sweep":
            el = self.now() - self._t_sweep
            if not s.readings and el > 1.5 and self._sweep_sent == 1:
                self._send_sweep()
            elif not s.readings and el > 1.5 and self._sweep_sent >= 2:
                self._phase = "sweep_done"
            elif el > 8.0:
                self._phase = "sweep_done"
        elif self._phase == "sweep_done":
            self.link.send(f"PAN,{C.PAN_CENTER_DEG}")
            self.pan_angle = C.PAN_CENTER_DEG
            if not s.readings:
                s.sensor_failed = True
                s.notice = "SENSOR OFFLINE"
                s.result = scan.ScanResult(sensor_failed=True)
                self.say("My sensors are down.")
                self._finish_react(gemma.fallback_job2(s.result))
                self.lcd("SENSOR OFFLINE", "NOTHING FOUND")
                return
            self.goto(REACT)
            s.result = scan.analyse(s.readings, self.baseline)
            s.job2 = gemma.Job(
                gemma.job2_prompt(s.message, s.theme, s.result), self.model, 0.7, C.JOB2_CAP_S,
                lambda t: gemma.validate_job2(t, s.result.threat, gemma.side_word(s.result)),
                enabled=self.use_gemma,
            )
            self.lcd("THINKING", "...")
            self.say("Sensors tingling.")
            self._phase = "think"
            if s.result.threat != "CLEAR":
                # NOTE: webcam open + SSTV encode take a few seconds, so build now while the spider talks
                s.picture = Picture().start()

    def _tick_react(self):
        s, j = self.s, self.s.job2
        if self._phase == "think":
            if j.done or j.expired(C.JOB2_CAP_S):
                r = j.result if j.done and j.result else gemma.fallback_job2(s.result)
                j.fallback = j.result is None
                self._finish_react(r)
        elif self._phase == "speak" and self.speech_idle():
            if s.result.threat != "CLEAR" and not s.sensor_failed and s.picture:
                self.goto(PICTURE)
                self._phase = "build"
            else:
                self.goto(END)

    def _finish_react(self, r):
        s = self.s
        if s.state != REACT:  # sensor-failed path arrives from SCAN
            self.goto(REACT)
        s.scene, s.reaction = r["scene"], r["reaction"]
        res = s.result
        if res.threat == "CLEAR":
            self.lcd("CLEAR", "NOTHING FOUND")
        else:
            n = str(res.people_estimate) if res.people_estimate < 9 else "9+"
            self.lcd(f"HUMANS: {n}", f"NEAREST {res.nearest.dist_cm / 100:.1f} M")
        self.voice.prerender(s.scene)
        self.voice.prerender(s.reaction)
        self.say(s.scene)
        self.say(s.reaction)
        self._phase = "speak"

    def _tick_picture(self):
        s, p = self.s, self.s.picture
        if self.since() > C.PICTURE_CAP_S:
            self.goto(END)
            return
        if self._phase == "build":
            if not p.done:
                return
            if p.skip or p.image is None:
                self.goto(END)
                return
            self.audio.play_clip(p.sound)
            self._t_pic = self.now()
            self._phase = "play"
            s.notice = "CARRIER: LOST" if p.fallback else "SSTV"
        elif self._phase == "play":
            el = self.now() - self._t_pic
            s.picture_rows = min(C.PICTURE_H, int(el / ROBOT36_TOTAL_S * C.PICTURE_H))
            if el >= C.PICTURE_PLAY_S:
                self.goto(END)

    def _tick_end(self):
        pass
