---
name: ue-mcp-workflow
description: Use when driving Unreal Engine editor via the ue-mcp MCP server. Covers the required order of operations (status check first), editor lifecycle, project scoping, and what to do when the bridge says "still initializing". Pulls in automatically any time the user asks to use an Unreal project or references ue-mcp tools.
---

# ue-mcp workflow

The `ue-mcp` MCP exposes 26 category tools (action-dispatch style) that drive a live Unreal Engine editor via a C++ bridge plugin. Every tool takes an `action` parameter.

## Start every session with a status check

**Always** call `project(action="get_status")` before anything else. It tells you:

- Whether the bridge is connected
- Which project is loaded
- Whether the editor is responsive

If status reports `not connected` / `editor not running`, call `editor(action="start_editor")` to launch UE. Wait for the status check to succeed before issuing other calls - handlers that need the editor world will return `"Editor is still initializing. Please wait and retry."` if you call them too early.

## Orient yourself before authoring

Before writing, read. Common orientation calls:

- `level(action="get_outliner")` - what's in the current level
- `asset(action="list", directory="/Game/...", recursive=true)` - what assets exist
- `asset(action="search_fts", query="...")` - ranked search across names/classes/paths (after `asset(action="reindex_fts")` has built the index)
- `reflection(action="reflect_class", className="StaticMeshActor")` - inspect any UE class
- `project(action="list_project_modules")` - native C++ modules in the project

## Mutation recipe

For any write action:

1. Call the read/list variant first to confirm the target exists and capture the current shape (e.g. `blueprint(action="read", assetPath=...)` before `add_node`).
2. Issue the write. Most write handlers return `{ success, existed, created, updated, rollback? }` - honor `existed` as "idempotent no-op" and `updated` as "real change made".
3. If a rollback record came back and you hit a later failure in the same logical unit, call the rollback method yourself (the TS flow runner does this automatically when tasks are composed via `ue-mcp.yml`).

## Common pitfalls

- **Action typos silently fail** - each tool validates `action` against an enum; a typo returns `Unknown action '<x>'. Available: <list>`. Read the `Available:` list rather than guessing.
- **Asset paths use `/Game/...`**, not filesystem paths. Package paths (folder) vs object paths (`Folder/Name.Name`) matter - most create handlers take `packagePath` (folder) plus `name`; most read handlers take `assetPath` (full object path).
- **`execute_python` is an escape hatch, not a shortcut** - if a native tool exists for the job, use it. When you use `execute_python`, a hook may prompt you to file a GitHub issue so the native tool gap can be closed.
- **Editor must be fully loaded** for asset registry queries. If a `list_*` action retries with "still initializing", the editor is still starting - wait a few seconds and retry.

## PIE lifecycle: the traps that invalidate a test

Most wasted effort in a visual/runtime session comes from testing the wrong state, not
from the change being wrong.

- **`play_in_editor(start)` returns `success: false` when a session is already running.**
  That stale session predates your edits, so anything you measure in it is the OLD build.
  After any asset edit, always: `stop` -> poll `status` until `isPlaying: false` -> `start`.
- **Stop is deferred.** Both start and stop take effect on a later editor tick. Poll
  `play_in_editor(pieAction="status")` rather than assuming.
- **`level(save)` is refused while PIE runs** ("stop it before saving the level"). Stop
  first, then save, then restart if you still need it.
- **Edit assets with PIE stopped.** A Blueprint or Niagara edit applied mid-session may or
  may not reach the running world.

## Verifying something visually

Pick the capture path deliberately - they do not show the same thing, and two of them can
report success while producing nothing useful.

| Path | Shows | Watch out |
|---|---|---|
| `editor(capture_scene_png)` | editor world, correct lighting/foliage/water | **Does not draw Niagara particles.** An empty frame is not evidence |
| `editor(capture_screenshot, target="pie")` | the real game viewport incl. particles and UMG | needs a PIE session; the reliable default for judging VFX |
| `editor(capture_screenshot, target="editor")` / `HighResShot` | editor viewport | **silently wrote no file** when the editor window was not redrawing in the background - check the file exists |

