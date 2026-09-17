---
name: ue-mcp-pcg-vegetation
description: Use when scattering vegetation, foliage, grass, ferns, rocks or trees across an Unreal Landscape through ue-mcp. A parameterized PCG recipe with slope filtering, per-species weighting, tree spacing and save checkpoints. Pulls in any time the user asks to populate, vegetate or scatter props on terrain, or mentions PCG scatter. Also read it before touching the `foliage` category, which crashes the editor.
---

# PCG vegetation scatter (ue-mcp)

A parameterized recipe for scattering vegetation over a Landscape with the native `pcg`
category. Every implementation detail below was paid for with a debugging session or an
editor crash — follow them literally.

## Do not use the `foliage` category

**Bug claim — verified 2026-09-16, UE 5.8, ue-mcp bridge API v1. Recheck after any engine
or bridge upgrade; if fixed upstream, delete this section.**

`foliage(add_type_to_level)` and `foliage(add_instances)` **hard-assert and kill the
editor** (`InLevelHint`, `ActorPartitionSubsystem.cpp:184`), from
`FoliageHandlers_Depth.cpp:893` and `:482` respectively. Correct call order does not help.
`foliage(create_type)` and the read actions are safe. For scattering, use this recipe.

## Parameters

Resolve these before authoring. Defaults are tuned for a ~126 m x 126 m landscape on a
6 GB GPU.

| Parameter | Default | Notes |
|---|---|---|
| `graphPath` | `/Game/<Area>/PCG/PCG_Vegetation` | Keep beside the level, not `/Game/PCG` |
| `volumeLabel` | `PCG_VegetationVolume` | Idempotency key for `add_volume` |
| `layers` | grass, ferns, rocks, trees | One branch each; drop or add freely |
| `density` (per layer) | grass 0.30, ferns 0.08, rocks 0.018, trees 0.008 | `pointsPerSquaredMeter` |
| `species` + `weight` | see below | Weighted entries per spawner |
| `slopeMax` (per layer) | grass 35°, ferns 34°, rocks 40°, trees 27° | Converted to `$Rotation.W` |
| `scaleMin`/`scaleMax` | grass 0.75-1.45, ferns 0.7-1.3, rocks 0.45-1.5, trees 0.65-1.15 | Uniform |
| `yawRandom` | full 0-360 | `rotationMax.yaw = 360` |
| `tiltRandom` | rocks only, ±8° pitch/roll | Leave 0 for plants so they stand upright |
| `treeSpacing` | 650 cm point extents + Self Pruning | Yields ~25 m spacing |
| `clustering` | `looseness` 1.0 | 0 = rigid grid, 1 = free within cell |
| `seed` | component `Seed` (default 42) | Pass via `pcg(execute, seed=...)` |
| `maxInstances` | ~6,000 | Budget guardrail, see below |

### Density to instance count

`instances ≈ pointsPerSquaredMeter × areaInSquareMetres × slopeKeepRatio`

A 126 m square is 15,876 m². Slope filtering typically keeps ~75-80%. At 0.30 ppsm that
is ~4,766 sampled, ~3,755 kept. **Estimate before generating** and keep the total under
`maxInstances`; a 6 GB GPU handles ~5,000 ISM instances of KiteDemo-grade foliage
comfortably.

## Decision rules

This is a playbook, not a fixed recipe. Apply judgment in this order, and state the
numbers you chose so the user can correct them.

### Density presets

Map the user's wording to a starting density, then say the number out loud. These ranges
are **taste, not fact** — when one looks wrong, change the number rather than argue about
the adjective.

| Wording | Trees (ppsm) | Ground cover (ppsm) |
|---|---|---|
| bare / barren | 0 | 0.02 - 0.05 |
| sparse, scattered, open | 0.002 - 0.006 | 0.05 - 0.12 |
| moderate, normal, wooded | 0.006 - 0.012 | 0.12 - 0.35 |
| dense, thick, forest | 0.012 - 0.025 | 0.35 - 0.6 |
| overgrown, jungle | 0.025+ | 0.6 - 1.0 |

Ambiguous input ("some trees") defaults to the moderate row.

### Terrain-adaptive density

Sample the terrain before choosing (`landscape(analyze_terrain)` reports slope
distribution). Steep ground both rejects more points and looks wrong when crowded.

- Mostly flat (median slope < 10°): use the preset as-is
- Rolling (10-20°): preset as-is; expect ~20% slope rejection
- Steep (median > 20°): drop ground cover ~30% and widen tree spacing; most of the map
  will fail the slope filter anyway, so high density just wastes budget

