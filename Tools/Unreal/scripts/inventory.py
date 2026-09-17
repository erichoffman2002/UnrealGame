"""Read-only inventory of /Game via the Asset Registry.

Reads registry metadata only: nothing is loaded, modified, saved or compiled.

Run with:  run_unreal.ps1 -Script inventory
Params:    {"root": "/Game", "top": 40}
"""

import os
import sys
from collections import Counter, defaultdict

sys.path.insert(0, os.path.join(os.environ.get("UE_TOOLS_DIR", ""), "lib"))

import unreal

import ue_util
from ue_util import log

# Substring -> bucket, for locating the interesting content by name/path.
KEYWORDS = [
    ("foliage", ("foliage", "tree", "grass", "plant", "bush", "fern", "leaf", "leaves",
                 "shrub", "vegetation", "flower", "weed", "ivy", "moss")),
    ("rock", ("rock", "cliff", "boulder", "stone", "gravel", "pebble")),
    ("landscape", ("landscape", "terrain", "ground", "dirt", "soil", "sand", "mud", "grassland")),
    ("ruins", ("ruin", "column", "pillar", "arch", "wall", "statue", "temple", "brick",
               "rubble", "debris", "monument", "shrine")),
    ("water", ("water", "river", "lake", "ocean", "waterfall", "pond")),
]


def bucket_for(path_lower):
    hits = []
    for name, words in KEYWORDS:
        if any(word in path_lower for word in words):
            hits.append(name)
    return hits


def main(params):
    root = params.get("root", "/Game")
    top = int(params.get("top", 40))

    registry = unreal.AssetRegistryHelpers.get_asset_registry()
    registry.wait_for_completion()
    assets = registry.get_assets_by_path(root, recursive=True)
    log("asset registry returned %d assets under %s" % (len(assets), root))

    by_class = Counter()
    by_top_folder = Counter()
    folder_class = defaultdict(Counter)
    class_by_top = defaultdict(Counter)
    buckets = defaultdict(lambda: defaultdict(Counter))
    maps = []

    for data in assets:
        package = str(data.package_name)
        try:
            class_name = str(data.asset_class_path.asset_name)
        except Exception:
            class_name = str(getattr(data, "asset_class", "") or "Unknown")

        parts = package.split("/")            # ['', 'Game', 'ParagonProps', 'Agora', ...]
        top_folder = parts[2] if len(parts) > 2 else "(root)"
        # One level below the top folder, e.g. ParagonProps/Agora
        sub = "/".join(parts[2:4]) if len(parts) > 4 else top_folder

        by_class[class_name] += 1
        by_top_folder[top_folder] += 1
        class_by_top[top_folder][class_name] += 1
        folder_class[sub][class_name] += 1

        if class_name == "World":
            maps.append(package)

        for name in bucket_for(package.lower()):
            buckets[name][sub][class_name] += 1

    def flatten(counter_map, limit=None):
        out = {}
        for key, counter in counter_map.items():
            out[key] = dict(counter.most_common(limit))
        return out

    summary = {
        "root": root,
        "total_assets": len(assets),
        "by_class": dict(by_class.most_common(top)),
        "by_top_folder": dict(by_top_folder.most_common()),
        "class_by_top_folder": flatten(class_by_top, 12),
        "by_subfolder": dict(sorted(
            ((k, sum(v.values())) for k, v in folder_class.items()),
            key=lambda kv: kv[1], reverse=True)[:top]),
        "subfolder_detail": flatten(
            {k: v for k, v in folder_class.items()
             if k.startswith("ParagonProps") or k.startswith("KiteDemo")}, 10),
        "maps": sorted(maps),
        "buckets": {name: flatten(subs, 8) for name, subs in buckets.items()},
    }

    log("classes: %d, top folders: %d, maps: %d"
        % (len(by_class), len(by_top_folder), len(maps)))
    return summary


ue_util.run(main, "inventory")
