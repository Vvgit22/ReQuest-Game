"""
runner.py — used internally by bridge.py for "Launch + mirror".

Runs her pygame script exactly as `python her_game.py` would (her normal
window opens, sensors work as usual). Her script is never modified.

Performance design (this is what keeps the game smooth):
  * The game's main loop does ONLY a cheap raw-pixel grab, rate-capped to
    MIRROR_FPS. No image encoding happens on the game thread.
  * A separate worker thread JPEG-encodes the most recent frame and sends
    it to the companion. If it falls behind it DROPS frames instead of
    queueing them, so the game never waits for the network or the encoder.
  * Grabbing raw pixels costs ~1-2 ms; encoding (~15 ms) is off the loop.
"""
import argparse, io, json, sys, threading, time
from collections import deque
from pathlib import Path

import pygame
from PIL import Image

WS_URL = "ws://127.0.0.1:8765/ws/game"
MIRROR_FPS = 18           # how often we GRAB a frame (cheap) on the game thread
JPEG_QUALITY = 55
MAX_WIDTH = 720           # downscale wide windows in the worker
SESSION_EVENT = pygame.USEREVENT + 7

_lock = threading.Lock()
_raw = {"bytes": None, "size": (0, 0), "seq": 0}
_inputs = deque()
_last_grab = 0.0

_KEYMAP = {"ArrowLeft": pygame.K_LEFT, "ArrowRight": pygame.K_RIGHT,
           "ArrowUp": pygame.K_UP, "ArrowDown": pygame.K_DOWN,
           " ": pygame.K_SPACE, "Enter": pygame.K_RETURN,
           "Escape": pygame.K_ESCAPE, "Shift": pygame.K_LSHIFT,
           "Tab": pygame.K_TAB, "Backspace": pygame.K_BACKSPACE}


def _grab():
    """Cheap: copy raw pixels into the shared slot. Runs on the game thread."""
    global _last_grab
    now = time.perf_counter()
    if now - _last_grab < 1.0 / MIRROR_FPS:
        return
    surf = pygame.display.get_surface()
    if surf is None:
        return
    _last_grab = now
    to_bytes = getattr(pygame.image, "tobytes", pygame.image.tostring)
    data = to_bytes(surf, "RGB")
    with _lock:
        _raw["bytes"] = data
        _raw["size"] = surf.get_size()
        _raw["seq"] += 1


def _drain():
    """Inject browser/dashboard events on the game's own thread (cheap)."""
    if not _inputs:
        return
    surf = pygame.display.get_surface()
    sw, sh = surf.get_size() if surf else (1, 1)
    while _inputs:
        m = _inputs.popleft()
        t = m.get("type")
        if t == "session":
            pygame.event.post(pygame.event.Event(SESSION_EVENT, session=m.get("session", {})))
        elif t in ("keydown", "keyup"):
            name = m.get("key", "")
            k = _KEYMAP.get(name)
            if k is None and len(name) == 1:
                try:
                    k = pygame.key.key_code(name.lower())
                except Exception:
                    k = None
            if k is not None:
                pygame.event.post(pygame.event.Event(
                    pygame.KEYDOWN if t == "keydown" else pygame.KEYUP,
                    key=k, mod=0, unicode=name if len(name) == 1 else ""))
        elif t in ("mousedown", "mouseup"):
            pos = (int(m.get("x", 0) * sw), int(m.get("y", 0) * sh))
            pygame.event.post(pygame.event.Event(
                pygame.MOUSEBUTTONDOWN if t == "mousedown" else pygame.MOUSEBUTTONUP,
                pos=pos, button=int(m.get("button", 1))))


_flip, _update = pygame.display.flip, pygame.display.update
def flip(*a, **kw):
    r = _flip(*a, **kw); _drain(); _grab(); return r
def update(*a, **kw):
    r = _update(*a, **kw); _drain(); _grab(); return r
pygame.display.flip, pygame.display.update = flip, update


def _ws_thread():
    import asyncio, websockets

    async def run():
        while True:
            try:
                async with websockets.connect(WS_URL, max_size=None) as ws:

                    async def recv():
                        async for msg in ws:
                            try:
                                _inputs.append(json.loads(msg))
                            except Exception:
                                pass

                    task = asyncio.create_task(recv())
                    last_sent = -1
                    while not task.done():
                        with _lock:
                            seq, data, size = _raw["seq"], _raw["bytes"], _raw["size"]
                        if data is not None and seq != last_sent:
                            last_sent = seq
                            w, h = size
                            img = Image.frombytes("RGB", (w, h), data)
                            if w > MAX_WIDTH:
                                img = img.resize((MAX_WIDTH, int(h * MAX_WIDTH / w)))
                            buf = io.BytesIO()
                            img.save(buf, "JPEG", quality=JPEG_QUALITY)
                            await ws.send(buf.getvalue())
                        else:
                            await asyncio.sleep(0.005)
            except Exception:
                await asyncio.sleep(1)

    asyncio.new_event_loop().run_until_complete(run())


def main():
    game = Path(sys.argv[1]).resolve()
    threading.Thread(target=_ws_thread, daemon=True).start()
    sys.argv = [str(game)] + sys.argv[2:]
    sys.path.insert(0, str(game.parent))
    import runpy
    runpy.run_path(str(game), run_name="__main__")


if __name__ == "__main__":
    main()