### Budget overrun — degrade in this fixed order

When the estimate exceeds `maxInstances`, cut in this order and stop as soon as you are
under. Keep the order stable so results are predictable across sessions.

1. Grass density
2. Flowers / small clutter
3. Ferns / mid shrubs
4. Rocks
5. **Never thin trees to fit budget** — trees carry the silhouette, and losing them
   changes how the scene reads. Increase `treeSpacing` instead, which reduces count while
   keeping distribution even.

Prefer raising spacing over lowering tree count wherever both would work.

### Tree spacing vs count

`treeSpacing` (point extents + Self Pruning) and tree `density` both change the final
count. They are not interchangeable:

- Too many trees, want them evenly spread → raise `treeSpacing`
- Too many trees, want clumps and clearings → lower `density`, keep spacing, raise
  `looseness`
- Want a grove rather than an even wood → lower `density`, lower `treeSpacing`

### Zero instances returned

Work the ladder in **Verification** below. Do not re-run generate hoping for a different
result; it is deterministic for a given seed.

## The eight details that break this

**Items 1-3 and 5 are durable engine behaviour. Items 4, 6 and 7 are bridge bugs as of
2026-09-16 / ue-mcp API v1 — recheck and delete them if a later bridge fixes them.**

1. **Mesh paths must be full object paths.** `set_static_mesh_spawner_meshes` stores the
   string verbatim into a `TSoftObjectPtr`. A package path like
   `/Game/Foo/SM_Grass` silently resolves to nothing: generation reports success,
   `bGenerated: True`, and `GeneratedResources` is empty with zero components. Always
   `/Game/Foo/SM_Grass.SM_Grass`.
2. **Never write a struct property partially.** `set_node_settings` with a subset of a
   struct's fields resets the unspecified ones to defaults. Writing three fields of
   `actorSelector` wiped `ActorSelection=ByClass` / `ActorSelectionClass=LandscapeProxy`
   and the landscape node matched no actors. Read the current value first, then write the
   **whole** struct as export text via `propertyName`/`propertyValue`.
3. **Connect every spawner to `DefaultOutputNode`.** PCG culls branches that do not reach
   the output node. They execute and produce points, but spawn nothing.
4. **Selector properties need export text**, not JSON:
   `PCGBegin($Rotation.W)PCGEnd`. Passing them inside a `settings` object returns
   `success: false` while still applying the other keys — check `setProperties`.
5. **Set `bSynchronousLoad: True`** on every Static Mesh Spawner. Meshes are soft refs.
6. **`pcg(create_graph)` ignores `path`** and writes to `/Game/PCG`. Move it afterwards
   with `asset(move)`.
7. **`reflection(list_classes)` ignores `filter`.** Do not trust a "filtered" class list.
8. **Node types are settings class names**, not display titles: `PCGSurfaceSamplerSettings`,
   not `"Surface Sampler"`. `pcg(add_node)` assigns the name and returns it — capture
   `nodeName` from the result, never guess it.

## Slope filtering

There is no `$Normal` attribute, and `Attribute Transform Op` only offers
Compose/Invert/Lerp, so no up-vector can be derived. Use the quaternion instead.

A landscape-sampled point's rotation is a pure minimal-arc tilt from +Z to the surface
normal (z-component ≈ 0), so **`$Rotation.W` = cos(θ/2)** where θ is the slope angle.

`threshold = cos(slopeMaxDegrees / 2 × π / 180)`

| Slope limit | `$Rotation.W` |
|---|---|
| 25° | 0.976 |
| 27° | 0.972 |
| 30° | 0.966 |
| 35° | 0.955 |
| 40° | 0.940 |

Node: `PCGAttributeFilteringSettings`, `operator: "Greater"`,
`bUseConstantThreshold: true`, `attributeTypes: {type: "Double", doubleValue: <threshold>}`,
and `TargetAttribute` written separately as `PCGBegin($Rotation.W)PCGEnd`.

**The filter must sit before Transform Points**, which adds random yaw and would destroy
the measurement.

## Graph shape

