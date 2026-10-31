# Rigor: how to run the demo

Rigor is a spider-shaped radio companion for a zombie. It receives a Morse transmission, decodes it, sweeps the room with an ultrasonic sensor, counts the "humans" and panics. Gemma writes the words, the code decides the facts.

## 1. Setup (once)

```
pip install -r requirements.txt
ollama pull gemma3:4b          # optional, for live transmissions
ollama pull gemma3:1b          # faster fallback
```

Optional voice: put a Piper model at `voices/en_US-lessac-medium.onnx` (plus its `.json`). Without it Rigor uses Windows SAPI; without that, subtitles only.

## 2. Hardware checklist

- Uno on a COM port (currently COM4), firmware `firmware/spider_uno/spider_uno.ino` flashed.
- HC-SR04 on D7/D8, mounted on the stepper shaft.
- 28BYJ-48 stepper on A2–A5, powered from the power module, grounds shared.
- Joystick: VRx on A1, SW on D3.
- **Centre the head by hand before powering on or resetting.** Position is dead-reckoned from there.

## 3. Start it

| Situation | Command |
|---|---|
| Real demo | `python spider.py --standby --port COM4` |
| No hardware | `python spider.py --sim --no-gemma --windowed` |
| No hardware, with Gemma | `python spider.py --sim --windowed` |
| Simulate 3 people | `python spider.py --sim --sim-people 3 --windowed` |
| Silent | add `--mute` |
| Slow laptop | add `--model gemma3:1b` |

`--standby` runs the self-test (stepper 20→160→90, one PING), warms Ollama, pre-renders speech and prints `[OK]`/`[FAIL]` per step. A failed step degrades the run, it does not stop it.

## 4. Keys (in the HUD window)

| Key | Does |
|---|---|
| Space | Start a run (READY only) |
| R | Reset to READY |
| Tab | Details screen: theme, message, Gemma timing, raw readings, contacts, corners cut |
| C | Baseline sweep of an empty room (READY only). Improves detection in cluttered rooms. |
| Z | Tell the Uno the head is at 90° (after recentering by hand) |
| Esc | Quit |

Pan is **not** on the keyboard. Use the joystick (hold the button, push left/right) or send `l`, `r`, `c` to the Uno over serial.

## 5. What a run looks like (~40 s)

1. **RIGOR WAKING**: static hiss, Gemma invents a transmission (5 s cap, else a canned one).
2. **RADIO IN**: beeps play, dots and dashes appear letter by letter in the RADIO panel. Audience can decode along.
3. **RADIO: <message>**: the decoded text appears, Rigor speaks its line.
4. **SCANNING**: the head sweeps 20°→160°. The SWEEP panel draws the true sensor map: the room outline, shaded open space, one dot per reading, sweep line following the head.
5. **THINKING**: contacts are computed, Gemma writes the scene (6 s cap, else canned).
6. **HUMANS: n / NEAREST x.x M** or **CLEAR**: contacts are circled with `~n` people, nearest is ringed. Rigor speaks the scene and reaction.
7. **SSTV** (FEW/CROWD only): webcam face crop goes out as Robot36 audio through the speaker. Hold a phone running an SSTV decoder (e.g. Robot36 on Android) against the speaker. The image reveals line by line.

Press R, then Space for a second run. The transmission will differ.

## 6. Firmware test keys (serial monitor at 115200)

`python tools/serial_monitor.py --port COM4`, then type:

| Key | Does |
|---|---|
| `a` | Sensor test then stepper test |
| `s` | 5 single-ping readings |
| `m` | Stepper 20 → 160 → 90, resets position counter |
| `j` | Toggle joystick readout (`X <v>  pos <steps>`, button, left/right) |
| `l` / `r` | 10° left / right |
| `c` | Back to centre |
| `PING` | One median reading: `S,<angle>,<cm>` |
| `SWEEP,20,160,10` | Full sweep: 15 `S` lines then `SWEEPDONE` |
| `PAN,45` | Move to 45°, answers `ACK` |
| `ZERO` | Declare current position 90° |

## 7. Troubleshooting

| Symptom | Fix |
|---|---|
| `SERIAL LOST` in header | Check USB; it retries every 2 s. Close the Arduino serial monitor. |
| `SENSOR OFFLINE` | No `S` lines came back. Check D7/D8 and the sensor's 5V. |
| Head drifts or hits the end | A stall skipped steps. Recentre by hand, press Z (or send `c`). |
| Left/right swapped | Set `DIR = -1` in the firmware, or `MIRROR_ANGLES = True` in `config.py`. |
| Gemma always falls back | Normal on a slow laptop; try `--model gemma3:1b`. Canned lines still make a full demo. |
| Everyone counts as 2+ people | Press C with the room empty to record a baseline. |
| Upload says "Access is denied" | Something has COM4 open; close the serial monitor and retry. |

## 8. Tests

```
python -m pytest tests -q
```
