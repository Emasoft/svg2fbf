#!/usr/bin/env bash
# regen_e2e_reference.sh — regenerate the byte-exact E2E reference output.
#
# Run this ONLY when you intentionally change either the input frames in
# tests/fixtures/e2e/frames/ OR the CLI invocation in
# tests/fixtures/e2e/expected/COMMAND.txt. After running, commit the
# regenerated tests/fixtures/e2e/expected/animation.fbf.svg in the same
# commit as the change that prompted it — so the diff is reviewable.
#
# DO NOT run this just because the byte-exact test failed. A failure
# means svg2fbf's output drifted, and that drift needs to be reviewed
# (and the fix or the reference update committed deliberately).

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

EPOCH="$(cat tests/fixtures/e2e/expected/SOURCE_DATE_EPOCH | tr -d '[:space:]')"
TMP_OUT="$(mktemp -d -t svg2fbf-regen-XXXXXX)"
trap 'rm -rf "$TMP_OUT"' EXIT

echo "▶ Regenerating reference with SOURCE_DATE_EPOCH=$EPOCH"
SOURCE_DATE_EPOCH="$EPOCH" PYTHONPATH=src uv run python src/svg2fbf.py \
    -i tests/fixtures/e2e/frames \
    -o "$TMP_OUT" \
    --no-browser -s 2.0 -a once -d 6 -c 6 -q

OLD="tests/fixtures/e2e/expected/animation.fbf.svg"
NEW="$TMP_OUT/animation.fbf.svg"

if [[ ! -f "$NEW" ]]; then
    echo "✗ Regeneration produced no output" >&2
    exit 1
fi

if cmp -s "$OLD" "$NEW"; then
    echo "✓ Reference is already up to date — no regen needed."
    exit 0
fi

echo ""
echo "Diff between current reference and regenerated output:"
# diff returns non-zero when files differ (which is the whole point here),
# and `set -e` would otherwise abort the script. `|| true` keeps us going.
{ diff -u "$OLD" "$NEW" || true; } | head -60
echo ""
# Allow non-interactive approval via REGEN_E2E_CONFIRM=y for use in scripts.
if [[ "${REGEN_E2E_CONFIRM:-}" == "y" || "${REGEN_E2E_CONFIRM:-}" == "Y" ]]; then
    confirm="y"
else
    read -r -p "Apply this change to tests/fixtures/e2e/expected/animation.fbf.svg? [y/N]: " confirm
fi
if [[ "$confirm" != "y" && "$confirm" != "Y" ]]; then
    echo "Aborted — reference NOT updated."
    exit 1
fi

cp "$NEW" "$OLD"
echo "✓ Updated $OLD"
echo ""
echo "Now commit the change explicitly:"
echo "  git add tests/fixtures/e2e/expected/animation.fbf.svg"
echo "  git commit -m 'test: regenerate e2e reference (<reason>)'"
