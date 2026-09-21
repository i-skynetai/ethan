#!/usr/bin/env bash
# extract-model.sh — show or switch the model the LOCAL knowledge base uses to
# extract entities. One binding serves every tenant on the instance, so this
# decides whether local content is processed externally or stays on the laptop.
#
#   tools/extract-model.sh                 show the current model
#   tools/extract-model.sh gpt-4o          external, best quality
#   tools/extract-model.sh granite4.1:8b   local via Ollama, nothing leaves
set -uo pipefail

API=http://localhost:8000
ENV_FILE="$(dirname "$0")/../.env"
[ -f "$ENV_FILE" ] && { set -a; . "$ENV_FILE"; set +a; }
: "${KB_LOCAL_PAT:?KB_LOCAL_PAT not set in .env}"

show() {
  curl -sS --max-time 15 "$API/admin/llm-bindings" -H "Authorization: Bearer $KB_LOCAL_PAT" \
  | python3 -c '
import json,sys
d=json.load(sys.stdin)
cur={b["operation"]:b["llm_model"] for b in d.get("bindings",[])}
m=cur.get("ingestion.extract","(unset — falls back to LLM_MODEL)")
local = m.startswith(("granite","gemma","llama","qwen","phi","mistral"))
print(f"  extraction model: {m}")
print("  " + ("stays on this laptop" if local else "sent to an external provider"))'
}

[ $# -eq 0 ] && { show; exit 0; }
MODEL="$1"

# a local model is useless if Ollama is not serving it — check before switching
case "$MODEL" in
  granite*|gemma*|llama*|qwen*|phi*|mistral*)
    curl -sS --max-time 5 http://localhost:11434/api/tags >/dev/null 2>&1 \
      || { echo "ollama is not running — start it with: brew services start ollama"; exit 1; }
    ollama list 2>/dev/null | awk 'NR>1{print $1}' | grep -qx "$MODEL" \
      || { echo "ollama has no model '$MODEL' — pull it first: ollama pull $MODEL"; exit 1; }
    ;;
esac

code=$(curl -sS -o /tmp/bind.json -w '%{http_code}' --max-time 20 \
  -X PATCH "$API/admin/llm-bindings/ingestion.extract" \
  -H "Authorization: Bearer $KB_LOCAL_PAT" -H 'Content-Type: application/json' \
  -d "$(python3 -c "import json,sys;print(json.dumps({'llm_model':sys.argv[1]}))" "$MODEL")")
[ "$code" = "200" ] || { echo "switch failed (HTTP $code): $(head -c 200 /tmp/bind.json)"; exit 1; }

# the binding is cached at process start, so the change is inert until a restart
echo "  binding updated -> $MODEL; restarting the API so it takes effect"
docker restart kb-api >/dev/null 2>&1
for i in $(seq 1 40); do
  sleep 3
  [ "$(curl -sS -o /dev/null -w '%{http_code}' --max-time 5 $API/health 2>/dev/null)" = "200" ] && break
done
show
