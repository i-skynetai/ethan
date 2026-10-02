"""Thin client for KB kbs (MCP JSON-RPC over HTTP). Never mounts the full tool surface."""
import json, os, re
from .util import log

CONFIG_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config")

_MAP = None


# v0.2 renamed brain-map.json -> kb-map.json. A KB tenant is the KB: memory and
# knowledge. "Brain" now means the whole assembly (KB + model + skills + policy +
# tools), so calling a tenant a brain was wrong. The old file still loads for one
# version so an existing install keeps working; the warning says what to rename.
def kb_map_path():
    """The map file actually in use — the real one, else the shipped example.

    Two callers need this answer and they must not disagree. `kb_map()` reads it, and
    `hands.build_command` passes it to `sky --kb-map`. Those used to be resolved
    separately: the router would fall back to the example while the hand was handed a
    path to `kb-map.json`, a file a clean checkout does not have. Everything looked
    fine until something was actually built.
    """
    if os.environ.get("ETHAN_KB_MAP"):          # the demo brings its own map
        return os.path.abspath(os.path.expanduser(os.environ["ETHAN_KB_MAP"]))
    real = os.path.join(CONFIG_DIR, "kb-map.json")
    return real if os.path.isfile(real) else os.path.join(CONFIG_DIR, "kb-map.example.json")


def kb_map():
    global _MAP
    if _MAP is None:
        path = kb_map_path()
        with open(path) as fh:
            _MAP = json.load(fh)
        if path.endswith("kb-map.example.json"):
            # A clean checkout has no kb-map.json — it is gitignored because it
            # names real tenants and hosts. The shipped example keeps the repo
            # running, and this says so rather than failing on a missing file.
            log("No config/kb-map.json — using config/kb-map.example.json. "
                "Copy it and fill in your own knowledge bases.")
    # Keys beginning with "_" are comments, not knowledge bases.
    return {k: v for k, v in _MAP.items() if not k.startswith("_")}


def _folder(b):
    """A KB with `folder` is a directory of Markdown files on this machine: no
    server, no token. A relative path is relative to the map file."""
    folder = os.path.expanduser(b["folder"])
    return folder if os.path.isabs(folder) else os.path.join(os.path.dirname(kb_map_path()), folder)


def _folder_search(b, query, k):
    """Rank the folder's notes by how many of the query's words they contain."""
    words = {w for w in re.findall(r"[a-z0-9]+", query.lower()) if len(w) > 2}
    scored = []
    folder = _folder(b)
    for name in sorted(os.listdir(folder)) if os.path.isdir(folder) else []:
        if not name.endswith(".md"):
            continue
        with open(os.path.join(folder, name), encoding="utf-8") as fh:
            text = fh.read()
        score = len(words & set(re.findall(r"[a-z0-9]+", text.lower())))
        if score:
            scored.append((-score, name, text))
    return [{"source": name, "doc_id": name, "text": text[:800]}
            for _, name, text in sorted(scored)[:k]]


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
    b = kb_map()[kb]
    if b.get("folder"):
        return _folder_search(b, query, k)
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
    if b.get("folder"):
        os.makedirs(_folder(b), exist_ok=True)
        with open(os.path.join(_folder(b), os.path.basename(filename)), "w", encoding="utf-8") as fh:
            fh.write(text + "\n")
        return {"job_id": f"local:{os.path.basename(filename)}"}
    job = _rpc(kb, "kb.documents.ingest",
               {"ontology": ontology or b["ontology"], "layer": "project",
                "filename": filename, "text": text, "metadata": metadata})
    return job
