"""Close-out. The hand decides what is worth keeping; Ethan decides what is allowed.

Ethan holds no rules about what matters — that judgement needs the full context of
the work, which only the hand has. Ethan's job is narrower and fixed: check the
decision against policy, perform the write itself (so a hand never holds a token),
and refuse out loud rather than silently.
"""
import json, re
from . import kb, hands, redact, store
from .util import cfg, log

MAX_BODY = 20000          # a knowledge note, not a transcript dump
MAX_TITLE = 120


PROMPT = """You have just finished a piece of work. Your own output is below.

--- YOUR OUTPUT ---
{output}
--- END OF YOUR OUTPUT ---

Decide, on your own judgement: is anything here worth keeping in a long-term
knowledge base, so a future task starts from it instead of rediscovering it?

Worth keeping: a decision and the reason for it; a non-obvious fact about how the
system actually behaves; a root cause; a gotcha; a correction of a belief that
turned out to be wrong; a design that was agreed; a measurement someone would
otherwise have to redo.

Not worth keeping: routine status, a restatement of the request, anything already
obvious from reading the code, your own narration of what you did.

These are the knowledge bases. Pick the ONE that fits, or none:
{kb_table}

Rules for the body you write:
- It must stand alone. Someone reading it months from now sees only this note —
  no "the above", no "as discussed", no reference to this conversation.
- Keep concrete details: file paths, numbers, command names, identifiers.
- State only what the work actually established. If something was assumed rather
  than verified, say so in the note.
- Markdown. Short. No preamble.

Reply with ONLY a JSON object. No prose before or after, no code fence:

{{"keep": true, "kb": "<kb name>", "title": "<short kebab-case title>",
  "body": "<the note, markdown>", "why": "<one line: why this is worth keeping>"}}

If nothing is worth keeping, reply exactly:

{{"keep": false, "why": "<one line: why not>"}}
"""


def _kb_table():
    rows = []
    for name, b in kb.kb_map().items():
        rows.append(f"- {name}: {b.get('purpose','')} "
                    f"[privacy={b.get('privacy','?')}, "
                    f"{'writable' if b.get('write') else 'READ-ONLY, cannot be chosen'}]")
    return "\n".join(rows)


def _extract_json(text):
    """Hands wrap JSON in prose or fences however they like. Take the last object
    that actually parses, scanning from each '{' to its matching '}'."""
    if not text:
        return None
    best = None
    for start in (i for i, c in enumerate(text) if c == "{"):
        depth, in_str, esc = 0, False, False
        for i in range(start, len(text)):
            c = text[i]
            if in_str:
                if esc:      esc = False
                elif c == "\\": esc = True
                elif c == '"':  in_str = False
                continue
            if c == '"':   in_str = True
            elif c == "{": depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0:
                    try:
                        obj = json.loads(text[start:i + 1])
                        if isinstance(obj, dict) and "keep" in obj:
                            best = obj
                    except Exception:
                        pass
                    break
    return best


def ask(hand, work_output, repo=None, task_id=None):
    """Ask the hand what it wants kept. Read-only: harvesting must not edit code."""
    prompt = PROMPT.format(output=work_output[-12000:], kb_table=_kb_table())
    res = hands.run(hand, prompt, repo, review=True, task_id=task_id)
    decision = _extract_json(res.get("out", ""))
    if decision is None:
        return None, f"{hand} did not return a usable JSON decision"
    return decision, None


