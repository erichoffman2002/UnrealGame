# Operating Unreal from Claude Code

This project (Unreal Engine 5.8, Blueprint-only) is driven programmatically.
Use the supported Python/editor APIs — never simulated mouse or keyboard input.

There are two interfaces. Pick deliberately.

## Choosing an interface

**`ue-mcp` (default).** A project-scoped MCP server declared in `.mcp.json`, backed
by the `UE_MCP_Bridge` plugin. Drives a **running** editor over a socket. This is the
primary interface for all interactive work: building levels, authoring assets,
inspecting state, iterating on anything you need to look at.

Start every session with `project(action="get_status")`. See the `ue-mcp-workflow`
skill in `.claude/skills/` and the other `ue-mcp-*` skills for per-domain recipes.

**`Tools/Unreal` scripts (batch only).** A launcher that spawns its **own** editor
process and requires the GUI editor to be closed. Use it only for unattended,
deterministic jobs: batch conversions, repairs, migrations, CI-style checks.

The two are mutually exclusive by design — one needs the editor open, the other
needs it closed. Do not mix them in a single task. If you find yourself closing the
editor to run a script for something ue-mcp can already do, use ue-mcp instead.

**Escape hatch.** When no native MCP action covers a case, `editor(execute_python)`
and `editor(run_python_file)` run Python *inside the live editor* — no restart, full
access to live state. The bridge gates these behind a `ruledOut` justification;
respect that gate rather than routing around it, and consider `feedback(action="submit")`
so the gap becomes a native action.

## Running a script

```powershell
Tools\Unreal\run_unreal.ps1 -Script verify_scene
Tools\Unreal\run_unreal.ps1 -Script build_test_scene -Editor
```

From bash: `Tools/Unreal/run_unreal.sh --script verify_scene`

- **Default** = headless `UnrealEditor-Cmd.exe -run=pythonscript` with
  `-NullRHI`. Fast; use it for anything that does not need to render.
- **`-Editor`** = full `UnrealEditor.exe` with `-ExecCmds="py <file>"`. Required
  for screenshots/rendering. The editor stays alive after the script returns, so
  **the script must call `unreal.SystemLibrary.quit_editor()` itself** — on the
  error path too, or the run hangs until `-TimeoutSeconds`.
- `-Params '{"key":"value"}'` passes JSON to the script.
- Exit codes: `0` ok, `1` script failed, `2` setup error, `3` the editor is
  already running (close it, or pass `-AllowEditorRunning`).

**Close the Unreal Editor before running.** The launcher refuses otherwise,
because a headless run writing assets while the GUI editor holds the same
project can clobber saves.

## Paths

Never hard-code an engine or project path. `run_unreal.ps1` resolves both and
is the only place that knows about them: explicit flag → env var
(`UE_ENGINE_ROOT` / `UE_PROJECT_FILE`) → `Tools/Unreal/unreal_config.json` →
auto-discovery (nearest `.uproject`; engine from its `EngineAssociation` via
the registry). Scripts read `UE_TOOLS_DIR`, `UE_PROJECT_DIR`, etc. from the
environment.

## Reading results

Each run writes `Tools/Unreal/logs/<run-id>.{result.json,stdout.log,unreal.log}`.
The launcher prints the result JSON on stdout:

```json
{"status": "ok|error", "script": "...", "data": {...}, "errors": [], "traceback": null}
```

Check `status` first. On failure the launcher already prints the relevant
`Error:` / `LogPython` / `Traceback` lines — read those before opening the full
Unreal log.

## Writing a script

Put it in `Tools/Unreal/scripts/` and follow this shape:

```python
import os, sys
sys.path.insert(0, os.path.join(os.environ.get("UE_TOOLS_DIR", ""), "lib"))
import unreal
import ue_util
from ue_util import log

def main(params):
    log("doing the thing")
    return {"some": "result"}     # becomes result["data"]

ue_util.run(main, "my_script")
```

Anything raised becomes `status: "error"` with a traceback; `ue_util.error()`
fails the run without raising. Verify what you create (asset exists **and** has
a file on disk) before reporting success.

## Current state

- `scripts/build_ruin_scene.py` — builds `/Game/FantasyRuins/L_SunkenShrine`
  and renders `Tools/Unreal/output/ruin_*.png`. Idempotent: rerunning clears
  and rebuilds the level in place.
