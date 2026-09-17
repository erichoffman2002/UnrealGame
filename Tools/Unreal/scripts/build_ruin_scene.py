"""Build 'The Sunken Shrine' - a small, hand-composed fantasy ruin environment.

Monolith ruins + rocks, KiteDemo vegetation and trees. Everything is placed
deliberately: a raised shrine plaza with a damaged statue on axis, a flanking
colonnade with two collapsed columns, an arch gateway to the south, broken
walls east and west, rubble where the columns fell, and a rock/pine treeline
enclosing the clearing. Vegetation reclaims everything except the worn
central path.

This script is now only composition - every Unreal operation comes from the
reusable library in Tools/Unreal/lib. Nothing in the asset packs is modified:
meshes and textures are referenced, and material overrides are applied
per-component.

Run with:  run_unreal.ps1 -Script build_ruin_scene -Editor
"""

import math
import os
import random
import sys

sys.path.insert(0, os.path.join(os.environ.get("UE_TOOLS_DIR", ""), "lib"))

import unreal

import ue_level
import ue_lighting
import ue_material
import ue_place
import ue_render
import ue_util
from ue_util import log, rot, v

# --------------------------------------------------------------------------
# Content paths
# --------------------------------------------------------------------------
LEVEL_PATH = "/Game/FantasyRuins/L_SunkenShrine"
FOLDER = "/Game/FantasyRuins"
RUINS = "/Game/ParagonProps/Monolith/Ruins/Meshes/"
NROCK = "/Game/ParagonProps/Monolith/Rocks/Meshes/"
KITE = "/Game/KiteDemo/Environments/"
GAMEMODE = "/Game/FirstPerson/Blueprints/BP_FirstPersonGameMode"

GROUND_MESH = "/Engine/BasicShapes/Plane.Plane"
GROUND_MAT = FOLDER + "/M_RuinGround"
GROUND_TEX_D = KITE + "GroundTiles/RockyPath/T_GDC_StonePath_Tile_D_R"
GROUND_TEX_N = KITE + "GroundTiles/RockyPath/T_GDC_StonePath_Tile_N"

# --------------------------------------------------------------------------
# Layout (cm). +X is north; the approach runs south -> north.
# Offsets come from probed mesh bounds, so pieces sit correctly on the ground.
# --------------------------------------------------------------------------
PLAZA_Z = -12.0           # sink the 46.5cm slab so its lip is a steppable ~35cm
PLAZA_TOP = PLAZA_Z + 46.5
GROUND_HALF = 12000.0     # 240m square: the edge must never meet sky on camera
TILE = 500.0

COLUMN_X = [-550.0, -150.0, 250.0]
COLUMN_Y = 500.0
BLOCK_H = 250.0           # pillar blocks are 2.5m cubes, pivot at centre
BLOCK_HALF = 125.0

SEED = 20260916


def rng():
    return random.Random(SEED)


def on_path(x, y):
    """The worn southern approach, kept clear of planting."""
    return x < -650 and abs(y) < 240


def on_plaza(x, y):
    return abs(x) < 700 and abs(y) < 700


# --------------------------------------------------------------------------
# Scene
# --------------------------------------------------------------------------
def build_ground():
    ue_material.tiling_material(GROUND_MAT, diffuse=GROUND_TEX_D,
                                normal=GROUND_TEX_N, tiling=2.5, roughness=0.93)
    ground = ue_place.instancer(GROUND_MESH, material_path=GROUND_MAT,
                                cast_shadow=False, label="INST_ground")
    tiles = ue_place.grid(ground, GROUND_HALF, TILE, z=0.0,
                          scale=TILE / 100.0, rotate_steps=True)
    ue_level.add_collision_floor(GROUND_HALF)
    log("ground: %d tiles" % tiles)


