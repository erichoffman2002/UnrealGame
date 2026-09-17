"""Creating simple materials, for when an existing one cannot be used.

Prefer reusing a pack's own materials. Build one here when you need a material
that works on instanced meshes: many library material instances lack the
"Used with Instanced Static Meshes" usage flag and silently fall back to the
default checkerboard on a HISM. A material created here gets the flag set by
the engine on first use.

Source textures are only referenced - never modified.
"""

import unreal

import ue_assets
from ue_util import log, safe_set, warn


def tiling_material(asset_path, diffuse=None, normal=None, tiling=2.5,
                    roughness=0.93, metallic=None, overwrite=True):
    """A basic tiling surface: diffuse + optional normal + constant roughness.

    asset_path is the full /Game/... path of the material to create.
    Returns the path, or None on failure.
    """
    folder, name = asset_path.rsplit("/", 1)

    if unreal.EditorAssetLibrary.does_asset_exist(asset_path):
        if not overwrite:
            return asset_path
        unreal.EditorAssetLibrary.delete_asset(asset_path)

    material = unreal.AssetToolsHelpers.get_asset_tools().create_asset(
        name, folder, unreal.Material, unreal.MaterialFactoryNew())
    if material is None:
        warn("could not create material %s" % asset_path)
        return None

    mel = unreal.MaterialEditingLibrary
    uv = mel.create_material_expression(
        material, unreal.MaterialExpressionTextureCoordinate, -900, 0)
    safe_set(uv, "u_tiling", float(tiling))
    safe_set(uv, "v_tiling", float(tiling))

    if diffuse:
        texture = unreal.EditorAssetLibrary.load_asset(diffuse)
        if texture is None:
            warn("diffuse texture missing: %s" % diffuse)
        else:
            node = mel.create_material_expression(
                material, unreal.MaterialExpressionTextureSample, -600, -200)
            safe_set(node, "texture", texture)
            mel.connect_material_expressions(uv, "", node, "UVs")
            mel.connect_material_property(
                node, "RGB", unreal.MaterialProperty.MP_BASE_COLOR)

    if normal:
        texture = unreal.EditorAssetLibrary.load_asset(normal)
        if texture is None:
            warn("normal texture missing: %s" % normal)
        else:
            node = mel.create_material_expression(
                material, unreal.MaterialExpressionTextureSample, -600, 200)
            # Sampler type must be set before the texture, or it samples as colour.
            safe_set(node, "sampler_type",
                     unreal.MaterialSamplerType.SAMPLERTYPE_NORMAL)
            safe_set(node, "texture", texture)
            mel.connect_material_expressions(uv, "", node, "UVs")
            mel.connect_material_property(
                node, "RGB", unreal.MaterialProperty.MP_NORMAL)

    _constant(mel, material, roughness, 500, unreal.MaterialProperty.MP_ROUGHNESS)
    if metallic is not None:
        _constant(mel, material, metallic, 700, unreal.MaterialProperty.MP_METALLIC)

    mel.recompile_material(material)
    unreal.EditorAssetLibrary.save_asset(asset_path)
    ue_assets.track_material(material)
    log("built material %s" % asset_path)
    return asset_path


def color_material(asset_path, color, roughness=0.5, metallic=0.0, overwrite=True):
    """A flat coloured material. color is an (r, g, b) tuple in linear space."""
    folder, name = asset_path.rsplit("/", 1)

    if unreal.EditorAssetLibrary.does_asset_exist(asset_path):
        if not overwrite:
            return asset_path
        unreal.EditorAssetLibrary.delete_asset(asset_path)

    material = unreal.AssetToolsHelpers.get_asset_tools().create_asset(
        name, folder, unreal.Material, unreal.MaterialFactoryNew())
    if material is None:
        warn("could not create material %s" % asset_path)
        return None

    mel = unreal.MaterialEditingLibrary
    base = mel.create_material_expression(
        material, unreal.MaterialExpressionConstant3Vector, -400, 0)
    safe_set(base, "constant", unreal.LinearColor(color[0], color[1], color[2], 1.0))
    mel.connect_material_property(base, "", unreal.MaterialProperty.MP_BASE_COLOR)

    _constant(mel, material, roughness, 300, unreal.MaterialProperty.MP_ROUGHNESS)
    _constant(mel, material, metallic, 180, unreal.MaterialProperty.MP_METALLIC)

    mel.recompile_material(material)
    unreal.EditorAssetLibrary.save_asset(asset_path)
    ue_assets.track_material(material)
    log("built material %s" % asset_path)
    return asset_path


def _constant(mel, material, value, y, prop):
    node = mel.create_material_expression(
        material, unreal.MaterialExpressionConstant, -600, y)
    safe_set(node, "r", float(value))
    mel.connect_material_property(node, "", prop)
    return node
