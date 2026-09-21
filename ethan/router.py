"""The router — classify (hint first), pick kb, pull context, brief, delegate, report."""
import json, re
from . import kb, brief, hands, harvest, llm, store
from .util import log

ROUTE_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "properties": {
        "kind": {"type": "string", "enum": ["question", "build", "review", "chain", "followup", "status", "updates", "chat"]},
        "kb": {"type": "string"},
        "hand": {"type": "string", "enum": ["claude", "codex", "kimi", "auto", "none"]},
        "steps": {"type": "array", "items": {"type": "object", "additionalProperties": False,
            "properties": {"hand": {"type": "string", "enum": ["claude", "codex", "kimi"]},
                            "goal": {"type": "string"}},
            "required": ["hand", "goal"]}},
        "search_query": {"type": "string"},
        "reason": {"type": "string"},
    },
    "required": ["kind", "kb", "hand", "steps", "search_query", "reason"],
}


def _hint_route(text):
    """A hint in the ask pins the kb directly — no LLM needed."""
    low = text.lower()
    for name, b in kb.kb_map().items():
        if any(h in low for h in b.get("hints", [])):
            return name
    return None


def _hint_hand(text):
    m = re.search(r"\b(use|with)\s+(claude|codex|kimi)\b", text.lower())
    return m.group(2) if m else None


def _close_out(hand, output, repo, door, chat_id, reply, task_id=None):
    """Hand decides what to keep; Ethan enforces policy and reports the outcome."""
    status, msg = harvest.run(hand, output, repo, door, chat_id, task_id)
    if status == "written":
        reply(f"Kept: {msg}")
    elif status == "off":
        pass                                    # harvest disabled in config, stay quiet
    else:                                       # nothing / refused / failed / unparsed
        reply(f"Nothing kept — {msg}")          # always say so, so silence never means "did it run?"
    ok, why = harvest.can_close(chat_id)
    reply(f"Session can close — {why}." if ok else f"Not closing — {why}.")


