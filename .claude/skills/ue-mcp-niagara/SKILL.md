---
name: ue-mcp-niagara
description: Use when authoring Niagara VFX systems via ue-mcp - creating systems and emitters, adding renderers, setting module inputs and static switches, building HLSL modules, and batching operations. Pulls in any time the user asks for a particle system, VFX, Niagara emitter, or motion matching cost visualization.
---

# ue-mcp Niagara authoring

The `niagara` tool covers systems, emitters, modules, renderers, and HLSL authoring.

## Create and inspect

- `niagara(action="create", name, packagePath?)` - stand up a blank `UNiagaraSystem`.
- `niagara(action="create_system_from_spec", name, packagePath?, emitters=[{path}])` - declaratively create a system with emitters in one call.
- `niagara(action="list_emitters", systemPath)` / `niagara(action="get_info", assetPath)` - inspect shape.
- `niagara(action="inspect_data_interfaces", systemPath)` - enumerate user-scope data interfaces.
- `niagara(action="list_system_parameters", systemPath)` - user-exposed parameters (with isDataInterface flag).

## Renderers

- `niagara(action="list_renderers", systemPath, emitterName?)` - current renderer stack.
- `niagara(action="add_renderer", systemPath, rendererType="sprite"|"mesh"|"ribbon", emitterName?)` - or pass a full class name.
- `niagara(action="set_renderer_property", systemPath, rendererIndex, propertyName, value, emitterName?)` - bool / numeric / string properties via reflection.
- `niagara(action="remove_renderer", systemPath, rendererIndex, emitterName?)`.

## Module inputs + static switches (v0.7.14)

- `niagara(action="list_module_inputs", systemPath, emitterName?, stackContext?)` - walks every module in the ParticleSpawn / ParticleUpdate / EmitterSpawn / EmitterUpdate script stacks, reports input + output pins (name, type, default, linked-state).
- `niagara(action="set_module_input", systemPath, moduleName, inputName, value, emitterName?, stackContext?)` - writes a literal default on the module's function-call input pin. **Limitation:** inputs already overridden via the stack editor's override-map node aren't touched by this path. Clear the override in-editor if the write doesn't take effect.
- `niagara(action="list_static_switches", systemPath, moduleName?, emitterName?, stackContext?)` - uses `UNiagaraGraph::FindStaticSwitchInputs` on each module's function script, cross-referenced against pins on the calling node.
- `niagara(action="set_static_switch", systemPath, moduleName, switchName, value, emitterName?, stackContext?)` - format the `value` per the switch type: `"true"`/`"false"` for bool, integer literal for int/byte/enum.

## HLSL module authoring (v0.7.14)

- `niagara(action="create_module_from_hlsl", name, hlsl, packagePath?)` - creates a `UNiagaraScript` module and injects a `UNiagaraNodeCustomHlsl` carrying the supplied HLSL body. Pin signatures are re-parsed from the HLSL body the first time the asset is opened.
- `niagara(action="get_compiled_hlsl", systemPath, emitterName?)` - introspect the GPU compute script for a system's emitter.

## Batching (v0.7.14)

- `niagara(action="batch", ops=[{action, params}])` - run a sequence of niagara sub-actions fail-fast in order. Returns per-step results plus `stoppedAt` (null on full success, index of the first failure otherwise). Nested batches are rejected.

## Typical authoring flow

1. Create the system + emitters (`create_system_from_spec` or step-by-step).
2. Inspect the stack: `list_module_inputs` to see what you're working with.
3. Tune: `set_module_input` / `set_static_switch` for literal values; `set_renderer_property` for visual output.
4. For custom HLSL behavior: `create_module_from_hlsl` to produce a reusable module, then `add_emitter` / reference it from your stack.
5. Optional: wrap a long sequence in `batch` so a mid-sequence failure gets reported as a single result.

## Diagnosing a system that renders wrong

Work in this order. Each step rules something out that the next one would otherwise
confound.

1. **Is realtime on?** Editor viewports default to realtime OFF, and a Niagara system
   does not tick without it. `editor(set_realtime, enabled=true)` first, or you are
   judging a system that never simulated.
2. **Can your capture even show particles?** `editor(capture_scene_png)` renders through
   a scene capture and did **not** draw particles here, while the lighting, water and
   foliage all looked correct - so an empty frame proves nothing. The capture that works
   is PIE: `editor(play_in_editor, pieAction="start")`, then
   `editor(capture_screenshot, target="pie")`. Editor-window captures
   (`target="editor"`, `HighResShot`) silently wrote no file at all when the editor
   window was not redrawing in the background. **Establish a capture path you trust
   before you change anything**, or you will tune blind.
   `filename` is already relative to `Saved/Screenshots` - passing
   `"Saved/Screenshots/x.png"` doubles the prefix and the file lands somewhere else.