```
Get Landscape Data ──┬── Surface Sampler ── Filter (slope) ─────────────────── Transform Points ── Static Mesh Spawner ──┐
                     ├── Surface Sampler ── Filter (slope) ─────────────────── Transform Points ── Static Mesh Spawner ──┤
                     ├── Surface Sampler ── Filter (slope) ─────────────────── Transform Points ── Static Mesh Spawner ──┼── DefaultOutputNode
                     └── Surface Sampler ── Filter (slope) ── Self Pruning ─── Transform Points ── Static Mesh Spawner ──┘
                                                              (trees only)
```

One `Get Landscape Data` feeds every branch. Separate samplers give per-layer density;
that is simpler and cheaper than one dense sampler plus per-layer thinning.

## Build order

Read `ue-mcp-workflow` first; `project(get_status)` before anything else.

1. `level(load, levelPath=...)`, then `level(save)` as the pre-PCG checkpoint.
2. `pcg(create_graph, name=...)` → `asset(move)` to `graphPath`.
3. `pcg(add_node, nodeType="PCGGetLandscapeSettings")`. Write the **full** `actorSelector`
   struct (detail 2) with `ActorFilter=AllWorldActors`, `ActorSelection=ByClass`,
   `ActorSelectionClass=LandscapeProxy`, `bMustOverlapSelf=False`, and set
   `samplingProperties.bGetHeightOnly=False` so normals exist.
4. Per layer, `add_node` the 4-5 nodes, capture each returned `nodeName`, set settings,
   set mesh entries with full object paths, set `bSynchronousLoad`, then connect:
   landscape→sampler `Surface`, sampler→filter `In`, filter `InsideFilter`→next,
   →spawner `In`, spawner→`DefaultOutputNode` `Out`. Every `connect_nodes` returns
   `edgeVerified` — check it.
5. `pcg(add_volume, graphPath, label, location, extent)` sized to cover the landscape in
   XY and its full height range in Z.
6. `level(save)` — checkpoint before the first generate.
7. `pcg(execute)` or `pcg(force_regenerate)`.
8. Verify, then `level(save)`.

Save before and after generation. Generation is the step that historically loses work.

## Verification

Never trust `success: true` from generate. It reports `bGenerated: True` with zero output.

- **Instance counts:** `level(query_components, componentClass="InstancedStaticMeshComponent",
  fields=["mesh"])`. Returns per-component `mesh.instanceCount`. This is the ground truth.
- **`level(summarize_static_mesh_usage)` does not see PCG instances** — it counts
  StaticMeshActors only. Zero there means nothing about PCG.
- **Point counts per node:** `pcg(epic_get_node_data_view, pCGVolume=<full actor path>,
  node=<full node object path>, attributeName="$Position")` returns `totalElements`.
  Both arguments need full object paths. Compare sampler vs filter totals to prove the
  slope filter is discriminating rather than passing or rejecting everything.
- **If a node "produced no data on pin 'Out'"**, walk upstream one node at a time. The
  failure is almost always the landscape selector (detail 2) or a culled branch (detail 3).
- **Persistence:** load a different level, load this one back, re-run the instance count.
  Identical numbers prove `GenerateOnLoad` works. Do this before reporting success.

## Preview images

`editor(capture_scene_png)` works and shows geometry and instance distribution accurately,
but uses a SceneCapture actor, so **colour and lighting are not representative** — expect
flat, oversaturated output. Say so when presenting one.

`editor(capture_screenshot, target="editor")` queues asynchronously and may never write a
file; it also double-prefixes `Saved/Screenshots`. Do not build a rendering workaround —
report that a representative shot needs the editor viewport and move on.

## Guardrails

- Estimate instance count from density before generating; stay under `maxInstances`.
- Reference source assets, never modify them. Create new assets under the test area.
- Heavy meshes can stall the editor for minutes on first load (one KiteDemo tree took
  525 s building 4096x4096 atlases). Prefer meshes already resident, and treat a long
  `get_mesh_bounds` as a sign to pick a lighter asset.
- Preserve hand-placed actors, the landscape and its sculpting, lighting and Player Start.
  Re-check with `level(count_actors_by_class)` after generating.
- `pcg(force_regenerate)` destroys and rebuilds generated content — fine for PCG output,
  destructive to any hand edits made to it.

## See also

- `ue-mcp-workflow` — session prerequisites: `project(get_status)` first, editor
  lifecycle, the read-before-write mutation recipe. Read it before this skill.
- `ue-mcp-epic-routing` — when both a native action and an `epic_*` action could do
  the job, this decides which.
- `CLAUDE.md` — project-wide interface choice (ue-mcp vs `Tools/Unreal` scripts) and
  the cross-cutting gotchas.
