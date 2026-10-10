# TODO

## Build phases

- [x] Phase 0: organization, fork, `cowork` branch and local clone (see [build phases](build-phases.md))
- [ ] Verification tasks, before any building
- [ ] Phase 1: baseline build and run on the Spark
- [ ] Phase 2: theme and branding
- [ ] Phase 3: projects
- [ ] Phase 4: task inbox
- [ ] Phase 5: agent-limited projects
- [ ] Phase 6: harden

## Next steps

### Repo structure (ADR 0005)

1. Read the Losus fork-stack kit in `LosusRoster` and answer the open questions in ADR 0005.
2. Rename the GitHub repo `opencowork-ui` to `losus-openwebui` and the branch `cowork` to `losus/main`; create `losus-roster`.
3. Move the docs to the repo the answers point to, and update the repo names and code locations in the specs and plans.

### Build phases

1. Run the verification tasks in [build phases](build-phases.md) and record each result as confirmed or not reproduced.
2. Add the repo to the `git-guard` allowlist on the Spark before committing there.
3. Start phase 1: build and run the unmodified fork.
