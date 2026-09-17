"""Build a small 3D test scene, save it, and render a screenshot.

Creates /Game/AutomationTest/TestScene with a floor, three coloured shapes,
directional + sky lighting, and a camera; renders a PNG into Tools/Unreal/output/.

Run with:  run_unreal.ps1 -Script build_test_scene -Editor
(needs -Editor: a real RHI is required to render anything)
"""

import os
import sys

sys.path.insert(0, os.path.join(os.environ.get("UE_TOOLS_DIR", ""), "lib"))

import unreal

import ue_util
from ue_util import log

CONTENT_PATH = "/Game/AutomationTest"
LEVEL_PATH = CONTENT_PATH + "/TestScene"

# name -> (basic shape asset, location, scale, linear colour, metallic, roughness)
SHAPES = [
    ("Cube",     "/Engine/BasicShapes/Cube.Cube",         (-260.0, 0.0, 60.0),  1.2, (0.80, 0.15, 0.10), 0.0, 0.35),
    ("Sphere",   "/Engine/BasicShapes/Sphere.Sphere",     (   0.0, 0.0, 70.0),  1.4, (0.10, 0.35, 0.85), 0.9, 0.15),
    ("Cylinder", "/Engine/BasicShapes/Cylinder.Cylinder", ( 260.0, 0.0, 70.0),  1.3, (0.15, 0.70, 0.30), 0.0, 0.55),
]
FLOOR = ("/Engine/BasicShapes/Cube.Cube", (0.0, 0.0, -10.0), (14.0, 14.0, 0.2), (0.35, 0.35, 0.38))

CAMERA_LOCATION = (-620.0, -640.0, 340.0)
CAMERA_ROTATION = (0.0, -14.0, 44.0)  # roll, pitch, yaw
RENDER_WIDTH = 1280
RENDER_HEIGHT = 720


def get_editor_world():
    """Editor world, across the 5.x API shuffle."""
    subsystem = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
    if subsystem:
        world = subsystem.get_editor_world()
        if world:
            return world
    return unreal.EditorLevelLibrary.get_editor_world()


def set_component_property(actor, component_class, property_name, value):
    component = actor.get_component_by_class(component_class)
    if component is None:
        raise RuntimeError("%s has no %s" % (actor.get_actor_label(), component_class.__name__))
    component.set_editor_property(property_name, value)
    return component


def make_material(name, color, metallic, roughness):
    """A simple constant-colour material via MaterialEditingLibrary."""
    asset_path = "%s/M_%s" % (CONTENT_PATH, name)
    if unreal.EditorAssetLibrary.does_asset_exist(asset_path):
        unreal.EditorAssetLibrary.delete_asset(asset_path)

    tools = unreal.AssetToolsHelpers.get_asset_tools()
    material = tools.create_asset("M_%s" % name, CONTENT_PATH, unreal.Material,
                                  unreal.MaterialFactoryNew())
    if material is None:
        raise RuntimeError("could not create material M_%s" % name)

    base = unreal.MaterialEditingLibrary.create_material_expression(
        material, unreal.MaterialExpressionConstant3Vector, -400, 0)
    base.set_editor_property("constant", unreal.LinearColor(color[0], color[1], color[2], 1.0))
    unreal.MaterialEditingLibrary.connect_material_property(
        base, "", unreal.MaterialProperty.MP_BASE_COLOR)

    metal = unreal.MaterialEditingLibrary.create_material_expression(
        material, unreal.MaterialExpressionConstant, -400, 180)
    metal.set_editor_property("r", float(metallic))
    unreal.MaterialEditingLibrary.connect_material_property(
        metal, "", unreal.MaterialProperty.MP_METALLIC)

    rough = unreal.MaterialEditingLibrary.create_material_expression(
        material, unreal.MaterialExpressionConstant, -400, 300)
    rough.set_editor_property("r", float(roughness))
    unreal.MaterialEditingLibrary.connect_material_property(
        rough, "", unreal.MaterialProperty.MP_ROUGHNESS)

    unreal.MaterialEditingLibrary.recompile_material(material)
    unreal.EditorAssetLibrary.save_asset(asset_path)
    log("created material %s" % asset_path)
    return asset_path, material


def spawn_mesh(actor_subsystem, mesh_path, location, scale, material, label):
    mesh = unreal.EditorAssetLibrary.load_asset(mesh_path)
    if mesh is None:
        raise RuntimeError("could not load mesh %s" % mesh_path)
    actor = actor_subsystem.spawn_actor_from_object(mesh, unreal.Vector(*location))
    if actor is None:
        raise RuntimeError("could not spawn %s" % mesh_path)
    if isinstance(scale, tuple):
        actor.set_actor_scale3d(unreal.Vector(*scale))
    else:
        actor.set_actor_scale3d(unreal.Vector(scale, scale, scale))
    actor.set_actor_label(label)
    if material is not None:
        actor.static_mesh_component.set_material(0, material)
    log("spawned %s at %s" % (label, location))
    return actor


