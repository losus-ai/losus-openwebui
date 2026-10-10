# 0005. Split into a thin `losus-openwebui` fork and a `losus-roster` package repo

## Status

Proposed

## Context

[0001](0001-fork-open-webui-at-v0-11-4.md) put all new code (tables, routes, Svelte components) into one fork named `opencowork-ui`, on a branch named `cowork`.

Research done with a different AI tool produced the Losus fork-stack kit (a README read on 2026-10-10; the kit's files in `LosusRoster` have not been read by this planning session). It describes two repos:

- `losus-openwebui`: the Open WebUI fork. Kept thin. Its commits are accounted for in a manifest, all carry a `losus:` prefix, and package code is blocked from it by commit hooks and CI.
- `losus-roster`: an MIT repo that holds the package code. A boundary check blocks `open_webui` imports and copied Open WebUI copyright text.

The kit also expects the fork's working branch to be `losus/main`, sitting on a plain upstream tag, with a weekly rebase workflow.

## Decision

Adopt the kit's two-repo structure and names.

| Role | Old name | New name |
| --- | --- | --- |
| Open WebUI fork (dependency) | `losus-ai/opencowork-ui` | `losus-ai/losus-openwebui` |
| Fork working branch | `cowork` | `losus/main` |
| Product and package code (MIT) | none | `losus-ai/losus-roster` |
| Planning docs | in the fork | in `losus-roster` (to be confirmed, see open questions) |

The fork carries only the small set of upstream-file changes the manifest allows (for example the sidebar hook). The projects, inbox, agent-limited and theme code moves to `losus-roster`.

## Consequences

- The specs and ADRs 0002 to 0004 say new tables, routes and components live in the fork. Those locations must be revisited. The designs themselves (data model, API, enforcement rules) are not affected by this decision.
- Fork commits must start with `losus:`, which changes the commit style used so far.
- The fork's commit hooks may reject files outside its allowed paths, including `docs/`. This is why the docs are expected to move.
- The weekly rebase workflow replaces the manual rebase steps in the process doc.
- The product name is no longer tied to "Cowork". A name based on Roster would also remove the overlap with Anthropic's product name discussed on 2026-10-09. This is not decided here.

## Open questions

- How does the code in `losus-roster` load into the running app (installed package, plugin, mounted router)? The kit's README does not say. Read the kit's manifest and skill file first.
- Which paths does `.losus/stack.json` allow in the fork?
- Do the docs belong in `losus-roster`, or in a `docs/` path the fork allows?

## Alternatives considered

- Keep one fork with all code in it (the 0001 approach): rejected because the kit's guards exist to stop exactly that, and a thin fork rebases with fewer conflicts.

## Related decisions

- [0001. Fork Open WebUI at v0.11.4 into the losus-ai organization](0001-fork-open-webui-at-v0-11-4.md)
