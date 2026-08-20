#!/usr/bin/env bash
# Fixture: CARRIER — marker text emitted from a heredoc body (a doc
# generator, a help text, a fixture writer). Heredoc bodies are DATA, not
# comments attached to code, so they must not trip the scan.
usage() {
    cat <<'EOF'
Mutation markers this project refuses in production sources:
    # MUTATED for §11.4.115 RED
    // always pass
EOF
}
