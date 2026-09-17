---
name: ue-mcp-water
description: Use when creating, editing or debugging Unreal Water plugin bodies through ue-mcp - rivers, lakes, oceans, water zones, buoyancy and landscape carving. Covers the materials a programmatically created water body does NOT get, why a river flows sideways or not at all, and the ordering that crashes the editor. Pulls in any time the user asks for a river, stream, lake, water, flow, current, or a floating object.
---

# Water bodies through ue-mcp

## Danger first

**Never touch a water body property in the same sequence as a landscape edit.**
Writing `bAffectsLandscape` (or any water property that re-runs the landscape brush)
while an edit-layer update from `landscape(import_heightmap)` / `set_height_region` /
`sculpt` is still pending hard-asserts and takes the editor down:

```
Assertion failed: Component->GetLayerUpdateFlagPerMode() == 0
[LandscapeEditLayers.cpp:7292]
```

Unsaved level work is lost. The safe order is:

1. Write the water property **first**, while the landscape is idle
2. `level(save)`
3. *Then* do the landscape edit
4. `level(save)` again

Landscape-edit-then-water-toggle is what crashes. *Verified 2026-09-17, UE 5.8 /
ue-mcp bridge API v1. Recheck after any engine or bridge upgrade; if fixed upstream,
delete this section.*

## The materials a programmatic water body does not get

This is the big one, and it costs hours because nothing errors.

Placing a water body through the **editor UI** populates its material slots. Creating
one through **ue-mcp does not.** Read them back immediately after creating any water
body:

```
level(get_actor_details, actorLabel="River_Main")        # find the component
reflection(reflect_instance,
           objectPath=".../WaterBodyRiverComponent",
           filter="Material", includeValues=true)
```

| Slot | If `None` | Engine default for a river |
|---|---|---|
| `WaterMaterial` | no surface renders | `/Water/Materials/WaterSurface/Water_Material_River` |
| **`WaterInfoMaterial`** | **velocity never reaches the surface - the river cannot flow** | `/Water/Materials/WaterInfo/DrawWaterInfo` |
| `WaterLODMaterial` | no distant water | `/Water/Materials/WaterSurface/LODs/Water_Material_River_LOD` |
| `UnderwaterPostProcessMaterial` | no underwater tint | `/Water/Materials/PostProcessing/M_UnderWater_PostProcess_Volume` |

`WaterInfoMaterial` draws the body into the WaterZone's **water info texture**, which is
where the surface shader reads velocity from. With it unset, depth still reaches the
texture but velocity reads as a hard zero - so the river renders, looks correct when
still, and moves in a direction that has nothing to do with the spline.

Write them with `level(set_water_body_property)`. `reflection(epic_set_properties)`
reports `returnValue: false` and writes nothing on these.

## Flow: speed and direction are different dials

Conflating these is the easiest way to burn an afternoon.

| Want to change | Set | Lives on |
|---|---|---|
| **Direction** of flow | `WaterVelocityScalar` and `WaterVelocity` | `WaterSplineMetadata` (the actor) |
| **Speed** the surface appears to move | `River Flowmap Speed` | the material instance |

Lowering velocity to slow the water down **destroys the direction signal.** The flowmap
normalises velocity against `MaxFlowVelocity` (default 1024), so a velocity of 3 is
0.3% and quantisation noise dominates the direction. Slow water is a *material*
setting; keep velocity physically sensible (200-800).

`WaterSplineMetadata` carries velocity **twice**: `WaterVelocityScalar` (float curve)
and `WaterVelocity` (vector curve, often empty). `GetWaterVelocityVectorAtSplineInputKey`
synthesises its answer from the scalar and the spline tangent, so it returns
healthy-looking numbers even when the vector curve is empty. Populate both.

Both are `FInterpCurve` structs: write the **whole** struct, one point per spline key.
A partial write wipes the rest.

## Diagnosing "the river flows the wrong way"

Work down this ladder. Do not skip ahead to changing parameters.

1. **Is it really a WaterBodyRiver?** `level(get_actor_details)` - check the class and
   that it owns a `WaterSplineComponent` and a `WaterBodyRiverComponent`.
2. **Is the spline sane?** `level(get_spline_info)` - point order monotonic along the
   run, tangents pointing downstream, Z descending downstream.
