// Rigor spider firmware. Serial at 115200, lines end in \n.
// Uno -> laptop: READY, S,<angle>,<cm>, SWEEPDONE, ACK
// Laptop -> Uno: SWEEP,from,to,step  STOP  PING  PAN,deg  ZERO  TWITCH,n
// Single keys (hardware test): a all, s sensor, m stepper, j joystick readout, l/r 10 deg, c centre
// Centre the head by hand before powering on: position is dead-reckoned from 0 steps = 90 degrees.
//
// Corners cut (see changes.md section 9):
//  - no LCD, no eyes: LiquidCrystal and EYES are gone. The old D command is ignored.
//  - sensor test is one ping per reading; PING/SWEEP still use the median of 3.
//  - position is dead-reckoned, a stall is not detected. Recentre with c.
//  - joystick VRy, tap key and leg servo are not wired. TWITCH is accepted but does nothing unless legAttached.

#include <Stepper.h>
#include <Servo.h>

const int TRIG = 7;
const int ECHO = 8;
const int JOY_X = A1;      // VRx
const int JOY_SW = 3;      // SW, INPUT_PULLUP, pressed = LOW
const int SERVO_PIN = 10;
const long STEPS_PER_REV = 2048;
const int PAN_RPM = 10;    // do not go above 12
const int PAN_SETTLE_MS = 150;
const int PINGS_PER_ANGLE = 3;
const int PING_GAP_MS = 30;
const unsigned long ECHO_TIMEOUT_US = 25000;
const int DIR = 1;         // flip to -1 if left and right are reversed
const int JOY_CHUNK = 4;   // steps per loop while the button is held
const int JOY_LOW = 450, JOY_HIGH = 570;  // dead zone
const int MIN_DEG = 20, MAX_DEG = 160;

Stepper pan(STEPS_PER_REV, A2, A4, A3, A5);  // IN1, IN3, IN2, IN4: keep this order
Servo leg;
bool legAttached = false;

long pos = 0;              // steps from centre; 0 = 90 degrees
bool readout = false;
bool joyHeld = false;
bool lastBtn = false;

char lineBuf[64];
int lineLen = 0;

// ---------- stepper ----------
long degToSteps(int deg) { return lround((deg - 90) * (double)STEPS_PER_REV / 360.0); }
int posDeg() { return 90 + (int)lround(pos * 360.0 / STEPS_PER_REV); }
const long MIN_STEPS = degToSteps(MIN_DEG);
const long MAX_STEPS = degToSteps(MAX_DEG);

void release() {
  digitalWrite(A2, LOW); digitalWrite(A3, LOW); digitalWrite(A4, LOW); digitalWrite(A5, LOW);
}

// moves n steps and keeps the coils energized; refuses to pass the limits
bool stepHeld(long n) {
  long target = pos + n;
  if (target < MIN_STEPS || target > MAX_STEPS) return false;
  pan.step((int)(n * DIR));
  pos = target;
  return true;
}

// moves n steps, settles and releases
bool stepBy(long n) {
  bool ok = stepHeld(n);
  unsigned long t0 = millis();
  while (millis() - t0 < (unsigned long)PAN_SETTLE_MS) {}
  release();
  return ok;
}

void panTo(int deg) {
  deg = constrain(deg, MIN_DEG, MAX_DEG);
  stepBy(degToSteps(deg) - pos);
}

// ---------- sensor ----------
long pingOnce() {
  digitalWrite(TRIG, LOW); delayMicroseconds(2);
  digitalWrite(TRIG, HIGH); delayMicroseconds(10);
  digitalWrite(TRIG, LOW);
  unsigned long d = pulseIn(ECHO, HIGH, ECHO_TIMEOUT_US);
  return d == 0 ? 0 : (long)(d / 58);
}

long readingCm() {
  long v[PINGS_PER_ANGLE];
  for (int i = 0; i < PINGS_PER_ANGLE; i++) {
    v[i] = pingOnce();
    if (i < PINGS_PER_ANGLE - 1) delay(PING_GAP_MS);
  }
  if (v[0] > v[1]) { long t = v[0]; v[0] = v[1]; v[1] = t; }
  if (v[1] > v[2]) { long t = v[1]; v[1] = v[2]; v[2] = t; }
  if (v[0] > v[1]) { long t = v[0]; v[0] = v[1]; v[1] = t; }
  return v[1];
}

void sendReading(int angle) {
  Serial.print("S,"); Serial.print(angle); Serial.print(","); Serial.println(readingCm());
}

bool stopRequested() {
  while (Serial.available()) {
    char c = Serial.read();
    if (c == '\n' || c == '\r') {
      lineBuf[lineLen] = 0;
      bool stop = strncmp(lineBuf, "STOP", 4) == 0;
      lineLen = 0;
      if (stop) return true;
    } else if (lineLen < 63) {
      lineBuf[lineLen++] = c;
    }
  }
  return false;
}

