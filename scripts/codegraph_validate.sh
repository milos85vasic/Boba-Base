#!/usr/bin/env bash
# codegraph_validate.sh — Boba anti-bluff CodeGraph verification (§11.4.78 step 4).
#
# Purpose:
#   Prove the CodeGraph index is REAL and correctly scoped — not a §11.4 PASS-bluff.
#   Six checks, each backed by an observable fact obtained ONLY from CodeGraph
#   (CLI + MCP), never from this script reading files itself:
#     1. codegraph binary present + version on PATH (no hardcoded host path).
#     2. Index reality          — `codegraph status` reports nodeCount > 0.
#     3. Unforgeable MCP challenge — `codegraph serve --mcp` → tools/call
#        codegraph_status returns the SAME node count as the CLI (a fact an
#        agent answering from its own file tools cannot fabricate).
#     4. Own-code resolves      — a symbol from download-proxy/src resolves.
#     5. Own-org submodule included (§11.4.79) — a symbol living ONLY inside the
#        `constitution/` submodule resolves to a constitution/ path.
#     6. Third-party excluded + secrets excluded (§11.4.79 + §11.4.10) — NO
#        `submodules/jackett` path and NO real secret path is in the index.
#
# Usage:   bash scripts/codegraph_validate.sh
# Outputs: PASS/FAIL lines + a final verdict; exit 0 all-pass, 1 any-fail,
#          2 environment problem (codegraph absent / not initialized).
#
# Side-effects: read-only against the index; starts a transient MCP server that
#   it tears down. Never prints secrets.
# Dependencies: codegraph (on PATH, npm-installed per §11.4.78), node, bash.
# Cross-references: §11.4.78 / §11.4.79 / §11.4.10 / §11.4.80 (codegraph_sync.sh
#   step 4 invokes this), docs/CODEGRAPH.md, docs/codegraph/Status.md.

set -uo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${PROJECT_ROOT}"

PASS=0
FAIL=0
pass() { echo "PASS: $1"; PASS=$((PASS + 1)); }
fail() { echo "FAIL: $1"; FAIL=$((FAIL + 1)); }

# --- 0. environment ------------------------------------------------------
if ! command -v codegraph >/dev/null 2>&1; then
    echo "ENV-FAIL: codegraph not on PATH — install per §11.4.78 (npm install -g @colbymchenry/codegraph)." >&2
    exit 2
fi
if ! command -v node >/dev/null 2>&1; then
    echo "ENV-FAIL: node not on PATH — required by this validator." >&2
    exit 2
fi
if [ ! -d "${PROJECT_ROOT}/.codegraph" ]; then
    echo "ENV-FAIL: ${PROJECT_ROOT}/.codegraph missing — run codegraph init + index first." >&2
    exit 2
fi

CG_VERSION="$(codegraph --version 2>/dev/null | head -1)"
CG_PATH="$(command -v codegraph)"
pass "codegraph on PATH at ${CG_PATH} (version ${CG_VERSION})"

# --- helpers -------------------------------------------------------------
status_json() { codegraph status . --json 2>/dev/null; }
files_json()  { codegraph files --json 2>/dev/null; }

# --- 1. index reality ----------------------------------------------------
CLI_NODES="$(status_json | node -e "let d='';process.stdin.on('data',c=>d+=c).on('end',()=>{try{console.log(JSON.parse(d).nodeCount||0)}catch(e){console.log(0)}})")"
CLI_FILES="$(status_json | node -e "let d='';process.stdin.on('data',c=>d+=c).on('end',()=>{try{console.log(JSON.parse(d).fileCount||0)}catch(e){console.log(0)}})")"
if [ "${CLI_NODES}" -gt 0 ] 2>/dev/null; then
    pass "index reality — codegraph status reports ${CLI_NODES} nodes across ${CLI_FILES} files"
else
    fail "index reality — codegraph status reports 0 nodes (index empty / not built)"
fi