- `scripts/build_test_scene.py` — minimal smoke test (`/Game/AutomationTest`).
- `scripts/verify_scene.py` — fresh-process persistence check.
- `scripts/inventory.py` — read-only Asset Registry inventory.
- `lib/ue_util.py` — context, logging, JSON result.

The MCP layer (now the primary interface):

- `.mcp.json` — project-scoped `ue-mcp` server declaration.
- `Plugins/UE_MCP_Bridge/` — the C++ bridge plugin it talks to.
- `.claude/skills/ue-mcp-*` — per-domain playbooks: workflow, epic-routing,
  blueprint, animation, niagara, native-cpp, pcg-vegetation, water.
- Epic's UE 5.8 Toolset Registry is enabled (`ToolsetRegistry` + `AllToolsets`
  in the .uproject), surfacing ~830 `epic_*` actions across the categories.
- `/Game/MCP_Test/LandscapeTest` — disposable landscape/PCG test level with
  `PCG_Vegetation`, built entirely through ue-mcp.

The `Tools/Unreal` script layer is intentionally minimal. Do not extend it with
helpers that duplicate an existing ue-mcp action.

## Hard-won gotchas

These cost real debugging time; check them before inventing a new theory.

- **`foliage(add_type_to_level)` and `foliage(add_instances)` crash the editor.**
  Hard assert `InLevelHint` in `ActorPartitionSubsystem.cpp:184`, from
  `FoliageHandlers_Depth.cpp:893` / `:482`. Correct call order does not help; both
  entry points die. `foliage(create_type)` and the read actions are safe. Scatter
  vegetation with the `pcg` category instead — see the `ue-mcp-pcg-vegetation`
  skill. *Verified 2026-09-16, UE 5.8 / ue-mcp bridge API v1; recheck after an
  upgrade.*
- **A water body created through ue-mcp gets no materials.** `WaterMaterial`,
  `WaterInfoMaterial` and `WaterLODMaterial` are all `None` - the editor UI assigns
  them when you place one by hand, the programmatic path does not. `WaterInfoMaterial`
  is what writes velocity into the water info texture, so without it a river renders
  but can never flow correctly no matter what the spline says. Water work has its own
  playbook: see the `ue-mcp-water` skill, which also covers the landscape-edit ordering
  that crashes the editor. *Verified 2026-09-17, UE 5.8.*
- **Save the level at every stage of a long build.** An editor crash loses all
  unsaved in-memory work; assets saved individually survive, the `.umap` does not.
  `level(save)` after each major step costs nothing.
- **Arm `editor(set_dialog_policy)` before any unattended run.** A modal blocks
  *every* bridge action until answered, `respond_to_dialog` is refused for unarmed
  dialogs (they belong to the user), and simulated input is forbidden — so an
  unexpected modal ends an unattended session outright. A policy armed *in advance*
  is the only thing the bridge will answer by itself. Arm narrow patterns with a
  literal `buttonLabel`; a bare `response` keyword often matches no button
  (`response:'ok'` does not press `CLEAR`). Known blockers worth arming:
  `"Message Log"` → `CLEAR`, and `"Insert New Landscape Edit Layer"` → `Complete`,
  which the Water plugin raises the first time a Water Body is placed on a landscape.
  Never arm a pattern that could match a save prompt: the policy presses the button
  without anyone reading the warning, so unsaved work can be discarded silently.
  **An armed policy does not help in an interactive session.** Arming
  `"Message Log"` -> `CLEAR` was verified to have no effect here: the bridge still
  reported `dialogMode: "interactive"` and routed the dialog to the person on every
  call, refusing each action until they answered. The policy is for *unattended* runs
  only. In an interactive session a recurring modal will interrupt every PIE cycle, and
  the practical fix is to close or undock the offending window in the editor.
  *Verified 2026-09-17, UE 5.8.*
- **Material usage flags revert unless the material is saved.** The engine sets
  flags like `InstancedStaticMeshes` and `bUsedWithNanite` in memory at load, so the
  material looks correct in-session while the `.uasset` on disk still lacks them —
  and the Map Check warning returns every restart. Enabling Nanite on a mesh also
  dirties every material instance it uses (26 meshes dirtied 25 materials here).
  After any usage-flag or Nanite change, run `editor(list_dirty_packages)` and
  `asset(save_all_dirty)`, then confirm the `.uasset` mtime actually moved.

