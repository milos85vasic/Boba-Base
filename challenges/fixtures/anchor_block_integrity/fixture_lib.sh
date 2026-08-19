# fixture_lib.sh — helpers for anchor_block_integrity fixture authoring.
# Sourced by the challenge harness; NOT executable on its own.

# emit_config <fixture_dir>
#   Writes an anchor_block_integrity_check.conf that points the checker
#   at the fixture's `mirrors/` subtree so the real repository is never
#   touched during a fixture run.
emit_config() {
  local fixture_dir="$1"
  cat > "$fixture_dir/anchor_block_integrity_check.conf" <<'CONF'
BASE_DIR="./mirrors"
MIRROR_SET=(
  "CLAUDE.md"
  "AGENTS.md"
  "QWEN.md"
  "GEMINI.md"
)
CANONICAL_FILE="Constitution.md"
BLOCK_START_RE='^(#{2,4} §11\.4\.[0-9]+([.][A-Za-z0-9]+)?|\*\*§11\.4\.[0-9]+([.][A-Za-z0-9]+)?)'
ANCHOR_ID_RE='§11\.4\.[0-9]+([.][A-Za-z0-9]+)?'
CONF
}