# --- 2. unforgeable MCP challenge (§11.4.78 step 4) ----------------------
# Drive the real MCP server over stdio; the node count it returns MUST match
# the CLI. A file-reading impostor cannot produce this number.
MCP_NODES="$(
  {
    printf '%s\n' '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"validate","version":"0"}}}'
    printf '%s\n' '{"jsonrpc":"2.0","method":"notifications/initialized"}'
    sleep 1
    printf '%s\n' "{\"jsonrpc\":\"2.0\",\"id\":3,\"method\":\"tools/call\",\"params\":{\"name\":\"codegraph_status\",\"arguments\":{\"projectPath\":\"${PROJECT_ROOT}\"}}}"
    sleep 3
  } | timeout 30 codegraph serve --mcp 2>/dev/null \
    | node -e "let d='';process.stdin.on('data',c=>d+=c).on('end',()=>{let n=0;for(const l of d.split('\n').filter(Boolean)){try{const j=JSON.parse(l);if(j.id===3){const t=(j.result&&j.result.content&&j.result.content[0]&&j.result.content[0].text)||'';const m=t.match(/Total nodes:\*\*\s*([0-9]+)/);if(m)n=parseInt(m[1],10);}}catch(e){}}console.log(n)})"
)"
if [ "${MCP_NODES}" = "${CLI_NODES}" ] && [ "${MCP_NODES}" -gt 0 ] 2>/dev/null; then
    pass "unforgeable MCP challenge — codegraph_status via MCP returned ${MCP_NODES} nodes == CLI ${CLI_NODES}"
else
    fail "unforgeable MCP challenge — MCP node count '${MCP_NODES}' != CLI '${CLI_NODES}' (MCP server not serving the real index)"
fi

# --- 3. own-code symbol resolves ----------------------------------------
OWN_HIT="$(codegraph query "Deduplicator" --limit 10 --json 2>/dev/null | node -e "let d='';process.stdin.on('data',c=>d+=c).on('end',()=>{try{const r=JSON.parse(d);console.log(r.filter(x=>/^download-proxy\/src\//.test(x.node&&x.node.filePath||'')).length)}catch(e){console.log(0)}})")"
if [ "${OWN_HIT}" -gt 0 ] 2>/dev/null; then
    pass "own-code resolution — 'Deduplicator' resolves in download-proxy/src (${OWN_HIT} hit(s))"
else
    fail "own-code resolution — 'Deduplicator' did not resolve to download-proxy/src"
fi

# --- 4. own-org submodule INCLUDED (§11.4.79) ---------------------------
CONST_HIT="$(codegraph query "versionTagsCmd" --limit 10 --json 2>/dev/null | node -e "let d='';process.stdin.on('data',c=>d+=c).on('end',()=>{try{const r=JSON.parse(d);console.log(r.filter(x=>/^constitution\//.test(x.node&&x.node.filePath||'')).length)}catch(e){console.log(0)}})")"
if [ "${CONST_HIT}" -gt 0 ] 2>/dev/null; then
    pass "own-org INCLUDED (§11.4.79) — 'versionTagsCmd' resolves inside constitution/ (${CONST_HIT} hit(s))"
else
    fail "own-org INCLUDED (§11.4.79) — constitution-only symbol 'versionTagsCmd' NOT in index (own-org submodule excluded?)"
fi

# --- 5. third-party EXCLUDED + secrets EXCLUDED (§11.4.79 + §11.4.10) ----
AUDIT="$(files_json | node -e "let d='';process.stdin.on('data',c=>d+=c).on('end',()=>{try{const j=JSON.parse(d);const a=Array.isArray(j)?j:(j.files||j.nodes||[]);const p=a.map(x=>x.path||x.relativePath||x.file||x).filter(Boolean);const jk=p.filter(s=>/^submodules\/jackett/.test(s)).length;const sec=p.filter(s=>/(^\.env)|(^config\/qBittorrent)|(^config\/jackett)|(boba\.db)|(\.qbit\.env)|(cookies?\.txt)|(credentials\.json)/i.test(s)).length;console.log(jk+' '+sec)}catch(e){console.log('ERR ERR')}})")"
JK_COUNT="${AUDIT%% *}"
SEC_COUNT="${AUDIT##* }"
if [ "${JK_COUNT}" = "0" ]; then
    pass "third-party EXCLUDED (§11.4.79) — 0 submodules/jackett paths in index"
else
    fail "third-party EXCLUDED (§11.4.79) — ${JK_COUNT} submodules/jackett paths leaked into index"
fi
if [ "${SEC_COUNT}" = "0" ]; then
    pass "secrets EXCLUDED (§11.4.10) — 0 secret/config-credential paths in index"
else
    fail "secrets EXCLUDED (§11.4.10) — ${SEC_COUNT} secret/config-credential paths leaked into index"
fi

# --- verdict -------------------------------------------------------------
echo "----------------------------------------"
echo "CodeGraph validate: ${PASS} PASS / ${FAIL} FAIL"
if [ "${FAIL}" -eq 0 ]; then
    echo "VERDICT: PASS"
    exit 0
fi
echo "VERDICT: FAIL"
exit 1
