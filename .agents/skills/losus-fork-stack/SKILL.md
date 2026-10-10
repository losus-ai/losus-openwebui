---
name: losus-fork-stack
description: "Maintain the Losus Roster patch stack on the Open WebUI fork: add or change fork commits, sync the stack manifest, resolve upstream-rebase conflicts, and keep package code out of the fork. Use for losus-openwebui or losus-roster commits, rebases and CI guards. Not for building Losus runtime features."
license: MIT
compatibility: "Requires git 2.26+, Python 3.9+, Node 22 for lockfile regeneration. Run from the repo root."
metadata:
  author: Losus AI LLC
  version: "1.0"
---

# Losus fork stack

Two repos, one boundary:

| Repo | Holds | License |
|---|---|---|
| `losus-openwebui` | Open WebUI fork. Branch `losus/main` = upstream tag + a few `losus:` commits | Open WebUI License |
| `losus-roster` | All product code: `packages/*`, `roles/*` | MIT |

Detect the repo: `.losus/stack.json` exists → fork. `scripts/check-boundary.py` exists → roster.

## Rules

- Product logic, UI components, schemas, connectors and role manifests go in `losus-roster`. The fork only gets glue: the sidebar hook, dependency pins, Tailwind path, fork notice and Losus tooling.
- Never copy Open WebUI source into `losus-roster`, and never import `open_webui.*` or `$lib/` there.
- Every fork commit subject starts with `losus:`. No merge commits on `losus/main`.
- `.losus/stack.json` lists the stack. `allowed_paths` and `denied_paths` decide which files fork commits may touch. Don't widen `allowed_paths` unless the user agrees that the change can't live in a package.
- Prefer amending or fixing up an existing commit over adding a new one. Keep the stack at or under `max_commits`.
- Never push `losus/main` directly after a rebase. Promotion happens through the `fork-promotion` approval in CI.

## First run in a fork clone

```bash
python3 scripts/losus/stack.py install-hooks   # pre-commit + commit-msg guards
git remote add upstream https://github.com/open-webui/open-webui.git
git fetch upstream --tags
scripts/losus/rerere-sync.sh pull              # reuse known conflict fixes
```

Done when `python3 scripts/losus/stack.py check` prints `OK`.

## Change the fork

1. Ask whether the change belongs in a package. If it does, make it in `losus-roster` instead and only bump the pinned version in the fork's `package.json`.
2. Find the owning commit with `python3 scripts/losus/stack.py list`.
3. Make the edit. To fold it into an existing commit: `git commit --fixup=<sha>`, then `git rebase -i --autosquash <base-tag>`. For a genuinely new concern: `git commit -m "losus: <what>"`.
4. Run `python3 scripts/losus/stack.py sync`. Fill in any `purpose` that reads `TODO`, then `git add .losus/stack.json && git commit --amend --no-edit`.
5. Done when `python3 scripts/losus/stack.py check` prints `OK`. Push to a branch and open a PR to `losus/main`. The stack-guard workflow re-runs the check.

If the pre-commit hook rejects a path, unstage it (`git restore --staged <path>`) and move the change into `losus-roster`. Don't bypass the hook with `--no-verify`, because CI runs the same check.

## Upstream rebase

CI (`.github/workflows/losus-upstream-rebase.yml`) runs weekly: rebase → stack check → Docker build, hook check and `/health` → approval → promote and tag `vX.Y.Z-losus.N`. Run it manually with `gh workflow run losus-upstream-rebase.yml -f target_tag=vX.Y.Z`.

When it opens an `upstream-rebase` issue:

1. `scripts/losus/rerere-sync.sh pull`
2. Run the commands from the issue body, which check out `upgrade/vX.Y.Z` and start the rebase.
3. Resolve each conflict by keeping upstream's code and re-applying only the Losus intent described by that commit's `purpose` in `.losus/stack.json`. For `package-lock.json`, take upstream's (`git checkout --ours package-lock.json`), then `npm install --package-lock-only --force --ignore-scripts`.
4. `git add` and `git rebase --continue` until the rebase finishes, then `python3 scripts/losus/stack.py check --allow-dropped`.
5. If commits were dropped because upstream absorbed them, run `stack.py sync` and amend the manifest into the last commit.
6. `scripts/losus/rerere-sync.sh push`, then `git push --force-with-lease origin upgrade/vX.Y.Z`, then re-run the workflow with the same `target_tag`.

Done when the workflow reaches the `fork-promotion` approval with a passing stack check.

## In `losus-roster`

- Install the hook once: `git config core.hooksPath .githooks`.
- Every source file starts with an SPDX header: `# SPDX-License-Identifier: MIT` (Python), `// SPDX-License-Identifier: MIT` (TS/JS), `<!-- SPDX-License-Identifier: MIT -->` (Svelte).
- Done when `python3 scripts/check-boundary.py` passes. Add the same command to CI.

## Example

User: "Add an Approvals link under the Agents section in the sidebar."
→ The link markup goes in `@losus/ui` (`LosusAgents.svelte`) in `losus-roster`. Release a new version, then in the fork bump `@losus/ui` in `package.json`, fold that into the dependency-pin commit with a fixup, run `stack.py sync` and `stack.py check`, and open a PR. `Sidebar.svelte` doesn't change.
