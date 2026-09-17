"""Level lifecycle: create, open, clear, save, and make walkable."""

import unreal

from ue_util import actor_subsystem, editor_world, log, rot, safe_set, v, warn

KEEP_TYPES = (unreal.WorldSettings, unreal.Brush)


def _level_editor():
    return unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)


def create(level_path, reuse=True):
    """Create the level, or clear and reuse it if it already exists.

    Deleting the level that is currently loaded fails silently - the editor
    reopens the last level on startup and holds it - so this moves to a blank
    map first and falls back to clearing the actors in place. The result is
    idempotent: running a build script repeatedly is safe.
    """
    unreal.EditorLoadingAndSavingUtils.new_blank_map(False)

    if unreal.EditorAssetLibrary.does_asset_exist(level_path):
        unreal.EditorAssetLibrary.delete_asset(level_path)

    if unreal.EditorAssetLibrary.does_asset_exist(level_path):
        if not reuse:
            raise RuntimeError("level %s exists and could not be deleted" % level_path)
        unreal.EditorLoadingAndSavingUtils.load_map(level_path)
        removed = clear_actors()
        log("reused existing level %s, cleared %d actors" % (level_path, removed))
        return level_path

    if not _level_editor().new_level(level_path):
        raise RuntimeError("could not create level %s" % level_path)
    log("created level %s" % level_path)
    return level_path


def open_level(level_path):
    unreal.EditorLoadingAndSavingUtils.load_map(level_path)
    log("opened level %s" % level_path)
    return level_path


def clear_actors(keep_types=KEEP_TYPES):
    """Destroy every actor except world infrastructure. Returns the count."""
    actors = actor_subsystem()
    removed = 0
    for actor in actors.get_all_level_actors():
        if isinstance(actor, keep_types):
            continue
        actors.destroy_actor(actor)
        removed += 1
    return removed


def save(directory=None):
    """Save the current level, and optionally everything in a content folder."""
    if not _level_editor().save_current_level():
        raise RuntimeError("could not save the current level")
    if directory:
        unreal.EditorAssetLibrary.save_directory(directory, False, True)
    log("saved level%s" % (" and %s" % directory if directory else ""))
    return True


def actors_of_class(cls):
    return [a for a in actor_subsystem().get_all_level_actors() if isinstance(a, cls)]


# --- making a level walkable ------------------------------------------------

def add_player_start(location, rotation=None, label="PlayerStart"):
    """Where the player spawns in Play mode."""
    actor = actor_subsystem().spawn_actor_from_class(
        unreal.PlayerStart, location, rotation or rot(0.0))
    actor.set_actor_label(label)
    log("player start at %s" % (location,))
    return actor


def set_game_mode(blueprint_path):
    """Override this level's Game Mode, e.g. the first-person template one.

    Pass the Blueprint asset path without the _C suffix. This is what makes
    WASD walking work in Play mode; without it PIE falls back to the project
    default pawn.
    """
    gm_class = unreal.EditorAssetLibrary.load_blueprint_class(blueprint_path)
    if gm_class is None:
        warn("game mode blueprint not found: %s" % blueprint_path)
        return False

    settings = editor_world().get_world_settings()
    if settings is None:
        warn("no WorldSettings actor; game mode override not applied")
        return False
    safe_set(settings, "default_game_mode", gm_class)
    log("game mode override -> %s" % blueprint_path)
    return True


def add_collision_floor(half_extent, z=-20.0, thickness=0.4,
                        label="CollisionFloor"):
    """An invisible slab guaranteeing the player cannot fall through.

    Mesh collision on scattered/instanced ground is unreliable; this is a cheap
    safety net. half_extent is in cm.
    """
    mesh = unreal.EditorAssetLibrary.load_asset("/Engine/BasicShapes/Cube.Cube")
    if mesh is None:
        warn("could not load the engine cube; no collision floor added")
        return None
    actor = actor_subsystem().spawn_actor_from_object(mesh, v(0, 0, z), rot(0.0))
    actor.set_actor_scale3d(
        v(half_extent * 2.0 / 100.0, half_extent * 2.0 / 100.0, thickness))
    actor.static_mesh_component.set_visibility(False)
    actor.set_actor_label(label)
    log("collision floor: %.0fm square" % (half_extent * 2.0 / 100.0))
    return actor
