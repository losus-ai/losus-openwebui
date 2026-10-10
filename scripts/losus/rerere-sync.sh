#!/usr/bin/env bash
# Share git rerere conflict resolutions between your machine and CI.
#
#   scripts/losus/rerere-sync.sh pull   # merge origin's saved resolutions into .git/rr-cache
#   scripts/losus/rerere-sync.sh push   # pull, then publish the combined cache
#
# Resolutions are stored on an orphan branch (default: losus/rr-cache) so they
# never touch the product code history.

set -euo pipefail

MODE="${1:-pull}"
REMOTE="${RERERE_REMOTE:-origin}"
BRANCH="${RERERE_BRANCH:-losus/rr-cache}"
GIT_DIR_ABS="$(git rev-parse --absolute-git-dir)"
CACHE="$GIT_DIR_ABS/rr-cache"

pull() {
  mkdir -p "$CACHE"
  if git fetch -q "$REMOTE" "refs/heads/$BRANCH:refs/remotes/$REMOTE/$BRANCH" 2>/dev/null; then
    git archive "refs/remotes/$REMOTE/$BRANCH" | tar -x -C "$CACHE"
    echo "rr-cache: restored $(find "$CACHE" -mindepth 1 -maxdepth 1 -type d | wc -l) resolution(s) from $REMOTE/$BRANCH"
  else
    echo "rr-cache: no $REMOTE/$BRANCH yet, starting empty"
  fi
}

push() {
  pull
  if [[ -z "$(ls -A "$CACHE" 2>/dev/null)" ]]; then
    echo "rr-cache: nothing to publish"; return 0
  fi
  local idx; idx="$(mktemp)"; rm -f "$idx"
  local tree parent commit
  tree="$(cd "$CACHE" && GIT_INDEX_FILE="$idx" git --git-dir="$GIT_DIR_ABS" --work-tree=. add -A . \
          && GIT_INDEX_FILE="$idx" git --git-dir="$GIT_DIR_ABS" write-tree)"
  rm -f "$idx"
  parent="$(git rev-parse -q --verify "refs/remotes/$REMOTE/$BRANCH" || true)"
  if [[ -n "$parent" && "$(git rev-parse "$parent^{tree}")" == "$tree" ]]; then
    echo "rr-cache: $REMOTE/$BRANCH already up to date"; return 0
  fi
  commit="$(git commit-tree "$tree" ${parent:+-p "$parent"} -m "rr-cache: update resolutions")"
  git push -q "$REMOTE" "$commit:refs/heads/$BRANCH"
  echo "rr-cache: published to $REMOTE/$BRANCH"
}

case "$MODE" in
  pull) pull ;;
  push) push ;;
  *) echo "usage: $0 pull|push" >&2; exit 2 ;;
esac