def handle(chat_id, text, reply, door="telegram-private", cwd=None):
    """Process one ask. reply(str) sends back through the originating door.

    cwd, when given, is where the CALLER is working. It wins over the kb's
    repo as the hand's working directory, so asking from a project Ethan does
    not know still puts the hand in the right checkout.
    """
    store.remember(chat_id, "user", text)
    bmap = kb.kb_map()
    hinted_kb, hinted_hand = _hint_route(text), _hint_hand(text)

    summary = "\n".join(f"- {n}: {b['purpose']} (privacy: {b['privacy']})" for n, b in bmap.items())
    route = llm.ask(
        [{"role": "system", "content":
          "You are Ethan's router. Classify the user's ask and pick ONE kb from the list. "
          "kind: question=answer from knowledge, build=code/doc work in a repo, review=review code/MR, "
          "chain=the ask names MULTIPLE agents or asks to do-something-then-review/verify it "
          "(e.g. 'check with claude and ask codex to review') — even if phrased as a question, "
          "followup=the ask refers to what was JUST produced and needs no new work "
          "('summarise this', 'explain that', 'shorter please', 'what did it say about X', "
          "'expand point 2') — NEVER re-run agents for these, "
          "status=progress of tasks, updates=recent mail/notifications, chat=small talk/none of these. "
          "steps: ONLY for chain — the ordered plan, one entry per hand with a concrete goal "
          "(each later step builds on the previous step's output); empty list otherwise. "
          "hand: only if the user names exactly one, else 'auto' for build/review, 'none' otherwise. "
          "search_query: the best short knowledge-base query for this ask.\n\nKBs:\n" + summary},
         *store.recent(chat_id), {"role": "user", "content": text}],
        json_schema=ROUTE_SCHEMA)
    if hinted_kb:
        route["kb"] = hinted_kb
    if hinted_hand:
        route["hand"] = hinted_hand
    if route["kb"] not in bmap:
        route["kb"] = next(iter(bmap))
    log(f"route: {route}")

    kind, kb_name = route["kind"], route["kb"]
    b = bmap[kb_name]

    if kind == "followup":
        prior = store.last_result(chat_id)
        if not prior:
            reply("Nothing finished yet to follow up on — ask me something first.")
            return
        out = llm.ask([{"role": "system", "content":
                        "The user is following up on the result below. Answer their request about it "
                        "directly — summarise, shorten, expand or extract as asked. Keep concrete "
                        "details (numbers, file paths, names). Do not invent anything not present."},
                       {"role": "user", "content": f"Previous result:\n{prior[:14000]}\n\nFollow-up: {text}"}])
        store.remember(chat_id, "assistant", out)
        reply(out)
        return

    if kind in ("status", "updates"):
        reply("Status and inbox updates land in v0.2 — today I can answer questions and run build/review tasks.")
        return
    if kind == "chat":
        out = llm.ask([{"role": "system", "content": "You are Ethan, a concise personal agent."},
                       *store.recent(chat_id), {"role": "user", "content": text}])
        store.remember(chat_id, "assistant", out)
        reply(out)
        return

    # the caller's directory beats the kb default; kbs stay for context only
    workdir = cwd or b.get("repo")
    where = f" · in {workdir}" if cwd else ""
    reply(f"On it — {kind} · kb: {kb_name}{where}.")
    try:
        hits = kb.search(kb_name, route["search_query"], k=5)
    except Exception as e:
        hits = []
        reply(f"(kb unreachable: {e} — continuing without context)")

    if kind == "question":
        cites = "\n".join(f"- [{h['source']}] {h['text'][:400]}" for h in hits) or "(no hits)"
        out = llm.ask([{"role": "system", "content":
                        "Answer using ONLY the cited context below. Every claim must reference a [source]. "
                        "If the context does not answer it, say what is missing.\n\nContext:\n" + cites},
                       {"role": "user", "content": text}])
        store.remember(chat_id, "assistant", out)
        reply(out)
        return

    if kind == "chain" and route.get("steps"):
        prior = None
        for i, step in enumerate(route["steps"], 1):
            h, goal = step["hand"], step["goal"]
            task_id = store.add_task(chat_id, f"chain:{i}", kb_name, h, goal)
            short = goal.split(".")[0][:150]
            reply(f"Step {i}/{len(route['steps'])} — {h}: {short}…")
            btxt = brief.render(f"{goal}\n\n(Original ask: {text})", hits, workdir,
                                prior_output=prior)
            res = hands.run(h, btxt, workdir, review=("review" in goal.lower()),
                            task_id=task_id, kb=kb_name)
            store.finish_task(task_id, "done" if res["ok"] else "failed", res["out"])
            if not res["ok"]:
                reply(f"Step {i} FAILED ({h}): {res['out'][-1500:]}")
                return
            prior = res["out"]
            reply(f"Step {i} done ({h}).")
        store.remember(chat_id, "assistant", prior[:1500])
        reply(f"Chain complete:\n{prior[-3000:]}")
        # the last hand in the chain saw the most context, so it does the close-out
        _close_out(route["steps"][-1]["hand"], prior, workdir, door, chat_id, reply)
        return

    # build / review → delegate to a hand
    hand = route["hand"] if route["hand"] not in ("auto", "none") else ("codex" if kind == "review" else "claude")
    task_id = store.add_task(chat_id, kind, kb_name, hand, text)
    reply(f"Task #{task_id}: delegating to {hand} in {workdir or '(no repo)'} — I'll report back.")
    btxt = brief.render(text, hits, workdir)
    res = hands.run(hand, btxt, workdir, review=(kind == "review"), task_id=task_id,
                    kb=kb_name, kind=kind)
    store.finish_task(task_id, "done" if res["ok"] else "failed", res["out"])
    store.remember(chat_id, "assistant", res["out"][:1500])
    reply(f"Task #{task_id} {'done' if res['ok'] else 'FAILED'} ({hand}):\n{res['out'][-3000:]}")
    if res["ok"]:                                # failed work has nothing to harvest
        _close_out(hand, res["out"], workdir, door, chat_id, reply, task_id)
