"""Finding and inspecting assets.

Loading a mesh here also records its materials, so a later render can force
their textures resident - capturing before textures stream in produces flat,
untextured images.
"""

import os

import unreal

from ue_util import log, warn

# Materials seen by load_mesh()/track_material(), used by ue_render.prepare().
_TRACKED_MATERIALS = set()


# --- loading ----------------------------------------------------------------

def load(path):
    """Load any asset by /Game/... path. Returns None (with a warning) if absent."""
    asset = unreal.EditorAssetLibrary.load_asset(path)
    if asset is None:
        warn("asset not found: %s" % path)
    return asset


def load_mesh(path):
    """Load a StaticMesh and remember its materials for texture pre-streaming."""
    asset = unreal.EditorAssetLibrary.load_asset(path)
    if asset is None or not isinstance(asset, unreal.StaticMesh):
        warn("missing static mesh: %s" % path)
        return None
    try:
        for slot in asset.static_materials:
            if slot.material_interface is not None:
                _TRACKED_MATERIALS.add(slot.material_interface)
    except Exception:
        pass
    return asset


def track_material(material):
    """Register a material so its textures are forced resident before renders."""
    if material is not None:
        _TRACKED_MATERIALS.add(material)


def tracked_materials():
    return set(_TRACKED_MATERIALS)


def exists(path):
    return bool(unreal.EditorAssetLibrary.does_asset_exist(path))


# --- finding ----------------------------------------------------------------

def find(package_path, recursive=True, class_name=None, name_contains=None):
    """List asset paths under a content folder, optionally filtered.

    class_name is matched against the asset's class, e.g. "StaticMesh".
    Uses the Asset Registry, so nothing is loaded.
    """
    registry = unreal.AssetRegistryHelpers.get_asset_registry()
    results = []
    for data in registry.get_assets_by_path(package_path, recursive=recursive):
        package = str(data.package_name)
        if name_contains and name_contains.lower() not in package.lower():
            continue
        if class_name:
            try:
                found = str(data.asset_class_path.asset_name)
            except Exception:
                found = str(getattr(data, "asset_class", "") or "")
            if found != class_name:
                continue
        results.append(package)
    return sorted(results)


# --- inspecting -------------------------------------------------------------

def bounds(mesh):
    """Size / pivot information for a StaticMesh.

    min_z is the mesh's lowest point relative to its pivot. Pivots vary a lot
    (centre-pivoted blocks vs base-pivoted walls), so always check before
    placing rather than assuming zero.
    """
    if isinstance(mesh, str):
        mesh = load_mesh(mesh)
    if mesh is None:
        return None
    box = mesh.get_bounds()
    extent, origin = box.box_extent, box.origin
    return {
        "size": (extent.x * 2.0, extent.y * 2.0, extent.z * 2.0),
        "origin_z": origin.z,
        "min_z": origin.z - extent.z,
    }


def ground_offset(mesh, scale=1.0):
    """Z that puts a mesh's lowest point on z=0, accounting for actor scale.

    A scaled actor's offset scales with it - forgetting that leaves meshes
    floating or sunk.
    """
    data = bounds(mesh)
    if data is None:
        return 0.0
    return -data["min_z"] * float(scale)


def info(path):
    """Everything worth knowing about one asset, without a full load where
    possible: class, bounds, triangles, LODs, material count, file on disk."""
    result = {"asset_path": path, "exists": exists(path)}
    asset = unreal.EditorAssetLibrary.load_asset(path) if result["exists"] else None
    if asset is None:
        return result

    result["class"] = type(asset).__name__
    if isinstance(asset, unreal.StaticMesh):
        result.update(bounds(asset) or {})
        try:
            result["triangles"] = asset.get_num_triangles(0)
            result["lods"] = asset.get_num_lods()
        except Exception:
            pass
        try:
            result["materials"] = [
                str(s.material_interface.get_name()) if s.material_interface else None
                for s in asset.static_materials]
        except Exception:
            pass

    disk = package_file(path)
    if disk:
        result["disk_file"] = disk
        result["disk_size_bytes"] = os.path.getsize(disk)
    return result


def package_file(asset_path):
    """Absolute .uasset/.umap path for a /Game/... asset, or None."""
    package = asset_path.split(".")[0]
    for extension in (".uasset", ".umap"):
        try:
            filename = unreal.PackageTools.package_name_to_filename(package, extension)
        except Exception:
            continue
        if filename:
            full = unreal.Paths.convert_relative_path_to_full(filename)
            if os.path.isfile(full):
                return full
    return None


def verify(asset_paths, require_on_disk=True):
    """(all_ok, [info, ...]) - existence plus a real file on disk."""
    results, all_ok = [], True
    for path in asset_paths:
        item = info(path)
        ok = item.get("exists", False)
        if require_on_disk:
            ok = ok and bool(item.get("disk_file"))
        item["verified"] = ok
        if not ok:
            all_ok = False
            warn("verification failed: %s" % path)
        results.append(item)
    if all_ok:
        log("verified %d asset(s)" % len(results))
    return all_ok, results
