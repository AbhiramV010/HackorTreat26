// Pan stepper test, no sensor needed. Serial monitor at 115200 baud, line ending: No line ending.
// l = 10 deg left, r = 10 deg right, c = back to center, w = wiggle 20 to 160 three times,
// f = one full turn forward, b = one full turn back, + / - = speed up or down (RPM).

#include <Stepper.h>

const int STEPS_PER_REV = 2048;
const int DIR = 1;                           // change to -1 if left and right are swapped
Stepper pan(STEPS_PER_REV, A2, A4, A3, A5);  // order is IN1, IN3, IN2, IN4 on purpose
float angle = 90.0;                          // assumed straight ahead at power-up
int rpm = 10;

void release() {
  digitalWrite(A2, LOW);
  digitalWrite(A3, LOW);
  digitalWrite(A4, LOW);
  digitalWrite(A5, LOW);
}

void moveTo(float target) {
  long steps = lround((target - angle) * STEPS_PER_REV / 360.0) * DIR;
  pan.step((int)steps);
  angle = target;
  release();
  Serial.print("at ");
  Serial.print((int)angle);
  Serial.println(" deg");
}

void setup() {
  Serial.begin(115200);
  pan.setSpeed(rpm);
  release();
  Serial.println("Center the head by hand, then send a command.");
}

void loop() {
  if (!Serial.available()) return;
  char c = Serial.read();

  if (c == 'l') {
    moveTo(angle - 10);
  } else if (c == 'r') {
    moveTo(angle + 10);
  } else if (c == 'c') {
    moveTo(90);
  } else if (c == 'w') {
    for (int i = 0; i < 3; i++) {
      moveTo(20);
      moveTo(160);
    }
    moveTo(90);
  } else if (c == 'f') {
    pan.step(STEPS_PER_REV * DIR);
    release();
    Serial.println("full turn forward");
  } else if (c == 'b') {
    pan.step(-STEPS_PER_REV * DIR);
    release();
    Serial.println("full turn back");
  } else if (c == '+' || c == '-') {
    rpm = constrain(rpm + (c == '+' ? 1 : -1), 4, 14);
    pan.setSpeed(rpm);
    Serial.print("speed ");
    Serial.print(rpm);
    Serial.println(" RPM");
  }
}