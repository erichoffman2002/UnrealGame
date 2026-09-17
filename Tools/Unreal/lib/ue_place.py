"""Placing geometry: individual actors, and efficient instanced placement.

Two ways to put a mesh in a level:

* place()    - one StaticMeshActor. Use for hero pieces you may want to select
               and nudge by hand later.
* Instancer  - one HISM component holding many transforms. Use for anything
               repeated (ground tiles, vegetation, rubble, scatter).
"""

import math
import random

import unreal

import ue_assets
from ue_util import actor_subsystem, log, rot, safe_set, v, vec_scale, warn

_STATS = {"actors": 0, "instances": 0}


def stats():
    """Running totals, handy for a script's result payload."""
    return dict(_STATS)


def reset_stats():
    _STATS["actors"] = 0
    _STATS["instances"] = 0


# --- individual actors ------------------------------------------------------

def place(mesh_path, location, rotation=None, scale=1.0, label=None,
          on_ground=False):
    """Spawn one StaticMeshActor.

    on_ground=True ignores location.z and instead rests the mesh's lowest point
    on z=0, correcting for scale.
    """
    mesh = ue_assets.load_mesh(mesh_path)
    if mesh is None:
        return None

    if on_ground:
        location = v(location.x, location.y, ue_assets.ground_offset(mesh, scale))

    actor = actor_subsystem().spawn_actor_from_object(
        mesh, location, rotation or rot(0.0))
    if actor is None:
        warn("could not spawn %s" % mesh_path)
        return None
    if scale != 1.0:
        actor.set_actor_scale3d(vec_scale(scale))
    if label:
        actor.set_actor_label(label)
    _STATS["actors"] += 1
    return actor


def spawn(actor_class, location, rotation=None, label=None):
    """Spawn any actor class (lights, volumes, player starts...)."""
    actor = actor_subsystem().spawn_actor_from_class(
        actor_class, location, rotation or rot(0.0))
    if actor is None:
        warn("could not spawn %s" % actor_class)
        return None
    if label:
        actor.set_actor_label(label)
    _STATS["actors"] += 1
    return actor


# --- instanced placement ----------------------------------------------------

class Instancer(object):
    """A HISM component that many transforms are added to.

    Components cannot be constructed directly from Python and made to persist,
    so this goes through SubobjectDataSubsystem, which adds a properly
    registered instance component to a spawned host actor.

    Note: a material applied here must have its "Used with Instanced Static
    Meshes" usage flag set, or it silently renders as the default checkerboard.
    Materials built by ue_material get the flag automatically.
    """

    def __init__(self, mesh_path, material_path=None, cull_start=0, cull_end=0,
                 cast_shadow=True, label=None):
        self.component = None
        self.count = 0

        mesh = ue_assets.load_mesh(mesh_path)
        if mesh is None:
            return

        # StaticMeshActor as host: it always has a root component to attach to.
        host = actor_subsystem().spawn_actor_from_class(
            unreal.StaticMeshActor, v(0, 0, 0), rot(0.0))
        host.set_actor_label(label or ("INST_%s" % mesh_path.rsplit("/", 1)[-1]))
        host.set_mobility(unreal.ComponentMobility.STATIC)

        subobjects = unreal.get_engine_subsystem(unreal.SubobjectDataSubsystem)
        handles = subobjects.k2_gather_subobject_data_for_instance(host)
        if not handles:
            warn("no subobject handles for %s" % mesh_path)
            return
        params = unreal.AddNewSubobjectParams(
            parent_handle=handles[0],
            new_class=unreal.HierarchicalInstancedStaticMeshComponent,
            blueprint_context=None)
        _handle, fail = subobjects.add_new_subobject(params)
        if fail and str(fail).strip() not in ("", "None"):
            warn("add_new_subobject(%s): %s" % (mesh_path, fail))

        component = host.get_component_by_class(
            unreal.HierarchicalInstancedStaticMeshComponent)
        if component is None:
            warn("could not create instancer for %s" % mesh_path)
            return

        component.set_static_mesh(mesh)
        safe_set(component, "cast_shadow", cast_shadow)
        if cull_end:
            safe_set(component, "instance_start_cull_distance", int(cull_start))
            safe_set(component, "instance_end_cull_distance", int(cull_end))
        if material_path:
            material = unreal.EditorAssetLibrary.load_asset(material_path)
            if material is None:
                warn("missing material: %s" % material_path)
            else:
                # Per-component override; the source asset is never touched.
                component.set_material(0, material)
                ue_assets.track_material(material)

        self.component = component
        self.mesh = mesh
        _STATS["actors"] += 1

    def add(self, location, rotation=None, scale=1.0):
        if self.component is None:
            return False
        self.component.add_instance(
            unreal.Transform(location, rotation or rot(0.0), vec_scale(scale)),
            False)
        self.count += 1
        _STATS["instances"] += 1
        return True


def instancer(mesh_path, **kwargs):
    """Convenience wrapper returning an Instancer."""
    return Instancer(mesh_path, **kwargs)


# --- repeated-placement patterns -------------------------------------------

def grid(inst, half_extent, spacing, z=0.0, scale=1.0, rotate_steps=True):
    """Fill a square with instances - ground tiles, paving, fields.

    rotate_steps turns each tile by a varying multiple of 90 degrees, which
    breaks up the obvious repeating pattern a tiling texture otherwise shows.
    """
    steps = int((half_extent * 2) // spacing)
    start = -half_extent + spacing * 0.5
    for ix in range(steps):
        for iy in range(steps):
            yaw = 90.0 * ((ix * 7 + iy * 3) % 4) if rotate_steps else 0.0
            inst.add(v(start + ix * spacing, start + iy * spacing, z),
                     rot(yaw), scale)
    return steps * steps


def scatter_ring(inst, count, radius_min, radius_max, z=0.0, scale_range=(1.0, 1.0),
                 tilt=0.0, seed=0, skip=None):
    """Instances in an annulus - treelines, rock rings, boundary planting.

    skip(x, y) may return True to reject a position, e.g. to keep a path clear.
    """
    r = random.Random(seed)
    placed = 0
    for i in range(count):
        angle = (i / float(count)) * math.tau + r.uniform(-0.1, 0.1)
        radius = r.uniform(radius_min, radius_max)
        x, y = math.cos(angle) * radius, math.sin(angle) * radius
        if skip and skip(x, y):
            continue
        inst.add(v(x, y, z),
                 rot(r.uniform(0, 360), r.uniform(-tilt, tilt), r.uniform(-tilt, tilt)),
                 r.uniform(*scale_range))
        placed += 1
    return placed


def scatter_cluster(inst, centre, count, radius, z=0.0, scale_range=(1.0, 1.0),
                    tilt=0.0, seed=0, skip=None):
    """Instances clumped around a point - rubble at a collapse, undergrowth
    against a wall. Uses sqrt distribution so clusters read as evenly filled."""
    r = random.Random(seed)
    cx, cy = centre
    placed = 0
    for _ in range(count):
        angle = r.uniform(0, math.tau)
        dist = radius * math.sqrt(r.random())
        x, y = cx + math.cos(angle) * dist, cy + math.sin(angle) * dist
        if skip and skip(x, y):
            continue
        inst.add(v(x, y, z),
                 rot(r.uniform(0, 360), r.uniform(-tilt, tilt), r.uniform(-tilt, tilt)),
                 r.uniform(*scale_range))
        placed += 1
    return placed
