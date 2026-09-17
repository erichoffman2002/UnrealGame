# Operating Unreal from Codex

This project (Unreal Engine 5.8, Blueprint-only) is driven programmatically.
Use the supported Python/editor APIs — never simulated mouse or keyboard input.

There are two interfaces. Pick deliberately.

## Choosing an interface

**`ue-mcp` (default, if your client speaks MCP).** A project-scoped MCP server
declared in `.mcp.json`, backed by the `UE_MCP_Bridge` plugin in `Plugins/`. It
drives a **running** editor over a socket, and is the primary interface for all
interactive work: building levels, authoring assets, inspecting state, iterating
on anything you need to look at. Start with `project(action="get_status")`.

The per-domain playbooks live in `.claude/skills/ue-mcp-*` as Claude Code skills.
They are plain Markdown — read them directly for the recipes and known pitfalls
even if your client does not auto-load skills. `ue-mcp-workflow` is the entry point.

**`Tools/Unreal` scripts (batch only).** A launcher that spawns its **own** editor
process and requires the GUI editor to be closed. Use it only for unattended,
deterministic jobs: batch conversions, repairs, migrations, CI-style checks.

The two are mutually exclusive by design — one needs the editor open, the other
needs it closed. Do not mix them in a single task. If you find yourself closing the
editor to run a script for something ue-mcp can already do, use ue-mcp instead.

**Escape hatch.** When no native MCP action covers a case, `editor(execute_python)`
and `editor(run_python_file)` run Python *inside the live editor* — no restart, full
access to live state. The bridge gates these behind a `ruledOut` justification;
respect that gate rather than routing around it.

## Running a script

```bash
Tools/Unreal/run_unreal.sh --script verify_scene
Tools/Unreal/run_unreal.sh --script build_test_scene --editor
```

From PowerShell: `Tools\Unreal\run_unreal.ps1 -Script verify_scene`
(the `.sh` wrapper just forwards to the `.ps1`; flags map
`--editor`→`-Editor`, `--params`→`-Params`, `--allow-editor-running`→`-AllowEditorRunning`)

- **Default** = headless `UnrealEditor-Cmd.exe -run=pythonscript` with
  `-NullRHI`. Fast; use it for anything that does not need to render.
- **`-Editor`** = full `UnrealEditor.exe` with `-ExecutePythonScript`. Required
  for screenshots/rendering. The script must end by calling
  `unreal.SystemLibrary.quit_editor()`.
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

- `scripts/build_test_scene.py` — builds `/Game/AutomationTest/TestScene`
  (floor, 3 shapes with materials, lighting, camera) and renders
  `Tools/Unreal/output/test_scene.png`.
- `scripts/verify_scene.py` — fresh-process verification that it persisted.
- `lib/ue_util.py` — context, logging, JSON result.

The MCP layer (now the primary interface):

- `.mcp.json` — project-scoped `ue-mcp` server declaration.
- `Plugins/UE_MCP_Bridge/` — the C++ bridge plugin it talks to.
- `.claude/skills/ue-mcp-*` — per-domain playbooks: workflow, epic-routing,
  blueprint, animation, niagara, native-cpp, pcg-vegetation.
- Epic's UE 5.8 Toolset Registry is enabled (`ToolsetRegistry` + `AllToolsets`
  in the .uproject), surfacing ~830 `epic_*` actions across the categories.
- `/Game/MCP_Test/LandscapeTest` — disposable landscape/PCG test level with
  `PCG_Vegetation`, built entirely through ue-mcp.

The `Tools/Unreal` script layer is intentionally minimal. Do not extend it with
helpers that duplicate an existing ue-mcp action.

## Hard-won gotchas

- **`foliage(add_type_to_level)` and `foliage(add_instances)` crash the editor.**
  Hard assert `InLevelHint` in `ActorPartitionSubsystem.cpp:184`, from
  `FoliageHandlers_Depth.cpp:893` / `:482`. Correct call order does not help; both
  entry points die. `foliage(create_type)` and the read actions are safe. Scatter
  vegetation with the `pcg` category instead — see the `ue-mcp-pcg-vegetation`
  skill. *Verified 2026-09-16, UE 5.8 / ue-mcp bridge API v1; recheck after an
  upgrade.*
- **Save the level at every stage of a long build.** An editor crash loses all
  unsaved in-memory work; assets saved individually survive, the `.umap` does not.
- **Don't guess property names** — read `Intermediate/PythonStub/unreal.py`
  (generated by `bDeveloperMode`). It is the authoritative 5.8 API reference.

`CLAUDE.md` carries the Claude Code copy of these instructions, including the full
gotcha list.
