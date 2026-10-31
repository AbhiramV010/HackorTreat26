"""Rigor entry point.

python spider.py --sim --no-gemma --windowed      quick test, no hardware
python spider.py --standby --port COM3            the real thing
"""
import argparse
import os
import sys

import config as C


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", help="serial port (default: first port that answers READY)")
    ap.add_argument("--standby", action="store_true")
    ap.add_argument("--model", default=C.DEFAULT_MODEL)
    ap.add_argument("--no-gemma", action="store_true")
    ap.add_argument("--sim", action="store_true")
    ap.add_argument("--sim-people", type=int, default=None)
    ap.add_argument("--windowed", action="store_true")
    ap.add_argument("--mute", action="store_true")
    args = ap.parse_args()

    import pygame
    from audio import Audio
    from hud import Hud
    from serial_link import SerialLink, SimLink
    from state import StateMachine
    from voices import Voice
    import standby

    # audio before the HUD so the mixer gets its settings first
    audio = Audio(mute=args.mute)
    hud = Hud(windowed=args.windowed)
    link = SimLink(args.sim_people) if args.sim else SerialLink(args.port)
    voice = Voice(enabled=not args.mute)

    if args.standby:
        standby.run_all(link, audio, voice, args.model, sim=args.sim, use_gemma=not args.no_gemma)
    else:
        # lazy loads, no self-test
        for ln in ("Scanning.", "Sensors tingling.", "My sensors are down."):
            voice.prerender(ln)
        audio.prepare_static()

    sm = StateMachine(link, audio, voice, model=args.model, use_gemma=not args.no_gemma)
    clock = pygame.time.Clock()
    # no arrow keys: pan is driven by the joystick and the l/r/c keys on the Uno
    keys = {pygame.K_SPACE: "space", pygame.K_r: "r", pygame.K_c: "c", pygame.K_z: "z"}
    running = True
    try:
        while running:
            for ev in pygame.event.get():
                if ev.type == pygame.QUIT:
                    running = False
                elif ev.type == pygame.KEYDOWN:
                    if ev.key == pygame.K_ESCAPE:
                        running = False
                    elif ev.key == pygame.K_TAB:
                        hud.details = not hud.details
                    elif ev.key == pygame.K_5 and ev.mod & pygame.KMOD_ALT:
                        sm.picture_only()
                    elif ev.key in keys:
                        sm.key(keys[ev.key])
            sm.tick()
            hud.draw(sm)
            clock.tick(30)
    finally:
        try:
            sm.reset()
        except Exception:
            pass
        standby.restore_sleep()
        link.close()
        pygame.quit()
        # NOTE: cv2/pygame teardown can hang at interpreter exit; cleanup is done, so leave hard.
        os._exit(0)


if __name__ == "__main__":
    sys.exit(main())