def build_shrine():
    ue_place.place(RUINS + "Ruins_DecoFloor", v(0, 0, PLAZA_Z), label="Plaza")
    ue_place.place(RUINS + "MonoStatueBase", v(450, 0, PLAZA_TOP), rot(180.0),
                   label="StatueBase")
    ue_place.place(RUINS + "MonoStatue_Damaged",
                   v(450, 0, PLAZA_TOP + 87.5 + 40.0), rot(188.0), label="Statue")

    # Trim along the south lip, one piece broken.
    for i, y_off in enumerate([-500.0, -250.0, 250.0, 500.0]):
        mesh = "JungleTrim01Broken_250" if i == 1 else "JungleTrim01_250"
        ue_place.place(RUINS + mesh, v(-690, y_off, PLAZA_TOP), rot(90.0),
                       label="Trim_%d" % i)


def build_colonnade():
    layout = [
        (COLUMN_X[0], -COLUMN_Y, 2, True, "SW"),
        (COLUMN_X[1], -COLUMN_Y, 2, True, "W"),
        (COLUMN_X[2], -COLUMN_Y, 1, True, "NW_broken"),
        (COLUMN_X[0], COLUMN_Y, 2, True, "SE"),
        (COLUMN_X[1], COLUMN_Y, 1, False, "E_stump"),
        (COLUMN_X[2], COLUMN_Y, 2, True, "NE"),
    ]
    variants = ["JunglePillarBlock_01A", "JunglePillarBlock_01B",
                "JunglePillarBlock_01C"]
    r = rng()

    for x, y, blocks, capped, note in layout:
        for i in range(blocks):
            ue_place.place(RUINS + variants[r.randrange(len(variants))],
                           v(x, y, PLAZA_TOP + BLOCK_HALF + i * BLOCK_H),
                           rot(r.choice([0.0, 90.0, 180.0, 270.0])),
                           label="Column_%s_%d" % (note, i))
        if capped:
            ue_place.place(RUINS + "JunglePillarBlockCrumble01_A",
                           v(x, y, PLAZA_TOP + blocks * BLOCK_H),
                           rot(r.uniform(0.0, 360.0)), label="ColumnCap_%s" % note)

    # A toppled column lying across the east side, as if it fell outward.
    fallen_x = COLUMN_X[1]
    for i in range(3):
        ue_place.place(RUINS + variants[i % len(variants)],
                       v(fallen_x + r.uniform(-20, 20),
                         COLUMN_Y + 260 + i * 255, PLAZA_TOP + BLOCK_HALF),
                       rot(r.uniform(-8, 8), 90.0), label="Fallen_%d" % i)
    ue_place.place(RUINS + "JunglePillarBlockCrumble01_A",
                   v(fallen_x + 30, COLUMN_Y + 260 + 3 * 255, PLAZA_TOP),
                   rot(20.0, 80.0), label="Fallen_Cap")


def build_walls():
    for y_sign in (-1.0, 1.0):
        for x in (-800.0, 800.0):
            mesh = "JungleWall_02A" if x < 0 else "JungleWall_02B"
            ue_place.place(RUINS + mesh, v(x, y_sign * 1150.0, 0.0),
                           label="Wall_%s_%s" % (int(x), int(y_sign)))
    ue_place.place(RUINS + "JungleWall_02A", v(1150.0, -450.0, 0.0), rot(90.0),
                   label="Wall_N1")
    ue_place.place(RUINS + "JungleWall_02B", v(1150.0, 450.0, 0.0), rot(90.0),
                   label="Wall_N2")

    ue_place.place(RUINS + "Aclove_Wall_Broken", v(-1150.0, -1150.0, 0.0),
                   rot(45.0), label="Alcove_SW")
    ue_place.place(RUINS + "Aclove_Wall_Crumble", v(1150.0, 1150.0, 0.0),
                   rot(225.0), label="Alcove_NE")

    ue_place.place(RUINS + "JungleArch_01A", v(-1000.0, 0.0, 0.0), label="Gateway")
    ue_place.place(RUINS + "JungleArch_01B", v(-1700.0, 0.0, 0.0), rot(3.0),
                   label="OuterArch")


