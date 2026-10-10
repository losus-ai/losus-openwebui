#!/usr/bin/env bash
# Rebase the Losus patch stack onto a newer Open WebUI release tag.
#
# Usage:  scripts/losus/rebase-upstream.sh [target-tag]
# Env:    FORK_BRANCH   (default: losus/main)
#         UPSTREAM_URL  (default: https://github.com/open-webui/open-webui.git)
#
# Writes key=value results to $GITHUB_OUTPUT when running in Actions:
#   status = up-to-date | clean | conflict
#   base, target, branch, conflicts (comma-separated), stopped_at
#
# Exits 0 for all three statuses so the workflow decides what to do next.
# Exits non-zero only on unexpected errors.

set -euo pipefail

FORK_BRANCH="${FORK_BRANCH:-losus/main}"
UPSTREAM_URL="${UPSTREAM_URL:-https://github.com/open-webui/open-webui.git}"
TARGET="${1:-}"
OUT="${GITHUB_OUTPUT:-/dev/stdout}"
REPORT="${REPORT_FILE:-rebase-report.md}"

emit() { echo "$1=$2" >> "$OUT"; }
log()  { echo "::notice::$*" 2>/dev/null || echo "$*"; }

# 1. Make sure upstream remote and tags are present
git remote get-url upstream >/dev/null 2>&1 || git remote add upstream "$UPSTREAM_URL"
git fetch upstream --tags --force --quiet

# 2. Work out the upstream tag the stack currently sits on.
#    Only plain release tags count (vX.Y.Z); our own vX.Y.Z-losus.N tags are excluded.
BASE="$(git describe --tags --abbrev=0 --match 'v[0-9]*' --exclude '*-*' "$FORK_BRANCH")"

# 3. Pick the target: explicit argument, or the newest stable upstream tag
if [[ -z "$TARGET" ]]; then
  TARGET="$(git ls-remote --tags --refs upstream \
    | awk -F/ '{print $3}' \
    | grep -E '^v[0-9]+\.[0-9]+\.[0-9]+$' \
    | sort -V | tail -1)"
fi
git rev-parse -q --verify "refs/tags/$TARGET" >/dev/null || { echo "Unknown tag: $TARGET" >&2; exit 2; }

emit base "$BASE"
emit target "$TARGET"

NEWEST="$(printf '%s\n%s\n' "$BASE" "$TARGET" | sort -V | tail -1)"
if [[ "$BASE" == "$TARGET" || "$NEWEST" == "$BASE" ]]; then
  log "Stack is already on $BASE (target $TARGET). Nothing to do."
  emit status up-to-date
  exit 0
fi

BRANCH="upgrade/$TARGET"
emit branch "$BRANCH"
STACK_SIZE="$(git rev-list --count "$BASE..$FORK_BRANCH")"
log "Rebasing $STACK_SIZE Losus commit(s) from $BASE onto $TARGET as $BRANCH"

# 4. Rebase. rerere replays conflict resolutions you've made before;
#    --empty=drop removes commits that upstream has already absorbed.
git config rerere.enabled true      # applies to every rebase step, not just the first
git config rerere.autoupdate true   # stage files that rerere resolves
git checkout -q -B "$BRANCH" "$FORK_BRANCH"
export GIT_EDITOR=true
git rebase --empty=drop --onto "$TARGET" "$BASE" >/dev/null 2>&1 || true

# 5. Resolve what can be resolved automatically, stop on anything else
REASON=""
report_conflict() {
  local files=("$@")
  STOPPED_AT="$(git log -1 --format='%h %s' REBASE_HEAD 2>/dev/null || echo unknown)"
  {
    echo "## Upstream rebase blocked: $BASE → $TARGET"
    echo
    echo "Stopped while applying: \`$STOPPED_AT\`"
    [[ -n "$REASON" ]] && { echo; echo "Reason: $REASON"; }
    echo
    echo "Conflicting files:"
    for f in "${files[@]}"; do echo "- \`$f\`"; done
    echo
    echo "### Resolve locally"
    echo '```bash'
    echo "git fetch origin && git fetch upstream --tags"
    echo "git checkout -B $BRANCH origin/$FORK_BRANCH"
    echo "git -c rerere.enabled=true rebase --empty=drop --onto $TARGET $BASE"
    echo "# fix conflicts, git add, git rebase --continue"
    echo "git push --force-with-lease origin $BRANCH"
    echo '```'
    echo
    echo "Then run \`scripts/losus/rerere-sync.sh push\` so the next automated run reuses your resolution."
  } > "$REPORT"
  git rebase --abort 2>/dev/null || true
  git checkout -q -f "$FORK_BRANCH"
  emit status conflict
  emit stopped_at "$STOPPED_AT"
  emit conflicts "$(IFS=,; echo "${files[*]}")"
  log "Conflict in: ${files[*]}"
}

in_rebase() { [[ -d "$(git rev-parse --git-path rebase-merge)" || -d "$(git rev-parse --git-path rebase-apply)" ]]; }

for _ in $(seq 1 100); do
  in_rebase || break

  mapfile -t CONFLICTS < <(git diff --name-only --diff-filter=U)

  if [[ ${#CONFLICTS[@]} -eq 0 ]]; then
    # rerere (or an earlier step) resolved everything for this commit
    git rebase --continue >/dev/null 2>&1 || true
    continue
  fi

  if [[ ${#CONFLICTS[@]} -eq 1 && "${CONFLICTS[0]}" == "package-lock.json" ]]; then
    # Never hand-merge a lockfile: take upstream's, then regenerate it
    # from the (already merged) package.json.
    log "Regenerating package-lock.json"
    git checkout --ours -- package-lock.json      # during rebase, "ours" = upstream side
    if ! npm install --package-lock-only --force --ignore-scripts --no-audit --no-fund >npm-lock.log 2>&1; then
      REASON="npm could not regenerate package-lock.json (see npm-lock.log)"
      report_conflict package-lock.json
      exit 0
    fi
    rm -f npm-lock.log
    git add package-lock.json
    git rerere forget package-lock.json >/dev/null 2>&1 || true   # never reuse a stale lockfile merge
    git rebase --continue >/dev/null 2>&1 || true
    continue
  fi

  report_conflict "${CONFLICTS[@]}"
  exit 0
done

if in_rebase; then
  echo "Rebase did not finish after 100 steps" >&2
  git rebase --abort
  exit 3
fi

# 6. Success: write a range-diff so reviewers see how *your* commits changed
NEW_SIZE="$(git rev-list --count "$TARGET..$BRANCH")"
{
  echo "## Upstream rebase ready: $BASE → $TARGET"
  echo
  echo "Losus commits: $STACK_SIZE before, $NEW_SIZE after."
  [[ "$NEW_SIZE" -lt "$STACK_SIZE" ]] && echo "Some commits were dropped because upstream now contains them."
  echo
  echo "### How the Losus stack changed (git range-diff)"
  echo '```diff'
  git range-diff --no-color --creation-factor=95 "$BASE..$FORK_BRANCH" "$TARGET..$BRANCH" || true
  echo '```'
} > "$REPORT"

emit status clean
log "Rebased cleanly onto $TARGET"
