#!/usr/bin/env bash
# Run one query against merge-service /api/v1/search/sync. Timeout 30s.
set -u
slug="$1"; query="$2"
out="results/${slug}.json"
start=$(date +%s.%N)
http_code=$(curl -sS --max-time 30 -o "${out}.raw" -w "%{http_code}" \
  -X POST http://localhost:7187/api/v1/search/sync \
  -H 'Content-Type: application/json' \
  -d "{\"query\":\"${query}\",\"limit\":5,\"sources\":[\"rutracker\",\"kinozal\",\"nnmclub\",\"rutor\"]}" 2>&1) || http_code="TIMEOUT"
end=$(date +%s.%N)
dur=$(echo "$end - $start" | bc)
# Try to pretty-print
if jq . "${out}.raw" > "${out}" 2>/dev/null; then
  rm -f "${out}.raw"
else
  mv "${out}.raw" "${out}"
fi
# Extract summary
if jq -e . "${out}" > /dev/null 2>&1; then
  total=$(jq -r '.total_results // .totalResults // (.results|length) // "?"' "${out}")
  errs=$(jq -r '[.tracker_stats[]? | select(.error_type != null and .error_type != "") | .name] | join(",") // ""' "${out}" 2>/dev/null || echo "")
  stats=$(jq -c '[.tracker_stats[]? | {name,count,error_type,elapsed_ms}]' "${out}" 2>/dev/null || echo "[]")
else
  total="parse_error"
  errs=""
  stats="[]"
fi
printf '%s|%s|%s|%.2fs|total=%s|errs=%s|stats=%s\n' "$slug" "$query" "$http_code" "$dur" "$total" "$errs" "$stats"