void sweep(int from, int to, int step) {
  if (step <= 0) step = 10;
  int dir = to >= from ? 1 : -1;
  for (int a = from; dir > 0 ? a <= to : a >= to; a += dir * step) {
    if (stopRequested()) break;
    panTo(a);
    sendReading(a);
  }
  Serial.println("SWEEPDONE");
}

void twitch(int n) {
  if (!legAttached) return;
  for (int i = 0; i < n; i++) { leg.write(80); delay(120); leg.write(100); delay(120); }
  leg.write(90);
}

// ---------- hardware tests ----------
void sensorTest() {
  Serial.println("sensor test: 5 readings (one ping each)");
  for (int i = 0; i < 5; i++) {
    Serial.print("  "); Serial.print(pingOnce()); Serial.println(" cm");
    delay(200);
  }
}

void stepperTest() {
  Serial.println("stepper test: 20, 160, 90");
  panTo(20);  Serial.println("  at 20");
  panTo(160); Serial.println("  at 160");
  panTo(90);  Serial.println("  at 90");
  pos = 0;
  Serial.println("  position counter reset to 0");
}

// ---------- joystick, runs every loop ----------
void joystick() {
  bool btn = digitalRead(JOY_SW) == LOW;
  int x = analogRead(JOY_X);
  if (btn != lastBtn) {
    if (readout) Serial.println(btn ? "button PRESSED" : "button released");
    lastBtn = btn;
    if (!btn && joyHeld) { release(); joyHeld = false; }
  }
  if (!btn) return;
  int dir = 0;
  if (x < JOY_LOW) dir = -1;
  else if (x > JOY_HIGH) dir = 1;
  if (dir == 0) return;
  if (stepHeld(dir * JOY_CHUNK)) joyHeld = true;  // coils stay energized until the button comes up
  if (readout) Serial.println(dir < 0 ? "left" : "right");
}

unsigned long lastReadout = 0;
void readoutTick() {
  if (!readout || millis() - lastReadout < 250) return;
  lastReadout = millis();
  Serial.print("X "); Serial.print(analogRead(JOY_X));
  Serial.print("  pos "); Serial.println(pos);
}

// ---------- commands ----------
void handle(char* line) {
  if (strcmp(line, "PING") == 0) {
    sendReading(posDeg());
  } else if (strncmp(line, "SWEEP,", 6) == 0) {
    int from, to, step;
    if (sscanf(line + 6, "%d,%d,%d", &from, &to, &step) == 3) sweep(from, to, step);
  } else if (strncmp(line, "PAN,", 4) == 0) {
    panTo(atoi(line + 4));
    Serial.println("ACK");
  } else if (strcmp(line, "ZERO") == 0) {
    pos = 0;
    Serial.println("ACK");
  } else if (strncmp(line, "TWITCH,", 7) == 0) {
    twitch(atoi(line + 7));
    Serial.println("ACK");
  } else if (strncmp(line, "D,", 2) == 0) {
    Serial.println("ACK");  // LCD removed; D is accepted and ignored
  } else if (strlen(line) == 1) {
    switch (line[0]) {
      case 'a': sensorTest(); stepperTest(); break;
      case 's': sensorTest(); break;
      case 'm': stepperTest(); break;
      case 'j': readout = !readout; Serial.println(readout ? "readout on" : "readout off"); break;
      case 'l': if (!stepBy(-degToSteps(100))) Serial.println("limit"); Serial.print("at "); Serial.println(posDeg()); break;
      case 'r': if (!stepBy(degToSteps(100))) Serial.println("limit"); Serial.print("at "); Serial.println(posDeg()); break;
      case 'c': stepBy(-pos); Serial.println("at 90"); break;
    }
  }
}

void setup() {
  Serial.begin(115200);
  pinMode(TRIG, OUTPUT); pinMode(ECHO, INPUT); digitalWrite(TRIG, LOW);
  pinMode(JOY_SW, INPUT_PULLUP);
  pan.setSpeed(PAN_RPM);
  release();
  if (legAttached) { leg.attach(SERVO_PIN); leg.write(90); }
  Serial.println("READY");
}

void loop() {
  while (Serial.available()) {
    char c = Serial.read();
    if (c == '\n' || c == '\r') {
      if (lineLen > 0) { lineBuf[lineLen] = 0; handle(lineBuf); }
      lineLen = 0;
    } else if (lineLen == 0 && strchr("asmjlrc", c)) {
      char k[2] = {c, 0};  // test keys work with or without a line ending
      handle(k);
    } else if (lineLen < 63) {
      lineBuf[lineLen++] = c;
    }
  }
  joystick();
  readoutTick();
}