3. **Read the renderer's `Material`.** A renderer created programmatically can have
   `Material: None`, and it renders nothing while every module and both counts look
   healthy. Same class of failure as a water body's empty material slots.
4. **Only then** look at modules.

## The "solid column" artifact

A fire or smoke emitter that renders as a **hard-edged vertical pillar** is not a
material, blend-mode or texture bug, and no amount of material work fixes it. It is
geometry:

- `SystemLocation` spawns every particle at the **same point** (no positional spread), and
- `AddVelocity` in its default **Linear** mode gives every particle the **same** velocity vector, and
- a long `Particles.Lifetime` carries them a long way.

The result is N identical sprites stacked in a perfectly straight line - at 60/s with a
5 s lifetime that is 300 overlapping additive sprites over 8 metres, which reads as a
solid glowing bar. Column height is simply `Lifetime x Velocity Speed`; use that to size
the effect.

The fix is spread plus a shorter life:

- Set `AddVelocity`'s **Velocity Mode** static switch to **In Cone**
  (`ENiagara_VelocityMode` -> `NewEnumerator2`; the display names are Linear / From Point /
  In Cone but the values are `NewEnumerator0..2`). Then set `Cone Axis`, `Cone Angle`
  (~30 deg) and `Velocity Speed`.
- Cut `Particles.Lifetime`. For a campfire, ~0.85 s at ~92 cm/s gives a plume ~80 cm tall.
- Drop the HDR colour once sprites overlap. Stacked additive sprites at 4.0 blow out to
  white; ~1.5 in red reads as flame.

## Writing a SetParameters ("SetVariables") module

`Particles.SpriteSize`, `Particles.Lifetime` and friends usually live in an **assignment
node**, which `list_module_inputs` reports with `settable: false` and
`"No input found with name = ..."`. `set_module_input` cannot write these under any
spelling, qualified or bare - this is a real gap, not a naming mistake.

Note also that a `Lifetime` input on `ParticleState` in ParticleUpdate is **not** the
value in play: the assignment module sets `Particles.Lifetime` at spawn and that is what
governs. Writing the ParticleState input appears to succeed and changes nothing.

Use the Epic toolset instead. The module name carries a GUID suffix - read it from
`niagara(epic_get_emitter_topology)` rather than guessing:

```
niagara(epic_get_stack_input_data | epic_set_stack_input_data,
        stackInputRef={ system: "/Game/.../NS_Fire.NS_Fire",   # full object path
                        emitterName: "E_Flame",
                        scriptName: "ParticleSpawnScript",
                        moduleName: "SetVariables_<GUID>",
                        inputNameStack: ["Particles.Lifetime"] },  # ARRAY, not a string
        inputData={ struct: {refPath: "/Script/Niagara.NiagaraFloat"},
                    value: {value: 0.85} })
```

`inputNameStack` is a `TArray<FName>` (`FNiagaraExt_StackItemReference`, in
`NiagaraExternalSystemEditorUtilities.h`) because it walks a dynamic-input chain; a plain
string is rejected with "Input name not specified in stack reference". These refs are
**flat** - `system` sits at the top level, not nested under an `emitter` object. The
epic wrappers also name their argument strictly: `renderer` for SetRendererData but
`rendererRef` for GetRendererData, and a wrong name is rejected with the correct one.

When a ref shape is unknown, **make the read work first** - a successful
`epic_get_*` hands you the exact struct to echo back on the write.

## Pitfalls

- **Emitter references are version-pinned.** When using `create_system_from_spec`, the handler uses the source emitter's current exposed version - save the emitter first if you've been editing it.
- **`set_emitter_property` uses reflection on `FVersionedNiagaraEmitterData`.** Not all properties are writable this way (some require the stack editor's validators). If `success: false`, the response lists available properties so you can pick the right one.
- **GPU emitters** expose `get_compiled_hlsl` results only when `simTarget == GPU`. CPU emitters return a note explaining no HLSL is available.
- **`material(set_usage)` reports success without writing.** It returns `updated: true`
  while a read-back shows the flag unchanged. Set `bUsedWithNiagaraSprites` with
  `editor(set_property)` and `save=true`, then read it back.
- **The epic toolset wrappers return `null` on a successful write.** `SetRendererData`
  reports nothing at all, so a write is not evidence of a change - always follow with the
  matching `epic_get_*`.

## See also

- `ue-mcp-workflow` — session prerequisites: `project(get_status)` first, editor
  lifecycle, the read-before-write mutation recipe. Read it before this skill.
- `ue-mcp-epic-routing` — when both a native action and an `epic_*` action could do
  the job, this decides which.
- `CLAUDE.md` — project-wide interface choice (ue-mcp vs `Tools/Unreal` scripts) and
  the cross-cutting gotchas.