def render_screenshot(world, output_path):
    """Scene capture -> render target -> PNG. Synchronous, no UI involved."""
    render_target = unreal.RenderingLibrary.create_render_target2d(
        world, RENDER_WIDTH, RENDER_HEIGHT, unreal.TextureRenderTargetFormat.RTF_RGBA8)
    if render_target is None:
        raise RuntimeError("could not create render target")

    actor_subsystem = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    capture = actor_subsystem.spawn_actor_from_class(
        unreal.SceneCapture2D, unreal.Vector(*CAMERA_LOCATION),
        unreal.Rotator(*CAMERA_ROTATION))
    component = capture.capture_component2d
    component.set_editor_property("texture_target", render_target)
    component.set_editor_property("capture_source", unreal.SceneCaptureSource.SCS_FINAL_COLOR_LDR)
    component.set_editor_property("fov_angle", 70.0)
    component.set_editor_property("capture_every_frame", False)
    component.set_editor_property("capture_on_movement", False)

    # Let the frame settle so lighting/shaders are ready before capturing.
    for _ in range(6):
        component.capture_scene()

    directory = os.path.dirname(output_path)
    filename = os.path.basename(output_path)
    if not os.path.isdir(directory):
        os.makedirs(directory)
    unreal.RenderingLibrary.export_render_target(world, render_target, directory, filename)

    actor_subsystem.destroy_actor(capture)

    if not os.path.isfile(output_path):
        raise RuntimeError("export_render_target produced no file at %s" % output_path)
    log("wrote screenshot %s (%d bytes)" % (output_path, os.path.getsize(output_path)))
    return output_path


def main(params):
    level_editor = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    actor_subsystem = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)

    # --- level ---
    # Move off the target map first: the editor may have opened it as the
    # startup map, and deleting the world that is currently loaded leaves the
    # .umap on disk, which then makes new_level fail validation.
    unreal.EditorLoadingAndSavingUtils.new_blank_map(False)
    if unreal.EditorAssetLibrary.does_asset_exist(LEVEL_PATH):
        unreal.EditorAssetLibrary.delete_asset(LEVEL_PATH)
        if unreal.EditorAssetLibrary.does_asset_exist(LEVEL_PATH):
            raise RuntimeError("could not delete the existing level %s" % LEVEL_PATH)
        log("deleted the previous %s" % LEVEL_PATH)
    if not level_editor.new_level(LEVEL_PATH):
        raise RuntimeError("could not create level %s" % LEVEL_PATH)
    log("created level %s" % LEVEL_PATH)

    created_assets = [LEVEL_PATH]

    # --- materials ---
    floor_material_path, floor_material = make_material("Floor", FLOOR[3], 0.0, 0.8)
    created_assets.append(floor_material_path)
    materials = {}
    for name, _mesh, _loc, _scale, color, metallic, roughness in SHAPES:
        path, material = make_material(name, color, metallic, roughness)
        materials[name] = material
        created_assets.append(path)

    # --- geometry ---
    spawn_mesh(actor_subsystem, FLOOR[0], FLOOR[1], FLOOR[2], floor_material, "Floor")
    for name, mesh, location, scale, _color, _metallic, _roughness in SHAPES:
        spawn_mesh(actor_subsystem, mesh, location, scale, materials[name], name)

    # --- lighting ---
    sun = actor_subsystem.spawn_actor_from_class(
        unreal.DirectionalLight, unreal.Vector(0.0, 0.0, 600.0), unreal.Rotator(0.0, -42.0, 140.0))
    sun.set_actor_label("Sun")
    # Light components are reached via get_component_by_class: the per-class
    # attributes (directional_light_component etc.) are editor properties, not
    # Python attributes.
    set_component_property(sun, unreal.DirectionalLightComponent, "intensity", 6.0)

    sky_light = actor_subsystem.spawn_actor_from_class(
        unreal.SkyLight, unreal.Vector(0.0, 0.0, 400.0), unreal.Rotator(0.0, 0.0, 0.0))
    sky_light.set_actor_label("SkyLight")
    set_component_property(sky_light, unreal.SkyLightComponent, "intensity", 1.0)

    atmosphere = actor_subsystem.spawn_actor_from_class(
        unreal.SkyAtmosphere, unreal.Vector(0.0, 0.0, 0.0), unreal.Rotator(0.0, 0.0, 0.0))
    atmosphere.set_actor_label("SkyAtmosphere")

    fog = actor_subsystem.spawn_actor_from_class(
        unreal.ExponentialHeightFog, unreal.Vector(0.0, 0.0, 0.0), unreal.Rotator(0.0, 0.0, 0.0))
    fog.set_actor_label("HeightFog")
    log("added lighting: directional, sky light, sky atmosphere, height fog")

    # --- camera ---
    camera = actor_subsystem.spawn_actor_from_class(
        unreal.CineCameraActor, unreal.Vector(*CAMERA_LOCATION), unreal.Rotator(*CAMERA_ROTATION))
    camera.set_actor_label("SceneCamera")
    log("added camera at %s" % (CAMERA_LOCATION,))

    # --- save ---
    if not level_editor.save_current_level():
        raise RuntimeError("could not save level %s" % LEVEL_PATH)
    unreal.EditorAssetLibrary.save_directory(CONTENT_PATH, only_if_is_dirty=False, recursive=True)
    log("saved level and assets under %s" % CONTENT_PATH)

    # --- screenshot ---
    world = get_editor_world()
    screenshot = os.path.join(ue_util.OUTPUT_DIR, "test_scene.png")
    render_screenshot(world, screenshot)

    actors = actor_subsystem.get_all_level_actors()
    return {
        "level_path": LEVEL_PATH,
        "created_assets": created_assets,
        "actor_count": len(actors),
        "actor_labels": sorted(a.get_actor_label() for a in actors),
        "screenshot": screenshot,
        "screenshot_bytes": os.path.getsize(screenshot),
    }


exit_code = ue_util.run(main, "build_test_scene")

# The full editor stays open after -ExecutePythonScript; close it so the
# verification run gets an exclusive process.
unreal.SystemLibrary.quit_editor()
