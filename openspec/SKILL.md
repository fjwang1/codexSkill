---
name: openspec
description: Use the local OpenSpec CLI and OPSX workflow for spec-driven development. Use when Codex is asked to initialize OpenSpec, create or review OpenSpec changes, write proposal/spec/design/tasks artifacts before implementation, validate OpenSpec changes, run `/opsx:*`-style workflows, or follow an "agree on specs before coding" process.
---

# OpenSpec

## Overview

Use OpenSpec to plan software changes before implementation. Prefer creating or updating `openspec/changes/<change-name>/` artifacts first, validating them, and only implementing after the user approves the planned change.

The local CLI is installed globally as `openspec` and also available from `/Users/wangfangjia/code/OpenSpec/bin/openspec.js`.

## Quick Commands

- Show CLI help: `openspec --help`
- Initialize a project: `openspec init <project-path> --tools codex --force`
- List active changes: `openspec list --json`
- Show a change/spec: `openspec show <name> --json`
- Validate one change: `openspec validate <change-name>`
- Validate everything: `openspec validate --all --json`
- Show artifact status: `openspec status --json`
- Get artifact instructions: `openspec instructions <artifact> --json`

Use `scripts/openspec-cli` when a stable path is useful:

```bash
/Users/wangfangjia/.codex/skills/openspec/scripts/openspec-cli --version
```

## Workflow

1. Inspect the project for existing `openspec/` state.
2. If missing, initialize OpenSpec with `openspec init <path> --tools codex --force`.
3. Create or update a change under `openspec/changes/<kebab-case-name>/`.
4. Write artifacts before implementation:
   - `proposal.md` for intent, scope, and approach.
   - `specs/<domain>/spec.md` for ADDED/MODIFIED/REMOVED requirements with scenarios.
   - `design.md` for technical direction and interaction/state decisions.
   - `tasks.md` for implementation checklist.
5. Run `openspec validate <change-name>` and fix validation issues.
6. Stop for user review when the user asks to check specs before coding.
7. Only implement after explicit user approval.

## Artifact Style

Use concise, concrete artifacts. Delta specs should describe externally visible behavior, not implementation details. Scenarios should use Given/When/Then-style bullets.

For product/UI planning, put user-visible behavior and transitions in specs, and put component structure, state model, animation sequencing, and data persistence in design.

## References

- Read `references/quick-guide.md` for local conventions and artifact examples.
- The source CLI repo is `/Users/wangfangjia/code/OpenSpec`.
