"""Verify, in a fresh Unreal process, that the test scene persisted.

Creates nothing. Checks the Asset Registry, EditorAssetLibrary and the actual
files on disk, then loads the map and counts its actors.

Run with:  run_unreal.ps1 -Script verify_scene
"""

import os
import sys

sys.path.insert(0, os.path.join(os.environ.get("UE_TOOLS_DIR", ""), "lib"))

import unreal

import ue_util
from ue_util import log, error

CONTENT_PATH = "/Game/AutomationTest"
LEVEL_PATH = CONTENT_PATH + "/TestScene"
EXPECTED_MATERIALS = ["M_Floor", "M_Cube", "M_Sphere", "M_Cylinder"]


def disk_file(package_name):
    for extension in (".umap", ".uasset"):
        try:
            filename = unreal.PackageTools.package_name_to_filename(package_name, extension)
        except Exception:
            continue
        if filename:
            full = unreal.Paths.convert_relative_path_to_full(filename)
            if os.path.isfile(full):
                return full
    return None


def check(asset_path):
    info = {
        "asset_path": asset_path,
        "exists": bool(unreal.EditorAssetLibrary.does_asset_exist(asset_path)),
        "disk_file": disk_file(asset_path),
    }
    info["disk_size_bytes"] = os.path.getsize(info["disk_file"]) if info["disk_file"] else None
    info["ok"] = info["exists"] and bool(info["disk_file"])
    if info["ok"]:
        log("verified %s (%s bytes)" % (asset_path, info["disk_size_bytes"]))
    else:
        error("missing or unsaved: %s (%s)" % (asset_path, info))
    return info


def main(params):
    registry = unreal.AssetRegistryHelpers.get_asset_registry()
    registry.scan_paths_synchronous([CONTENT_PATH], force_rescan=True)

    checks = [check(LEVEL_PATH)]
    for name in EXPECTED_MATERIALS:
        checks.append(check("%s/%s" % (CONTENT_PATH, name)))

    listing = [str(p) for p in unreal.EditorAssetLibrary.list_assets(
        CONTENT_PATH, recursive=True, include_folder=False)]

    # Load the saved map in this fresh process and count what is actually in it.
    actor_labels = []
    load_error = None
    try:
        unreal.EditorLoadingAndSavingUtils.load_map(LEVEL_PATH)
        actor_subsystem = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
        actor_labels = sorted(a.get_actor_label() for a in actor_subsystem.get_all_level_actors())
        log("loaded map, found %d actors: %s" % (len(actor_labels), ", ".join(actor_labels)))
    except Exception as exc:
        load_error = str(exc)
        log("could not load the map in this process: %s" % exc, "warning")

    if not all(item["ok"] for item in checks):
        raise RuntimeError("one or more assets failed verification")

    return {
        "verified": True,
        "checks": checks,
        "asset_listing": listing,
        "actor_count": len(actor_labels),
        "actor_labels": actor_labels,
        "map_load_error": load_error,
    }


ue_util.run(main, "verify_scene")