def build_rubble():
    pieces = ["JunglePillarBlockPiece_05A", "JunglePillarBlockPiece_05B",
              "JunglePillarBlockPiece_05C", "JunglePillarBlockPiece_01A",
              "JunglePillarBlockPiece_02A", "JunglePillarBlockPiece_03A"]
    inst = [ue_place.instancer(RUINS + name, cull_end=12000) for name in pieces]

    # Clusters at the failure points, not scattered evenly.
    clusters = [
        (COLUMN_X[2], -COLUMN_Y, 380.0, 9),
        (COLUMN_X[1], COLUMN_Y, 300.0, 7),
        (COLUMN_X[1], COLUMN_Y + 1100.0, 420.0, 8),
        (-700.0, 1150.0, 340.0, 6),
        (1150.0, 0.0, 300.0, 5),
        (-1000.0, -500.0, 300.0, 5),
    ]
    r = rng()
    for i, (cx, cy, radius, count) in enumerate(clusters):
        for _ in range(count):
            angle = r.uniform(0, math.tau)
            dist = radius * math.sqrt(r.random())
            inst[r.randrange(len(inst))].add(
                v(cx + math.cos(angle) * dist, cy + math.sin(angle) * dist,
                  BLOCK_HALF * r.uniform(0.35, 0.6)),
                rot(r.uniform(0, 360), r.uniform(-25, 25), r.uniform(-20, 20)),
                r.uniform(0.7, 1.15))

    ue_place.place(RUINS + "JungleRubblePile_A",
                   v(COLUMN_X[1] + 120, COLUMN_Y + 1500, 0.0), rot(28.0),
                   label="RubblePile_E")
    ue_place.place(RUINS + "JungleRubblePile_A", v(-1250.0, -900.0, 0.0),
                   rot(200.0), label="RubblePile_SW")


def build_rocks():
    """Natural rock frame. Only closed meshes are used - the KiteDemo
    Mountain_RockFace and Cliff meshes are single-sided terrain facades and
    read as hollow shells when placed free-standing."""
    r = rng()
    big = ue_place.instancer(NROCK + "SM_RockNordic_Small_01", cull_end=25000)
    mid = ue_place.instancer(NROCK + "SM_RockNordic_Small_03", cull_end=20000)
    small = ue_place.instancer(NROCK + "SM_RockNordic_05", cull_end=9000)
    river = ue_place.instancer(KITE + "Rocks/River_Rock_01/SM_River_Rock_01",
                               cull_end=6000)

    for i in range(26):
        angle = (i / 26.0) * math.tau + r.uniform(-0.09, 0.09)
        radius = r.uniform(2100, 3300)
        comp = big if r.random() < 0.45 else mid
        z = 49.7 if comp is big else 15.4
        comp.add(v(math.cos(angle) * radius, math.sin(angle) * radius,
                   z * r.uniform(0.3, 0.8)),
                 rot(r.uniform(0, 360), r.uniform(-6, 6), r.uniform(-6, 6)),
                 r.uniform(0.85, 1.5))

    ue_place.place(KITE + "Rocks/Medium_Boulder_001/Medium_Boulder_001",
                   v(-1500, 1150, 0.0), rot(70.0), 1.2, label="Boulder_SW",
                   on_ground=True)

    for _ in range(70):
        angle = r.uniform(0, math.tau)
        radius = r.uniform(900, 3000)
        (small if r.random() < 0.5 else river).add(
            v(math.cos(angle) * radius, math.sin(angle) * radius, 0.0),
            rot(r.uniform(0, 360), r.uniform(-12, 12), r.uniform(-12, 12)),
            r.uniform(0.6, 1.4))

    for loc, yaw in [((2350, -300), 20), ((-2250, 900), 140), ((1500, 2100), 260)]:
        ue_place.place(KITE + "Rocks/Scree002/SM_Scree002a",
                       v(loc[0], loc[1], 0.0), rot(yaw), label="Scree",
                       on_ground=True)


