# ReQuest Companion — run HER pygame from the web app

Her pygame script stays **completely untouched in her own repo**, sensors and all.
The companion is a small local helper you start once; after that, everything is
clickable from the ReQuest prototype.

## Setup (once, on the demo machine)

```bash
pip install -r requirements.txt
python bridge.py --game /path/to/her_repo/her_game.py
```

(Use `--game demo_game.py` to test without her repo.)

Open **http://localhost:8765** (the companion serves `request-app.html`), log in,
go to **Play**. The Crystal Caverns screen now shows a launch panel:

| button | what happens |
|---|---|
| **▶ LAUNCH GAME** | runs her script exactly like typing `python her_game.py` in a terminal — her real PyGame window pops up, she plays with the sensors as normal |
| **LAUNCH + MIRROR** | same native window, but every frame is also streamed live into the Crystal Caverns screen (red LIVE · PYGAME badge) |
| **STOP GAME** | terminates the running game |

A browser can't execute local commands on its own — that's exactly what the
companion exists for. The button sends `POST /api/launch`; the companion runs the
command. The old built-in JS demo game and the STRETCH button are **removed** —
that screen belongs to her game now.

## Reps & sets: dashboard → her game

Wired in two places:

1. **Play view** — "Game link" card: set *Reps / set* and *Sets*, press **Send to game**.
2. **Physio portal** — *Adjust program → Done* pushes the patient's new reps too.

On every push the companion:
- writes **`session.json` next to her script** (so she can just read a file),
- posts a pygame event (`USEREVENT + 7`) into the running game (live updates),
- serves it at `GET /api/session`.

Her game consumes it however she prefers — file, API, event, or not at all.
Optional one-liner via the bundled helper:

```python
import request_bridge
cfg = request_bridge.get_session()      # {'reps': 18, 'sets': 4, ...}
# live mid-game (optional):
#   if event.type == request_bridge.SESSION_EVENT: cfg = event.session
```

`demo_game.py` shows the full pattern (enemy HP = reps). If the companion isn't
running, `get_session()` returns defaults — her script still works standalone.





## After a workout: auto check-in + optional saved progress

When a full workout completes, the game reports it (save_result / auto-save on
exit). The website then: shows a "Workout complete" toast, records the session,
and for the patient view automatically jumps to the daily check-in (pain /
soreness self-report) with a summary banner of what was just done.

Saved progress (optional, off by default): in Settings there's a "Record my
progress" toggle. When on, the patient's level, check-in history, messages and
last workout are saved in the browser (localStorage) and merged back over the
seeded demo data on the next refresh, so a refresh no longer wipes the run.
"New session" still does a full reset (clears recorded progress) for the next
demo. Completed workouts are also always persisted server-side in
workout_log.json by the companion.


## How the live data flows (full picture)

Two directions, deliberately different, because of one hard constraint: a web
browser cannot read a file off the disk. So:

DASHBOARD -> GAME  (what to do): file-based.
  The dashboard writes session.json next to the game; the game reads it (or the
  helper / SESSION_EVENT). The game can read a local file easily, so a file is
  the simplest channel here.

GAME -> DASHBOARD  (what happened): live messages, not a file.
  The browser can't read the game's disk, so the game pushes its progress to the
  companion, which relays it to the website over a WebSocket. You never write
  HTTP yourself - two helper calls do it:

    request_bridge.report(reps_done=r, sets_done=s, level=l, score=p)  # live
    request_bridge.save_result(..., completed=True)                    # at the end

  * report(...) is how "every rep" reaches the website. Call it whenever your
    numbers change (e.g. after each rep). It's throttled to ~2-3 sends/sec so a
    burst of fast reps doesn't flood the link - it always sends the latest. The
    companion broadcasts a "progress" message; the website's "This session" card
    updates instantly.
  * The WORKOUT IS DONE when YOUR game decides it is and calls
    save_result(..., completed=True). The bridge does NOT guess - your code owns
    the rule (e.g. all sets of every exercise cleared). On that call the companion
    appends the session to workout_log.json (persistent) and broadcasts a
    "result" message; the website records it and sends the patient to the
    check-in page. As a safety net, if the game exits after calling report(...)
    but never save_result(...), the last reported stats auto-save on exit.

So: reps -> report() -> companion -> WebSocket -> website (live counts);
finish -> save_result() -> companion -> workout_log.json + website (done).
You do NOT need to manage any file for the game->dashboard direction.

## What the game reads (for the game developer)