- **A placed actor ignores Blueprint changes until it is re-placed.** Editing a
  property on the Blueprint (mass, a component default) leaves every instance already
  in the level on its old value - `GetMass()` still returned the previous 747 kg after
  the Blueprint was set to 500. There is no refresh action; delete the instance and
  place it again. Until you do, every runtime measurement you take is measuring the
  stale actor, which quietly invalidates whatever experiment you were running. It also
  covers a component you **add** to the Blueprint: the new component does appear on the
  placed instance, but every default you configured on it does not. A NiagaraComponent
  added and pointed at a system read back `Asset: null`, `bAutoActivate: true` and scale
  `1,1,1` on the existing actor while the Blueprint template held the correct values - so
  the logic ran, set its flags, and activated nothing. Re-place the actor.
  **Scope this carefully:** it applies to *property and component defaults*. A change to
  a Blueprint's **graph logic** does reinstance on compile, so re-placing an actor will
  not fix a function that behaves wrongly — if the logic is still wrong after a compile,
  the bug is in the graph, not in the instance. Re-placing to "fix" logic wastes a cycle
  and, worse, makes you stop looking. The one class-level case that does need a manual
  step is `blueprint(set_class_default)`: it writes the CDO, reads back correctly from the
  asset, and still does not reach newly spawned instances until the Blueprint is compiled.
  *Verified 2026-09-17, UE 5.8.*
- **`material(set_usage)` reports success without writing.** It returns
  `updated: true` while a read-back shows the flag unchanged. Set the underlying
  property instead - `editor(set_property)` on `bUsedWithNiagaraSprites` (or the
  matching `bUsedWith*` flag) with `save=true` - then read it back. This compounds
  with the usage-flag gotcha above: the reported success and the in-memory value can
  agree while the `.uasset` has neither. *Verified 2026-09-17, UE 5.8.*
- **A reported success is not evidence that anything was written.** Beyond
  `material(set_usage)`: the `epic_*` toolset wrappers return `returnValue: null` on a
  successful write and say nothing about what changed, and the Blueprint graph DSL
  resolves an **unrecognised enum string to index 0 instead of erroring** — passing a
  collision channel as `"Visibility"` writes `ECC_WorldStatic`, compiles clean, and the
  feature simply never works. Read back after every write that matters, and for runtime
  behaviour read back off the **live PIE object** (`editor(get_runtime_values)`,
  `editor(invoke_object_function)`) rather than the asset. *Verified 2026-09-17, UE 5.8.*

- **Components can't be created from Python directly.** `add_component_by_class`
  isn't exposed and a `new_object` component won't persist. Use
  `SubobjectDataSubsystem.add_new_subobject` with `blueprint_context=None` to
  add a registered component to a level actor instance.
- **Materials need the InstancedStaticMeshes usage flag.** A material without it
  renders as the default checkerboard on an ISM/HISM. The KiteDemo `GroundTiles`
  instances have this problem, which is why the scene builds its own
  `M_RuinGround`.
- **Pick the capture path deliberately; two of them can report success and show you
  nothing.** SceneCapture2D renders without resolved Lumen GI and without waiting for
  texture streaming, and `editor(capture_scene_png)` — which uses it — **does not draw
  Niagara particles at all**, so an empty frame is not evidence that an effect is broken.
  `capture_screenshot` with `target="editor"` and `HighResShot` both *silently wrote no
  file* when the editor window was not redrawing in the background. The dependable path
  for anything you intend to judge visually is a PIE session plus
  `editor(capture_screenshot, target="pie")`. Also note editor viewports default to
  **realtime OFF**, so nothing simulates until `editor(set_realtime, enabled=true)` — a
  "broken" effect is often a viewport that never ticked. Full table and the PIE lifecycle
  traps are in the `ue-mcp-workflow` skill. *Verified 2026-09-17, UE 5.8.*
- **Force textures resident before capturing**, via
  `MaterialInterface.set_force_mip_levels_to_be_resident`, or you capture the
  lowest mip — a flat average colour.
- **Deleting the current level fails silently.** The editor reopens the last
  level on startup; call `EditorLoadingAndSavingUtils.new_blank_map(False)`
  first, and fall back to clearing the level's actors if the delete is refused.
- **Check mesh bounds before placing.** Pivots vary wildly (`JunglePillarBlock`
  is centre-pivoted, walls are base-pivoted). Use `mesh.get_bounds()`, and
  remember a scaled actor's ground offset scales too.
- **Don't guess property names** — read `Intermediate/PythonStub/unreal.py`
  (generated by `bDeveloperMode`). It is the authoritative 5.8 API reference.

See `AGENTS.md` for the Codex-facing copy of these instructions.
