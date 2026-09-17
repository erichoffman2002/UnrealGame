"""Camera positioning and preview rendering.

Renders come from the real editor viewport via HighResShot, not SceneCapture2D.
A scene capture renders without resolved Lumen GI and without waiting for
texture streaming, which produces flat, black-shadowed, untextured images that
are useless for judging a scene.

HighResShot is asynchronous, so capture_views() drives a tick callback and
shuts the editor down when it finishes. That means the editor must be launched
so it stays alive after the script returns - run_unreal.ps1 -Editor does this
via -ExecCmds.

Typical use, as the last statement of a build script:

    exit_code = ue_util.run(main, "my_script")
    if exit_code:
        unreal.SystemLibrary.quit_editor()
    else:
        ue_render.capture_views([
            ("hero.png", ue_util.v(-2950, -1750, 780), ue_util.rot(29, -8)),
        ])
"""

import os

import unreal

import ue_assets
import ue_util
from ue_util import actor_subsystem, editor_world, log, warn

STREAMING_COMMANDS = (
    "r.Streaming.FullyLoadUsedTextures 1",
    "r.Streaming.PoolSize 3000",
    "r.Streaming.MipBias 0",
    "r.Streaming.Boost 10",
    "r.MipMapLODBias 0",
)

HIDE_EDITOR_FLAGS = (
    "ShowFlag.BillboardSprites 0",
    "ShowFlag.Grid 0",
    "ShowFlag.Selection 0",
    "ShowFlag.SelectionOutline 0",
)


def prepare(world=None):
    """Get the scene render-ready: stream textures in and capture the sky.

    Without this, previews show the lowest mip of every texture (a flat average
    colour) and an un-captured sky light contributes no ambient at all.
    """
    world = world or editor_world()
    for command in STREAMING_COMMANDS:
        try:
            unreal.SystemLibrary.execute_console_command(world, command)
        except Exception as exc:
            warn("console command failed (%s): %s" % (command, exc))

    for actor in actor_subsystem().get_all_level_actors():
        if isinstance(actor, unreal.SkyLight):
            try:
                actor.get_component_by_class(
                    unreal.SkyLightComponent).recapture_sky()
            except Exception as exc:
                warn("recapture_sky failed: %s" % exc)

    forced = 0
    for material in ue_assets.tracked_materials():
        try:
            material.set_force_mip_levels_to_be_resident(True, True, 600.0, 0, True)
            forced += 1
        except Exception:
            pass
    log("render prep: forced textures resident on %d materials" % forced)


def look_at(location, target, ):
    """Rotator aiming from location at target - saves guessing yaw/pitch."""
    dx = target.x - location.x
    dy = target.y - location.y
    dz = target.z - location.z
    import math
    yaw = math.degrees(math.atan2(dy, dx))
    pitch = math.degrees(math.atan2(dz, math.hypot(dx, dy)))
    return ue_util.rot(yaw, pitch)


def set_viewport_camera(location, rotation):
    """Move the editor's perspective viewport."""
    unreal.get_editor_subsystem(
        unreal.UnrealEditorSubsystem).set_level_viewport_camera_info(
            location, rotation)


def capture_views(views, width=1280, height=720, quit_when_done=True,
                  output_dir=None):
    """Render one PNG per view into Tools/Unreal/output.

    views is a list of (filename, location, rotation). Returns the shooter;
    the actual files appear asynchronously, and the editor quits at the end
    unless quit_when_done is False.
    """
    shooter = _ViewportShooter(views, width, height, quit_when_done, output_dir)
    shooter.start()
    return shooter


class _ViewportShooter(object):
    """Tick-driven state machine: move camera -> settle -> shoot -> collect."""

    SETTLE_TICKS = 170     # long enough for eye adaptation and streaming
    SHOT_TICKS = 200       # upper bound while waiting for the file to appear
    MAX_TICKS = 2500

    def __init__(self, views, width, height, quit_when_done, output_dir):
        self.views = list(views)
        self.width, self.height = width, height
        self.quit_when_done = quit_when_done
        self.output_dir = output_dir or ue_util.OUTPUT_DIR
        self.index, self.ticks, self.total = -1, 0, 0
        self.state = "next"
        self.handle = None
        self.saved = []
        self.shot_dir = os.path.join(
            unreal.Paths.convert_relative_path_to_full(
                unreal.Paths.project_saved_dir()),
            "Screenshots", "WindowsEditor")
        self.seen = set(self._existing())

    def _existing(self):
        if not os.path.isdir(self.shot_dir):
            return []
        return [f for f in os.listdir(self.shot_dir) if f.lower().endswith(".png")]

    def _fresh(self):
        return [f for f in self._existing() if f not in self.seen]

    def start(self):
        prepare()
        # Game view hides light billboards, the grid and the axis widget.
        try:
            unreal.get_editor_subsystem(
                unreal.LevelEditorSubsystem).editor_set_game_view(True)
        except Exception as exc:
            warn("could not enable game view: %s" % exc)
        for flag in HIDE_EDITOR_FLAGS:
            try:
                unreal.SystemLibrary.execute_console_command(editor_world(), flag)
            except Exception:
                pass
        self.handle = unreal.register_slate_post_tick_callback(self.tick)
        log("viewport capture started (%d views)" % len(self.views))

    def finish(self):
        if self.handle is not None:
            unreal.unregister_slate_post_tick_callback(self.handle)
            self.handle = None
        log("captured: %s" % (", ".join(self.saved) if self.saved else "nothing"))
        if self.quit_when_done:
            unreal.SystemLibrary.quit_editor()

    def tick(self, delta_seconds):
        self.ticks += 1
        self.total += 1
        if self.total > self.MAX_TICKS:
            warn("capture pass timed out")
            self.finish()
            return
        try:
            if self.state == "next":
                self.index += 1
                if self.index >= len(self.views):
                    self.finish()
                    return
                name, location, rotation = self.views[self.index][:3]
                set_viewport_camera(location, rotation)
                self.ticks, self.state = 0, "settle"

            elif self.state == "settle" and self.ticks >= self.SETTLE_TICKS:
                unreal.SystemLibrary.execute_console_command(
                    editor_world(), "HighResShot %dx%d" % (self.width, self.height))
                self.ticks, self.state = 0, "shoot"

            elif self.state == "shoot":
                if self._fresh():
                    self._collect(self.views[self.index][0])
                    self.state = "next"
                elif self.ticks >= self.SHOT_TICKS:
                    warn("no screenshot produced for %s" % self.views[self.index][0])
                    self.state = "next"
        except Exception as exc:
            warn("capture tick failed: %s" % exc)
            self.finish()

    def _collect(self, target_name):
        fresh = self._fresh()
        if not fresh:
            return
        fresh.sort(key=lambda f: os.path.getmtime(os.path.join(self.shot_dir, f)))
        newest = fresh[-1]
        self.seen.add(newest)
        destination = os.path.join(self.output_dir, target_name)
        try:
            if not os.path.isdir(self.output_dir):
                os.makedirs(self.output_dir)
            with open(os.path.join(self.shot_dir, newest), "rb") as src:
                data = src.read()
            with open(destination, "wb") as dst:
                dst.write(data)
            self.saved.append("%s (%d bytes)" % (target_name, len(data)))
            log("captured %s -> %s" % (newest, destination))
        except Exception as exc:
            warn("could not copy screenshot %s: %s" % (newest, exc))