def build_trees():
    tall = ue_place.instancer(KITE + "Trees/ScotsPineTall_01/ScotsPineTall_01",
                              cull_end=30000)

    def keep_south_open(x, y):
        angle = math.atan2(y, x)
        return -2.45 < angle - math.pi < 0.55 and random.Random(
            int(x) ^ int(y)).random() < 0.55

    ue_place.scatter_ring(tall, 30, 2900, 3800, z=8.5, scale_range=(0.8, 1.25),
                          tilt=3.0, seed=SEED, skip=keep_south_open)

    ue_place.place(KITE + "Trees/ScotsPine_01/ScotsPine_01", v(-1800, 3100, 0.0),
                   rot(40.0), 0.9, label="Pine_W", on_ground=True)
    ue_place.place(KITE + "Trees/ScotsPine_01/ScotsPine_01", v(2200, 2050, 0.0),
                   rot(215.0), 1.0, label="Pine_NE", on_ground=True)

    for loc, yaw in [((-1650, 950), 30), ((1250, -1750), 190)]:
        ue_place.place(KITE + "Trees/Tree_Stump_01/Tree_Stump_01",
                       v(loc[0], loc[1], 0.0), rot(yaw), label="Stump",
                       on_ground=True)


def build_vegetation():
    """Denser at edges and against stone; the central path stays worn."""
    r = rng()
    grass = ue_place.instancer(KITE + "Foliage/Grass/FieldGrass/SM_FieldGrass_01",
                               cull_end=7000, cast_shadow=False)
    fern1 = ue_place.instancer(KITE + "Foliage/Ferns/SM_Fern_01", cull_end=9000)
    fern2 = ue_place.instancer(KITE + "Foliage/Ferns/SM_Fern_02", cull_end=9000)
    heather = ue_place.instancer(
        KITE + "Foliage/Flowers/Heather/SM_Heather_Mesh_Clumps2",
        cull_end=8000, cast_shadow=False)
    butter = ue_place.instancer(
        KITE + "Foliage/Flowers/Buttercup/SM_Buttercup_Patch_01",
        cull_end=7000, cast_shadow=False)
    yarrow = ue_place.instancer(KITE + "Foliage/Flowers/Yarrow/SM_Yarrow",
                                cull_end=5000, cast_shadow=False)
    leaves = ue_place.instancer(KITE + "Foliage/Leaves/SM_DeadLeaves_Flat",
                                cull_end=5000, cast_shadow=False)
    bush = ue_place.instancer(KITE + "Foliage/BogMyrtleBush_01/BogMyrtleBush_01",
                              cull_end=12000)

    # Broad grass, thinning towards the shrine.
    placed = attempts = 0
    while placed < 1700 and attempts < 14000:
        attempts += 1
        x, y = r.uniform(-3600, 3600), r.uniform(-3600, 3600)
        radius = math.hypot(x, y)
        if radius > 3700 or on_path(x, y):
            continue
        if r.random() > min(1.0, 0.35 + radius / 2600.0):
            continue
        if on_plaza(x, y) and r.random() < 0.82:
            continue
        grass.add(v(x, y, 2.2), rot(r.uniform(0, 360)), r.uniform(0.75, 1.5))
        placed += 1

    # Ferns against stone and in shade.
    shade_points = [(-1000, 0), (1150, -450), (1150, 450), (-800, -1150),
                    (800, 1150), (-1150, -1150), (1150, 1150),
                    (COLUMN_X[2], -COLUMN_Y), (COLUMN_X[1], COLUMN_Y + 1100),
                    (-1700, 0), (-1900, 1400), (1750, -1500)]
    for px, py in shade_points:
        for _ in range(r.randint(14, 22)):
            angle = r.uniform(0, math.tau)
            dist = r.uniform(120, 520)
            x, y = px + math.cos(angle) * dist, py + math.sin(angle) * dist
            if on_path(x, y):
                continue
            (fern1 if r.random() < 0.6 else fern2).add(
                v(x, y, 1.1), rot(r.uniform(0, 360)), r.uniform(0.7, 1.25))

    # Overgrowth reclaiming the column bases.
    for x in COLUMN_X:
        for y in (-COLUMN_Y, COLUMN_Y):
            for _ in range(r.randint(4, 7)):
                angle = r.uniform(0, math.tau)
                dist = r.uniform(140, 260)
                heather.add(v(x + math.cos(angle) * dist,
                              y + math.sin(angle) * dist, PLAZA_TOP + 4.7),
                            rot(r.uniform(0, 360)), r.uniform(0.6, 1.0))

    # Cracks in the plaza.
    for _ in range(90):
        if r.random() < 0.35:
            continue
        (grass if r.random() < 0.6 else heather).add(
            v(r.uniform(-690, 690), r.uniform(-690, 690), PLAZA_TOP + 2.0),
            rot(r.uniform(0, 360)), r.uniform(0.45, 0.85))
    for _ in range(60):
        leaves.add(v(r.uniform(-900, 900), r.uniform(-900, 900), PLAZA_TOP + 0.8),
                   rot(r.uniform(0, 360)), r.uniform(0.8, 1.5))

    # Flower accents in the open clearing.
    for _ in range(260):
        angle = r.uniform(0, math.tau)
        radius = r.uniform(1100, 3300)
        x, y = math.cos(angle) * radius, math.sin(angle) * radius
        if on_path(x, y):
            continue
        (butter if r.random() < 0.65 else heather).add(
            v(x, y, 7.7), rot(r.uniform(0, 360)), r.uniform(0.7, 1.2))
    for _ in range(55):
        angle = r.uniform(0, math.tau)
        radius = r.uniform(1000, 3000)
        yarrow.add(v(math.cos(angle) * radius, math.sin(angle) * radius, 8.0),
                   rot(r.uniform(0, 360)), r.uniform(0.8, 1.4))

    # Bushes softening the wall bases and treeline.
    for _ in range(80):
        angle = r.uniform(0, math.tau)
        radius = r.uniform(1500, 3400)
        x, y = math.cos(angle) * radius, math.sin(angle) * radius
        if on_path(x, y):
            continue
        bush.add(v(x, y, 13.6), rot(r.uniform(0, 360)), r.uniform(0.9, 1.8))