The dashboard never writes into the game's memory directly — it writes a small
file the game reads, so the game stays in control. On every reps/sets change the
companion writes **session.json next to the game script**:

    {
      "patient": "Marcus",
      "plan": [
        {"exercise": "Shoulder External Rotation", "reps": 12, "sets": 3},
        {"exercise": "Banded I-Y-T Raises",        "reps": 15, "sets": 3},
        {"exercise": "Single-Arm Row to Press",    "reps": 10, "sets": 3}
      ],
      "current": 0,                                # which exercise is active
      "resistance": "medium",
      "updated": 1700000000.0
    }

There is one copy of each exercise (in `plan`); `current` points at the active
one. request_bridge.get_plan() returns the list, current_exercise() returns the
active one. It refreshes on every dashboard change (updated = timestamp); get_session() is cached and only re-reads when the file changes.

Read it any of these ways (all optional, pick one):
  * the file session.json directly (path also in env REQUEST_BRIDGE_SESSION)
  * request_bridge.get_session()  (cached helper)
  * the pygame event request_bridge.SESSION_EVENT (USEREVENT+7) for live updates
  * HTTP GET /api/session

It carries the prescribed reps/sets PER EXERCISE (the "exercise" field tells you
which). It does NOT touch lives or any other game variable — how reps map to
enemy HP, lives, score, etc. is entirely the game's own code. In the ReQuest
concept reps map to enemy hit points (1 rep = 1 hit), not lives.

Defaults: the reps/sets sent start from the physio's prescription for that
patient/exercise (set in the physio dashboard). The patient can override them in
the game dashboard for a single session, but the prescription is the source.

## Saving workout data (reps done, level, score)

The game reports its results back to the dashboard, and they are saved to
**workout_log.json** next to her script. Two optional one-liners:

    import request_bridge
    # during the workout, whenever numbers change:
    request_bridge.report(reps_done=hits, sets_done=cleared, level=lvl, score=score)
    # when the workout ends (or just rely on auto-save when the window closes):
    request_bridge.save_result(reps_done=hits, sets_done=cleared,
                               level=lvl, score=score, completed=True)

While the game runs, the Play view shows live "This session" numbers; finished
workouts appear under "Saved workouts" and persist in workout_log.json. If she
only calls report(...) and the game closes without save_result(...), the last
reported stats are auto-saved on exit. Both calls are fire-and-forget on a
background thread, so they never slow the game. demo_game.py shows the pattern.

Endpoints (if she wants them directly): POST /api/progress, POST /api/result,
GET /api/results.

## Performance (read if mirroring ever feels slow)

Mirroring adds almost nothing to the game loop: the game thread only does a
cheap raw-pixel grab (~1-2 ms, capped to 18/sec); all JPEG encoding and
network sending happen on a separate worker thread that drops frames if it
falls behind. So the game runs at full speed whether mirrored or not.

If her game still feels slower in *native* (non-mirror) launch, the usual
cause is reading session.json every frame. Use the bundled helper, which
caches and won't touch the disk on a hot loop:

    import request_bridge
    cfg = request_bridge.get_session()          # call ONCE before the loop
    # update live only when the dashboard sends new values:
    #   if event.type == request_bridge.SESSION_EVENT: cfg = event.session

Tuning knobs at the top of runner.py: MIRROR_FPS, JPEG_QUALITY, MAX_WIDTH.
Lower them for a weaker machine; raise MIRROR_FPS for a smoother mirror.

## Best practice for playing

Play in the **real pygame window** (sensors drive it directly, zero latency).
The mirror in the Crystal Caverns screen is a live *view* for the dashboard /
audience. Driving the game by clicking/keying the browser frame works but
adds network latency, so it's for convenience, not primary play.

## Files

| file | role |
|---|---|
| `bridge.py` | the companion: serves the app, launch/stop, session API, frame relay |
| `runner.py` | used only by LAUNCH + MIRROR: runs her script unchanged and streams its frames |
| `request-app.html` | updated prototype (launch panel in Play, dashboard→game wiring) |
| `request_bridge.py` | optional 1-import helper for the game side |
| `demo_game.py` | ordinary pygame script standing in for hers |

## Notes

- Mirror mode is read-mostly: sensors keep driving her game; keys/clicks on the
  mirrored frame are forwarded as ordinary pygame events but can be ignored.
- If the companion is off, the Play screen says so with the exact command to run,
  and the rest of the prototype works untouched.
- Port/quality knobs at the top of `bridge.py` / `runner.py` (default port 8765).
- Tested with pygame-ce 2.5.7 / Python 3.12; plain pygame works too.
