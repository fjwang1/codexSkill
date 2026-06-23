# OpenSpec Quick Guide

## Project Layout

After initialization:

```text
openspec/
├── specs/
├── changes/
│   └── <change-name>/
│       ├── proposal.md
│       ├── design.md
│       ├── tasks.md
│       └── specs/
│           └── <domain>/
│               └── spec.md
└── config.yaml
```

## Delta Spec Format

```markdown
# Delta for UI

## ADDED Requirements

### Requirement: Home Task List
The system SHALL ...

#### Scenario: Default tasks fill daily nectar
- GIVEN ...
- WHEN ...
- THEN ...
```

Use `ADDED`, `MODIFIED`, or `REMOVED` requirements. Prefer user-observable requirements and Given/When/Then scenarios.

## Planning Before Coding

When a user asks to create an OpenSpec change and review it before implementation:

1. Create a kebab-case change folder under `openspec/changes/`.
2. Write `proposal.md`, one or more delta specs, `design.md`, and `tasks.md`.
3. Run `openspec validate <change-name>`.
4. Report artifact paths and validation result.
5. Do not implement code until the user approves.

## Useful CLI

```bash
openspec init <project> --tools codex --force
openspec list --json
openspec show <change-name> --json
openspec status --json
openspec validate <change-name>
openspec validate --all --json
```
