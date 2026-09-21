"""Thin client for KB kbs (MCP JSON-RPC over HTTP). Never mounts the full tool surface."""
import json, os
from .util import http_json, cfg, log

_MAP = None


# v0.2 renamed brain-map.json -> kb-map.json. A KB tenant is the KB: memory and
# knowledge. "Brain" now means the whole assembly (KB + model + skills + policy +
# tools), so calling a tenant a brain was wrong. The old file still loads for one
# version so an existing install keeps working; the warning says what to rename.
def kb_map():
    global _MAP
    if _MAP is None:
        try:
            _MAP = cfg("kb-map.json")
        except FileNotFoundError:
            # A clean checkout has no kb-map.json — it is gitignored because it
            # names real tenants and hosts. Fall back to the shipped example so
            # the repo runs out of the box, and say so rather than failing with
            # a bare FileNotFoundError.
            _MAP = cfg("kb-map.example.json")
            log("No config/kb-map.json — using config/kb-map.example.json. "
                "Copy it and fill in your own knowledge bases.")
    # Keys beginning with "_" are comments, not knowledge bases.
    return {k: v for k, v in _MAP.items() if not k.startswith("_")}


def _rpc(kb, tool, args):
    b = kb_map()[kb]
    pat = os.environ.get(b["pat_env"], "")
    if not pat:
        raise RuntimeError(f"kb '{kb}': env {b['pat_env']} not set in .env")
    payload = {"jsonrpc": "2.0", "id": 1, "method": "tools/call",
               "params": {"name": tool, "arguments": {"tenant_code": b["tenant_code"], **args}}}
    import urllib.request
    req = urllib.request.Request(b["mcp_url"], method="POST", data=json.dumps(payload).encode())
    req.add_header("Authorization", f"Bearer {pat}")
    req.add_header("Content-Type", "application/json")
    req.add_header("Accept", "application/json, text/event-stream")
    with urllib.request.urlopen(req, timeout=120) as r:
        raw = r.read().decode("utf-8", "replace")
    for block in raw.split("\n\n"):           # unwrap SSE framing
        data = "\n".join(l[5:].strip() for l in block.splitlines() if l.startswith("data:"))
        if data:
            raw = data
            break
    outer = json.loads(raw)
    if "error" in outer:
        raise RuntimeError(f"kb {kb} {tool}: {outer['error']}")
    return json.loads(outer["result"]["content"][0]["text"])


def search(kb, query, k=5):
    """Fast cited hits: filename + snippet per hit."""
    res = _rpc(kb, "kb.similarity_search", {"query": query, "k": k, "layer": "project"})
    hits = []
    for h in res.get("hits", []):
        m = h.get("metadata", {})
        hits.append({"source": m.get("filename") or m.get("repo_path") or m.get("url", "?"),
                     "doc_id": m.get("doc_id", "?"), "text": h.get("text", "")[:800]})
    return hits


def answer(kb, question):
    """Synthesized answer with sources (slower)."""
    res = _rpc(kb, "kb.context_search", {"query": question, "layer": "project"})
    return res


def ingest(kb, filename, text, metadata, ontology=None):
    """Write one document. `ontology` overrides the kb default — session cards
    use the shared agent_context ontology; everything else uses the kb's own."""
    b = kb_map()[kb]
    if not b.get("write"):
        raise RuntimeError(f"kb '{kb}' is read-only by policy")
    job = _rpc(kb, "kb.documents.ingest",
               {"ontology": ontology or b["ontology"], "layer": "project",
                "filename": filename, "text": text, "metadata": metadata})
    return job
