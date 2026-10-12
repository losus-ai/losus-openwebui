# Losus fork notice

This repository is the Losus AI LLC fork of [Open WebUI](https://github.com/open-webui/open-webui). It is a thin patch stack: an upstream release tag plus a few `losus:` commits (`python3 scripts/losus/stack.py list`).

- **Base:** Open WebUI v0.11.4. `main` mirrors upstream and receives no commits; `losus/main` is the product line.
- **What the fork adds:** a five-line hook in `src/lib/components/layout/Sidebar.svelte` that renders `LosusAgents` from the npm package `@losus-ai/roster-ui`, and the tooling that keeps the stack small (`.losus/`, `scripts/losus/`, `.github/workflows/losus-*`). Product code lives in the separate `losus-roster` repository and reaches this fork only through that npm pin.
- **License:** Open WebUI's license applies unchanged to everything here. See `LICENSE`, `LICENSE_HISTORY` and `LICENSE_NOTICE`. This fork does not alter, remove or replace Open WebUI's name, logo or other branding (`static/BRANDING.md`).
- **Copyright:** Open WebUI code is Copyright (c) 2023- Open WebUI Inc. Losus additions in the paths above are Copyright (c) 2026 Losus AI LLC.
- **Upstream changes:** adopted through the rebase workflow (`.github/workflows/losus-upstream-rebase.yml`), never by merging into `losus/main`.