- **Editor viewports default to realtime OFF.** Nothing simulates - no Niagara, no
  animation - until `editor(set_realtime, enabled=true)`. A "broken" effect is often just
  a viewport that never ticked.
- **`filename` on `capture_screenshot` is already relative to `Saved/Screenshots`.**
  Passing `"Saved/Screenshots/x.png"` doubles the prefix and the file lands elsewhere.
- **Comparing an editor capture against a PIE capture from the same pose** is how you
  prove an artifact is runtime-only, which narrows it to something spawned rather than
  something authored.

*Verified 2026-09-17, UE 5.8.*

## A write reporting success is not evidence

This bridge has several actions that report success while writing nothing. Read back
after every write that matters:

- `material(set_usage)` returns `updated: true`, flag unchanged.
- The `epic_*` toolset wrappers return `returnValue: null` on a successful write and say
  nothing about what changed.
- The Blueprint graph DSL resolves an **unrecognised enum string to index 0** rather than
  erroring - `"Visibility"` becomes `ECC_WorldStatic`. Compiles clean, does nothing.
- `level(set_water_body_property)` and friends - see the water skill.

The general rule: the read-back is the assertion, and for runtime behavior the read-back
belongs on the **live PIE object** (`editor(get_runtime_values)`,
`editor(invoke_object_function)`), not on the asset.

## When something truly can't be done

If no native action covers your case:

1. Confirm no action already covers it: `project(action="search_tools", query=...)` searches the whole surface by intent, and `project(action="describe_action", action="...")` gives one action's parameters.
2. Confirm no UFUNCTION exists to call directly: `reflection(action="list_classes", parentFilter=...)` finds the class and `reflection(action="reflect_class", className=...)` lists what it exposes. A BlueprintCallable function is reachable with `editor(action="invoke_object_function")`.
2. Use `execute_python` as a last resort.
3. Consider using `feedback(action="submit")` to open a GitHub issue describing the gap. It checks the plugin registry and files against whichever tracker owns the surface - `db-lyon/ue-mcp` for core, or the plugin's own repo when the gap is in a plugin-provided category. Run `feedback(action="route")` first if you want to see where it would land without posting.

## Domain skills

This skill is the entry point. Once oriented, load the one that matches the task:

| Skill | Use for |
|---|---|
| `ue-mcp-epic-routing` | Choosing between a native action and an `epic_*` action |
| `ue-mcp-blueprint` | Blueprint graphs, components, CDO, interfaces, dispatchers |
| `ue-mcp-pcg-vegetation` | Scattering vegetation/rocks/trees on a Landscape via PCG |
| `ue-mcp-niagara` | Niagara systems, emitters, renderers, HLSL modules |
| `ue-mcp-water` | Rivers/lakes/oceans, water zones, flow direction, buoyancy |
| `ue-mcp-animation` | IK Rig/Retargeter, Control Rig, baking, bone analysis |
| `ue-mcp-native-cpp` | Native C++ UCLASSes (not used in this Blueprint-only project) |

`CLAUDE.md` covers the project-wide choice between ue-mcp and the `Tools/Unreal`
batch scripts, plus cross-cutting gotchas.

## Known editor-killing calls

`foliage(add_type_to_level)` and `foliage(add_instances)` hard-assert and take the
editor down (`InLevelHint`, `ActorPartitionSubsystem.cpp:184`). Correct call order does
not help. Scatter with the `pcg` category instead — see `ue-mcp-pcg-vegetation`.
*Verified 2026-09-16, UE 5.8 / bridge API v1.*

Save the level (`level(save)`) at each stage of a long build. A crash loses all unsaved
in-memory work; separately-saved assets survive but the `.umap` does not.