# --------------------------------------------------------------------------
def main(params):
    ue_place.reset_stats()
    ue_level.create(LEVEL_PATH)

    build_ground()
    build_shrine()
    build_colonnade()
    build_walls()
    build_rubble()
    build_rocks()
    build_trees()
    build_vegetation()

    ue_lighting.daylight()

    ue_level.add_player_start(v(-2600.0, 0.0, 120.0), rot(0.0))
    ue_level.set_game_mode(GAMEMODE)

    counts = ue_place.stats()
    log("placed %(actors)d actors and %(instances)d instances" % counts)

    ue_level.save(FOLDER)
    return {"level_path": LEVEL_PATH, "actors": counts["actors"],
            "instances": counts["instances"]}


VIEWS = [
    ("ruin_scene.png", v(-2950.0, -1750.0, 780.0), rot(29.0, -8.0)),
    ("ruin_eye.png", v(-2450.0, 0.0, 165.0), rot(0.0, -1.0)),
    ("ruin_top.png", v(-2600.0, -2600.0, 3400.0), rot(45.0, -36.0)),
]

exit_code = ue_util.run(main, "build_ruin_scene")

# The editor is launched with -ExecCmds so it stays alive after this returns;
# the capture pass shuts it down when the last view is written.
if exit_code:
    unreal.SystemLibrary.quit_editor()
else:
    ue_render.capture_views(VIEWS)
