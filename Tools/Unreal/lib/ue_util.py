"""Small shared helpers for the Unreal automation scripts.

Deliberately minimal: context from the launcher, a log function, and a result
wrapper so failures surface as JSON instead of being buried in the Unreal log.
"""

import json
import os
import sys
import time
import traceback

TOOLS_DIR = os.environ.get("UE_TOOLS_DIR") or os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir))
OUTPUT_DIR = os.path.join(TOOLS_DIR, "output")
PROJECT_DIR = os.environ.get("UE_PROJECT_DIR", "")
RUN_ID = os.environ.get("UE_RUN_ID", "")
RESULT_FILE = os.environ.get("UE_RESULT_FILE", "")

try:
    import unreal
except ImportError:
    unreal = None

_errors = []


def log(text, level="info"):
    line = "[automation][%s] %s" % (level, text)
    if unreal is not None:
        # unreal.log already reaches stdout via -stdout; printing too would
        # duplicate every line in the log.
        if level == "error":
            unreal.log_error(line)
        elif level == "warning":
            unreal.log_warning(line)
        else:
            unreal.log(line)
    else:
        print(line)
        sys.stdout.flush()


def warn(text):
    log(text, "warning")


def error(text):
    _errors.append(str(text))
    log(text, "error")


def params():
    raw = os.environ.get("UE_AUTOMATION_PARAMS_JSON", "")
    return json.loads(raw) if raw else {}


# --- small shared helpers ---------------------------------------------------

def v(x, y, z):
    """unreal.Vector from three numbers."""
    return unreal.Vector(float(x), float(y), float(z))


def rot(yaw, pitch=0.0, roll=0.0):
    """unreal.Rotator in yaw-first order, which is how scenes are described."""
    return unreal.Rotator(float(roll), float(pitch), float(yaw))


def vec_scale(scale):
    """Accept a number or a Vector and always return a Vector."""
    if isinstance(scale, unreal.Vector):
        return scale
    return v(scale, scale, scale)


def safe_set(obj, name, value):
    """set_editor_property that warns instead of aborting.

    Property names move between engine versions; one bad name should not kill
    a whole build.
    """
    try:
        obj.set_editor_property(name, value)
        return True
    except Exception as exc:
        warn("could not set %s: %s" % (name, exc))
        return False


def editor_world():
    return unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()


def actor_subsystem():
    return unreal.get_editor_subsystem(unreal.EditorActorSubsystem)


def run(main, name):
    """Run main(params), write a JSON result, return an exit code."""
    started = time.time()
    result = {"status": "ok", "script": name, "run_id": RUN_ID, "data": {}, "traceback": None}
    try:
        data = main(params())
        if data:
            result["data"] = data
    except Exception as exc:
        result["status"] = "error"
        result["traceback"] = traceback.format_exc()
        error("%s: %s" % (type(exc).__name__, exc))

    if _errors and result["status"] == "ok":
        result["status"] = "error"
    result["errors"] = _errors
    result["duration_seconds"] = round(time.time() - started, 1)

    payload = json.dumps(result, indent=2, sort_keys=True, default=str)
    if RESULT_FILE:
        try:
            with open(RESULT_FILE, "w", encoding="utf-8") as handle:
                handle.write(payload)
        except Exception as exc:
            log("could not write result file: %s" % exc, "error")
    print("<<<UE_RESULT_JSON>>>")
    print(payload)
    print("<<<END_UE_RESULT_JSON>>>")
    sys.stdout.flush()
    return 0 if result["status"] == "ok" else 1