def apply(decision, door, chat_id, hand):
    """Enforce policy, then write. Returns (status, message) — never raises."""
    if not decision.get("keep"):
        return "nothing", decision.get("why") or "hand kept nothing"

    name = (decision.get("kb") or "").strip()
    bmap = kb.kb_map()
    if name not in bmap:
        return "refused", f"hand picked kb '{name}', which does not exist"
    b = bmap[name]
    if not b.get("write"):
        return "refused", f"kb '{name}' is read-only by policy"

    # Fail CLOSED. An unknown door must never fall through to "no restrictions",
    # and a door with no classes declared grants nothing.
    doors = cfg("doors.json")
    if door not in doors:
        return "refused", f"unknown door '{door}' — refusing to write anywhere"
    allowed = doors[door].get("classes") or []
    if b.get("privacy") not in allowed:
        return "refused", (f"kb '{name}' is class '{b.get('privacy')}', which the "
                           f"'{door}' door may not write to (allows: "
                           f"{', '.join(allowed) or 'nothing'})")

    body = (decision.get("body") or "").strip()
    if len(body) < 40:
        return "refused", "the note was empty or too short to be worth storing"
    if len(body) > MAX_BODY:
        return "refused", f"note is {len(body)} chars, over the {MAX_BODY} cap"

    # Hard gate: a kb is long-lived and searchable, so a credential written
    # there is worse than one in scrollback. Refuse rather than scrub silently.
    leaks = redact.find(body)
    if leaks:
        return "refused", (f"note contains what looks like a secret "
                           f"({', '.join(leaks)}) — refusing to store it")

    title = re.sub(r"[^a-zA-Z0-9._-]+", "-", (decision.get("title") or "note")).strip("-")
    filename = f"{(title[:MAX_TITLE] or 'note')}.md"
    if not filename.endswith(".md"):
        filename += ".md"

    try:
        job = kb.ingest(name, filename, body, {
            "source": "ethan-harvest", "doc_type": "learning",
            "decided_by": hand, "door": door, "chat_id": str(chat_id),
            "why": (decision.get("why") or "")[:400],
        })
    except Exception as e:
        return "failed", f"write to '{name}' failed: {e}"

    store.add_harvest(chat_id, hand, name, filename, decision.get("why") or "", "written")
    log(f"harvest: {hand} -> {name}/{filename} (job {job.get('job_id')})")
    return "written", f"kept in {name}: {filename} — {decision.get('why','')}"


def run(hand, work_output, kb_repo, door, chat_id, task_id=None):
    """Full close-out for one finished piece of work."""
    if not cfg("ethan.json").get("harvest", True):
        return "off", "harvest disabled in config"
    decision, err = ask(hand, work_output, kb_repo, task_id)
    if err:
        store.add_harvest(chat_id, hand, "", "", err, "unparsed")
        return "unparsed", err
    status, msg = apply(decision, door, chat_id, hand)
    if status in ("refused", "failed"):
        store.add_harvest(chat_id, hand, decision.get("kb") or "", "", msg, status)
    return status, msg


def can_close(chat_id=None):
    """Ethan's only close-out judgement: is anything still outstanding?"""
    pend = store.pending(chat_id)
    if not pend:
        return True, "nothing pending"
    what = "; ".join(f"#{p['id']} {p['kind']}/{p['hand']}" for p in pend[:5])
    more = f" (+{len(pend) - 5} more)" if len(pend) > 5 else ""
    return False, f"{len(pend)} still running: {what}{more}"


# ── direct document ingest (CLI/console door) ───────────────────────────────
# The kb map is the single source of truth for WHERE a document goes: the
# file's location resolves the kb, the doc type resolves the ontology.
# Nothing here reads a per-repo config file.

# Session/skill docs get the shared agent-context schema — but only in WORK
# kb. A personal kb always uses its own ontology: agent_context is a
# work schema and must never hold personal data.
AGENT_CONTEXT_TYPES = {"session-context", "session_card"}

# A skill is a procedure — steps, tools, guardrails — and is extracted under the
# ontology built for that. `agent_context` records *use* of a skill, not the
# skill. "skill" used to sit in AGENT_CONTEXT_TYPES above, which put skill
# documents under the wrong ontology; the harness's ingest skill made the same
# mistake and both were fixed together.
SKILL_TYPES = {"skill"}


def ontology_for(doc_type: str, privacy: str | None, default: str) -> str:
    """Which ontology a document is ingested under.

    A personal kb always uses its own ontology, whatever the type. Everywhere
    else, session context goes to `agent_context`, a skill to `sky_skill`, and
    anything else to the kb's default.
    """
    if privacy == "personal":
        return default
    if doc_type in AGENT_CONTEXT_TYPES:
        return "agent_context"
    if doc_type in SKILL_TYPES:
        return "sky_skill"
    return default


