"""
Optional helper for the game side. Your script stays runnable on its own.

READING THE SESSION (what the dashboard pushes in):

    import request_bridge
    cfg = request_bridge.get_session()
    # cfg describes the whole session as a plan + which one is active:
    # {
    #   "patient":    "Marcus",
    #   "plan": [                                   # the FULL workout
    #     {"exercise": "Shoulder External Rotation", "reps": 12, "sets": 3},
    #     {"exercise": "Banded I-Y-T Raises",        "reps": 15, "sets": 3},
    #     {"exercise": "Single-Arm Row to Press",    "reps": 10, "sets": 3}
    #   ],
    #   "current":    0,            # index of the active exercise in plan
    #   "resistance": "medium",
    #   "updated":    1700000000.0  # unix time of last change
    # }

    plan = request_bridge.get_plan()          # -> the list of exercises
    active = request_bridge.current_exercise()  # -> plan[current], e.g.
                                              #    {"exercise": "...", "reps": 12, "sets": 3}

There is exactly ONE copy of each exercise (in `plan`); `current` just points
at the active one. Drive the whole workout off `plan`, or use current_exercise()
for just the active one.

HOW IT REFRESHES:
  * The dashboard rewrites the session every time anything changes (exercise
    picked, reps/sets edited, physio updates the prescription). `updated` is
    the timestamp of the last change.
  * get_session() is cached and only re-reads the file when it actually
    changes on disk (max ~4x/sec), so calling it every frame is cheap.
  * For instant, push-style updates without polling, listen for the pygame
    event request_bridge.SESSION_EVENT (USEREVENT+7); event.session carries
    the same dict.

SAVING WORKOUT DATA back to the dashboard (optional):
    request_bridge.report(reps_done=h, sets_done=c, level=lvl, score=s)   # live
    request_bridge.save_result(reps_done=h, sets_done=c, level=lvl,
                               score=s, completed=True)                   # final
If you only call report(...), the last stats auto-save when the game closes.

Everything is best-effort: if the dashboard/companion isn't running,
get_session()/get_plan() return defaults and report()/save_result() do
nothing, so your game still runs with a plain `python your_game.py`.
"""
import atexit, json, os, threading, time, urllib.request
import pygame

SESSION_EVENT = pygame.USEREVENT + 7

_DEFAULTS = {"patient": "Player", "resistance": "medium",
             "plan": [{"exercise": "Band pull-apart", "reps": 10, "sets": 3}],
             "current": 0}
_URL = os.environ.get("REQUEST_BRIDGE_URL", "http://127.0.0.1:8765")

_cache = {"data": dict(_DEFAULTS), "mtime": 0.0, "checked": 0.0}
_last_reported = {}
_saved = False
_last_report_post = 0.0


# ----------------------------------------------------------- read settings in
def get_session():
    """Return the full session dict (cached; re-reads only when the file changes)."""
    now = time.monotonic()
    if now - _cache["checked"] < 0.25:
        return dict(_cache["data"])
    _cache["checked"] = now
    path = os.environ.get("REQUEST_BRIDGE_SESSION", "session.json")
    try:
        m = os.path.getmtime(path)
        if m != _cache["mtime"]:
            with open(path) as f:
                _cache["data"] = {**_DEFAULTS, **json.load(f)}
            _cache["mtime"] = m
    except (OSError, json.JSONDecodeError):
        pass
    return dict(_cache["data"])


def get_plan():
    """Return the list of exercises for the full workout:
       [{'exercise': ..., 'reps': ..., 'sets': ...}, ...]"""
    return list(get_session().get("plan", []))


def current_exercise():
    """Return the active exercise dict {'exercise','reps','sets'} (plan[current])."""
    s = get_session()
    plan = s.get("plan", [])
    if not plan:
        return {"exercise": "Band pull-apart", "reps": 10, "sets": 3}
    i = min(max(0, s.get("current", 0)), len(plan) - 1)
    return dict(plan[i])


# ----------------------------------------------------------- send results out
def _post(path, payload):
    def _go():
        try:
            req = urllib.request.Request(
                _URL + path, data=json.dumps(payload).encode(),
                headers={"Content-Type": "application/json"})
            urllib.request.urlopen(req, timeout=1)
        except Exception:
            pass
    threading.Thread(target=_go, daemon=True).start()


def report(**stats):
    """Live running stats (reps_done, sets_done, level, score...). Throttled."""
    global _last_report_post
    _last_reported.update(stats)
    now = time.monotonic()
    if now - _last_report_post >= 0.4:
        _last_report_post = now
        _post("/api/progress", dict(_last_reported))


def save_result(**stats):
    """Save a completed workout to the dashboard + workout_log.json."""
    global _saved
    data = {**_last_reported, **stats}
    _saved = True
    _post("/api/result", data)


@atexit.register
def _auto_save():
    if _last_reported and not _saved:
        try:
            req = urllib.request.Request(
                _URL + "/api/result", data=json.dumps(_last_reported).encode(),
                headers={"Content-Type": "application/json"})
            urllib.request.urlopen(req, timeout=1)
        except Exception:
            pass
