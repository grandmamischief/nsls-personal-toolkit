#!/usr/bin/env bash
# PERSONAL FORK (davo/todoist): re-anchor hardcoded repo paths to this clone.
#
# Upstream skills hardcode the team install path
# (~/.claude/local-plugins/nsls-personal-toolkit). This fork runs from
# ~/Projects/pp-fork, so those literals must point HERE — otherwise the
# skills would launch the OLD checkout's companion and test vault.
#
# Run me after EVERY upstream merge (idempotent):
#   git merge upstream/main   # resolve conflicts, prefer upstream on path lines
#   bash scripts/fork-repath.sh
#
# Deliberately NOT repathed: docs/, updates/ (historical records), and
# docs/plans/todoist-personal-fork.md (references both paths on purpose).

set -euo pipefail
cd "$(dirname "$0")/.."

FILES=$(grep -rl "local-plugins/nsls-personal-toolkit" \
  --include="*.md" --include="*.py" --include="*.sh" --include="*.ps1" \
  skills/ hooks/ commands/ .claude-plugin/ companion/ \
  CLAUDE.md README.md install.sh install.ps1 2>/dev/null || true)

if [ -z "$FILES" ]; then
  echo "fork-repath: nothing to do — all functional paths already point here."
  exit 0
fi

for f in $FILES; do
  sed -i '' \
    -e 's|\$HOME/\.claude/local-plugins/nsls-personal-toolkit|\$HOME/Projects/pp-fork|g' \
    -e 's|~/\.claude/local-plugins/nsls-personal-toolkit|~/Projects/pp-fork|g' \
    -e 's|/Users/[a-z0-9_]*/\.claude/local-plugins/nsls-personal-toolkit|/Users/claw/Projects/pp-fork|g' \
    -e "s|'\.claude/local-plugins/nsls-personal-toolkit|'Projects/pp-fork|g" \
    -e 's|"\.claude/local-plugins/nsls-personal-toolkit|"Projects/pp-fork|g' \
    -e 's|"local-plugins/nsls-personal-toolkit"|"Projects/pp-fork"|g' \
    "$f"
  echo "fork-repath: $f"
done
echo "fork-repath: done."