def ingest_document(path, doc_type, door, chat_id, cwd=None):
    """Ingest one file, resolving everything from the kb map.
    Returns (status, info) where info is a dict on success, a message otherwise.

    The file's own location picks the KB — never the directory the command was run
    from. `cwd` is accepted for old callers and ignored: a private note outside every
    KB, ingested from inside a work repository, used to be filed into the work KB."""
    import os
    from . import sessions

    path = os.path.realpath(os.path.expanduser(path))
    if not os.path.isfile(path):
        return "refused", f"file not found: {path}"
    try:
        with open(path, errors="replace") as fh:
            text = fh.read()
    except Exception as e:
        return "refused", f"cannot read {path}: {e}"
    if len(text.strip()) < 40:
        return "refused", "file is empty or too short to be worth storing"
    if len(text) > 512_000:
        return "refused", f"file is {len(text)} chars — too large for a knowledge note"

    bmap = kb.kb_map()
    kb_name = sessions.route(os.path.dirname(path), bmap)
    if kb_name is None:
        known = ", ".join(bmap)
        return "refused", (f"no kb owns the folder this file is in — add it to a KB's "
                           f"repos in config/kb-map.json (kbs: {known})")
    b = bmap[kb_name]
    if not b.get("write"):
        return "refused", f"kb '{kb_name}' is read-only by policy"
    doors = cfg("doors.json")
    if door not in doors:
        return "refused", f"unknown door '{door}' — refusing to write anywhere"
    if b.get("privacy") not in (doors[door].get("classes") or []):
        return "refused", (f"kb '{kb_name}' is class '{b.get('privacy')}', which "
                           f"the '{door}' door may not write to")

    leaks = redact.find(text)
    if leaks:
        return "refused", (f"document contains what looks like a secret "
                           f"({', '.join(leaks)}) — refusing to store it")

    chosen = ontology_for(doc_type, b.get("privacy"), b.get("ontology", ""))
    ontology = None if chosen == b.get("ontology", "") else chosen
    filename = os.path.basename(path)
    if not filename.endswith((".md", ".txt")):
        filename += ".md"
    try:
        job = kb.ingest(kb_name, filename, text, {
            "source": f"ethan-{door}", "doc_type": doc_type,
            "chat_id": str(chat_id), "path": path,
        }, ontology=ontology)
    except Exception as e:
        return "failed", f"write to '{kb_name}' failed: {e}"

    info = {"kb": kb_name, "tenant": b.get("tenant_code", ""),
            "ontology": ontology or b.get("ontology", ""), "filename": filename,
            "job_id": job.get("job_id")}
    store.add_harvest(chat_id, "cli", kb_name, filename, f"direct ingest ({doc_type})", "written")
    log(f"ingest: {filename} -> {kb_name} ({info['ontology']}) job {info['job_id']}")
    return "written", info


def wait_job(kb_name, job_id, reply, tries=40):
    """Poll one ingest job and report the outcome through the door."""
    import time
    if str(job_id).startswith("local:"):         # a folder KB writes at once; no job to poll
        reply(f"ingest done: {job_id[len('local:'):]} written to {kb_name}")
        return
    for _ in range(tries):
        time.sleep(6)
        try:
            st = kb._rpc(kb_name, "kb.jobs.status", {"job_id": job_id})
        except Exception as e:
            reply(f"ingest status check failed: {e}"); return
        if st.get("status") in ("COMPLETED", "COMPLETED_WITH_ERRORS", "ERROR"):
            try:
                out = kb._rpc(kb_name, "kb.jobs.output", {"job_id": job_id})
            except Exception:
                out = st
            o = out.get("output", out)
            reply(f"ingest {out.get('status', st.get('status'))}: "
                  f"document {o.get('document_id', '?')} — {o.get('chunks', '?')} chunks, "
                  f"{o.get('entities', '?')} entities, {o.get('relations', '?')} relations"
                  + (" (duplicate — already in the kb)" if o.get("was_duplicate") else ""))
            return
    reply(f"ingest job {job_id} still running after {tries * 6}s — check it later")