3. **Do the velocity vectors match the tangents?** Batch
   `editor(invoke_object_functions)` calling `GetWaterVelocityVectorAtSplineInputKey`
   at every key; compare each normalised velocity to its normalised tangent. They
   should agree to 3 decimal places, bends included.
   - **Mismatch: spline/metadata problem.** Stop here and fix the spline.
   - **Match: the spline is fine.** The problem is downstream of it; continue.
4. **Is velocity reaching the surface at all?** Set the material's `Velocity Debug`
   parameter to 1, `editor(capture_scene_png)` straight down over the water, and read
   the mean channel values. The downstream axis should be the dominant channel. A
   near-zero red channel (about 1 of 255) means **velocity is not arriving** - go back
   and check `WaterInfoMaterial`.
5. **Only then** look at individual material layers.

### What "sideways" usually is

The river flowmap is also driven by the **gradient of the water depth field**. In any
normal channel that gradient points *across* the river: depth changes by roughly
0.5 cm per cm across the bank but 0.008 cm per cm downstream - about 70x stronger. So
whenever the velocity term is missing or too small, the depth term wins and the surface
drifts bank-to-bank.

**No riverbed shape can fix this.** Deepening the bed downstream enough to compete would
need about a 50% grade. Fix the velocity path; do not re-cut terrain.

## Making the water meet the banks

The water plane is clipped at `RiverWidth`. If the terrain at that distance sits *below*
the water surface, you get a visible vertical wall of water at the edge.

Set `RiverWidth` to twice the distance at which the bank profile crosses the water
level. If the channel profile is defined relative to the water surface, that distance is
constant along the whole river, so one number fixes it end to end.

## Buoyancy

`BuoyancyComponent` with an empty `Pontoons=` array applies **zero** buoyant force - the
actor is just a falling physics body and sinks to the riverbed. Nothing warns you.

Add pontoons at the hull corners with a real radius:

```
blueprint(set_component_property, componentName="Buoyancy",
          propertyName="BuoyancyData",
          value="(Pontoons=((RelativeLocation=(X=150,Y=55,Z=-30),Radius=110.0),...),
                  BuoyancyCoefficient=2.0,...)")
```

Write the **whole** `FBuoyancyData` struct - a partial write clears the rest.
`BuoyancyCoefficient` defaults to 0.1, too low to float most things; 1.5-3.0 works.
`WaterVelocityStrength` scales how hard the current pushes the actor: at velocity 800
use about 0.015, or the boat launches downstream.

## After any spline, width, velocity or material change

```
editor(invoke_object_function, objectPath=".../WaterZone_0",
       functionName="ForceUpdateWaterInfoTexture")
```

The water info texture is shared state; edits do not take effect until it is rebuilt.

## Verification

What is **not** proof:

- `set_water_body_property` returning `success: true` - read the value back
- `ForceUpdateWaterInfoTexture` returning `changed: true` - it reports the request, not
  whether the texture contents actually differ
- `GetWaterVelocityVectorAtSplineInputKey` returning good numbers - it reads the spline,
  not what the renderer receives

What **is** proof: `Velocity Debug` = 1 plus a capture, comparing channel means against
a capture taken before the change. If two captures are identical to within a fraction of
a colour unit, **nothing you did reached the renderer** - and that finding is worth more
than another parameter guess.

Set `Velocity Debug` back to 0 when finished. It is a visualisation mode, not a look.

## Guardrails

- Never edit engine content under `/Water/`. Make a child MaterialInstance under
  `/Game/<Project>/Materials/` and assign it to `WaterMaterial`.
- Do not accumulate material overrides while debugging. Clear them with
  `material(clear_instance_parameters)` before diagnosing, or you end up tuning your own
  edits. On this project the river started working again *after* the overrides were
  cleared back to engine defaults.
- Do not rotate the water actor, or globally rotate UVs, to compensate for a flow
  direction problem. A river bends; any fixed correction is right on one segment only.
- `UseFixedVelocity` (static switch) bypasses the info texture and uses a constant
  direction baked into the engine material. It is a diagnostic, not a fix - it cannot
  follow bends.

## See also

- `ue-mcp-workflow` - prerequisite: session start, editor lifecycle
- `ue-mcp-pcg-vegetation` - vegetating the banks afterwards
- `CLAUDE.md` - interface choice and cross-cutting gotchas
