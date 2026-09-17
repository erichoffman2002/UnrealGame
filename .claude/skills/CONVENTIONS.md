# Conventions for `ue-mcp-*` skills

House style for this project's Unreal skills, extracted from the seven that exist.
Read this before authoring a new one. It is a checklist, not a skill — it does not
load itself.

## Frontmatter

```yaml
---
name: ue-mcp-<domain>
description: Use when <task>. Covers <specifics>. Pulls in any time the user asks to <trigger phrases>.
---
```

The description is the trigger. Name the concrete nouns and verbs a user would
actually type ("particle system", "scatter", "retarget"), not abstractions. If the
skill warns about a destructive call, say so in the description — that is what gets
it loaded before the damage.

## Required sections

**Danger first.** If any action in the domain crashes the editor, destroys data, or
cannot be undone, it goes above everything else. Nobody reads to line 90 first.

**The action surface.** What the category's actions are and when each applies. Prose
or a table, not an exhaustive dump — `catalog(describe)` already does exhaustive.

**Pitfalls.** Numbered, each with its *symptom*. The symptom is what makes it
findable later. "Silently produces zero instances while reporting `success: true`" is
useful; "be careful with paths" is not.

**Verification.** What proves the operation worked — and explicitly what *looks* like
proof but is not. Every skill here that has been used in anger grew this section
after a false success. Include a diagnostic ladder for the domain's common silent
failure.

**See also.** Link `ue-mcp-workflow` as prerequisite, `ue-mcp-epic-routing` where both
surfaces exist, and `CLAUDE.md`.

## Optional but valuable

**Decision rules** — for skills with tunable output. Map vague user wording to
concrete numbers, define what to sacrifice first under a budget, and say to state the
chosen numbers so the user can correct them. A recipe executes; a playbook decides.

**Parameters table** — defaults plus notes, so the skill is adjustable rather than
fixed.

**Typical flow** — the ordered call sequence, with save checkpoints marked.

## Rot control

Skills encode two kinds of claim, and they age differently:

- **Durable** — engine behaviour, API shapes, physics of the problem
- **Perishable** — bugs and workarounds in the bridge, plugin or engine version

Version-stamp every perishable claim and say what to do when it expires:

> *Verified 2026-09-16, UE 5.8 / ue-mcp bridge API v1. Recheck after any engine or
> bridge upgrade; if fixed upstream, delete this section.*

Where a section mixes both, mark which items are which (see
`ue-mcp-pcg-vegetation`, "The eight details that break this").

A stale script fails loudly. A stale skill misleads silently — it will steer a future
session away from a path that now works. Stamping is the whole mitigation.

## Verification discipline

Two patterns worth copying verbatim:

- `ue-mcp-blueprint` — a write is not verified until the value is read back off the
  resolved CDO *and* confirmed persisted to disk (`persisted: false` means it dies on
  restart).
- `ue-mcp-pcg-vegetation` — generation reporting `success: true` with zero output is
  the default failure mode; count the actual artifacts, and name the tool that
  *cannot* see them.

Never let a skill claim success from a handler's return value alone.

## Scope

One domain per skill. If a skill starts covering two, split it. Do not add features
the user did not ask for — these are operational playbooks, not documentation.
