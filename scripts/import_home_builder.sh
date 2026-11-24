#!/usr/bin/env bash
# Import exact upstream tracked source; run from a clean clone on dev/fzm-builder.
# This does not install, execute, publish, or modify upstream code.
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"
test "$(git branch --show-current)" = "dev/fzm-builder" || { echo "Use dev/fzm-builder"; exit 1; }
test -z "$(git status --porcelain)" || { echo "Working tree must be clean"; exit 1; }
target=extensions/fzm_builder
test ! -e "$target" || { echo "$target already exists; refusing overwrite"; exit 1; }
upstream=https://github.com/CreativeDesigner3D/home_builder_5.git
expected=f345c1710161a4d09149d8ec7b610d0c6f2a9d5e
git fetch --no-tags --depth=1 "$upstream" refs/tags/v5.1.2
actual="$(git rev-parse 'FETCH_HEAD^{commit}')"
test "$actual" = "$expected" || { echo "Unexpected upstream commit: $actual"; exit 1; }
mkdir -p "$target"
git archive "$actual" | tar -x -C "$target"
test -f "$target/LICENSE" && test -f "$target/blender_manifest.toml" && test -d "$target/geometry_nodes"
echo "Imported pinned source into $target. Review tracked assets and licenses; stage and commit explicitly. Do not install or publish yet."
