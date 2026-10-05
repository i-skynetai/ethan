"""The router — hint first, model only when the hint cannot decide; pick kb, pull context, brief, delegate, report."""
import re
from . import kb, brief, clock, hands, harvest, identity, llm, policy, relay, status, store, todo, watch
from .util import log
from .character import VOICE

ROUTE_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "properties": {
        "kind": {"type": "string", "enum": ["question", "build", "review", "chain", "followup", "status", "updates", "chat"]},
        "kb": {"type": "string"},
        "hand": {"type": "string", "enum": ["claude", "codex", "kimi", "auto", "none"]},
        "steps": {"type": "array", "items": {"type": "object", "additionalProperties": False,
            "properties": {"hand": {"type": "string", "enum": ["claude", "codex", "kimi"]},
                            "kind": {"type": "string", "enum": ["build", "review"]},
                            "goal": {"type": "string"}},
            "required": ["hand", "kind", "goal"]}},
        "search_query": {"type": "string"},
        "reason": {"type": "string"},
    },
    "required": ["kind", "kb", "hand", "steps", "search_query", "reason"],
}


def _hint_kbs(text):
    """Every KB whose hint appears in the ask, in map order. Case does not matter:
    a hint written `PROJ-` matches `proj-412` and `PROJ-412` alike."""
    low = text.lower()
    return [name for name, b in kb.kb_map().items()
            if any(h.lower() in low for h in b.get("hints", []) if h)]


#: The first word of an ask, when it names the work outright. Anything else —
#: a question, a chain, an ask that names two hands — is left to the model.
_KIND_FOR_VERB = {
    "review": "review", "audit": "review",
    "fix": "build", "implement": "build", "build": "build", "add": "build",
    "refactor": "build", "write": "build", "update": "build", "change": "build",
}


def _hint_kind(text):
    """The kind, when the keyword rule can tell it for certain. None otherwise."""
    low = text.lower()
    if len(set(re.findall(r"\b(claude|codex|kimi)\b", low))) > 1 or re.search(r"\bthen\b", low):
        return None                              # sounds like a chain: the model decides
    first = re.match(r"\s*([a-z]+)", low)
    return _KIND_FOR_VERB.get(first.group(1)) if first else None


def _hint_hand(text):
    m = re.search(r"\b(use|with)\s+(claude|codex|kimi)\b", text.lower())
    return m.group(2) if m else None


def _close_out(hand, output, repo, door, chat_id, reply, task_id=None, kb_name=None):
    """Hand decides what to keep; Ethan enforces policy and reports the outcome."""
    if kb_name is None:                         # nothing is filed under a KB nobody chose
        status, msg = "nothing", "no knowledge base was chosen for this ask"
    else:
        status, msg = harvest.run(hand, output, repo, door, chat_id, task_id)
    if status == "written":
        reply(f"Kept: {msg}")
    elif status == "off":
        pass                                    # harvest disabled in config, stay quiet
    else:                                       # nothing / refused / failed / unparsed
        reply(f"Nothing kept — {msg}")          # always say so, so silence never means "did it run?"
    ok, why = harvest.can_close(chat_id)
    reply(f"Session can close — {why}." if ok else f"Not closing — {why}.")


def _model_route(text, bmap, choices, has_prior):
    """The routing call. It sees the KB purposes, the ask and one yes/no — nothing else.

    No conversation history and no earlier hand output: the router is the component
    most exposed to arbitrary text, so it is the one that is told the least. When
    hints matched more than one KB, only those KBs are offered.
    """
    offered = {n: bmap[n] for n in choices} if len(choices) > 1 else bmap
    summary = "\n".join(f"- {n}: {b['purpose']} (privacy: {b['privacy']})" for n, b in offered.items())
    prior = "yes" if has_prior else "no"
    return llm.ask(
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
          "and its kind (build if the step changes files, review if it only reads) "
          "(each later step builds on the previous step's output); empty list otherwise. "
          "hand: only if the user names exactly one, else 'auto' for build/review, 'none' otherwise. "
          "search_query: the best short knowledge-base query for this ask. "
          "If no kb fits, answer with kb 'none'.\n\n"
          f"An earlier result exists in this conversation: {prior}.\n\nKBs:\n" + summary},
         {"role": "user", "content": text}],
        json_schema=ROUTE_SCHEMA)


CLOSE_OUT = ("Session can close", "Not closing")


def handle(chat_id, text, reply, door="telegram-private", cwd=None):
    """Process one ask. reply(str) sends back through the originating door.

    cwd, when given, is where the CALLER is working. It wins over the kb's
    repo as the hand's working directory, so asking from a project Ethan does
    not know still puts the hand in the right checkout.

    Every ask ends with exactly one close-out line, whatever happened — an answer,
    a failed task, an error. `bin/ethan` waits for that line, and a door that never
    gets one leaves the person wondering whether anything ran.
    """
    closed = []
    def send(msg):
        if msg.startswith(CLOSE_OUT):
            if closed:
                return
            closed.append(msg)
        reply(msg)
    try:
        _handle(chat_id, text, send, door, cwd)
    except Exception as e:                      # a bad ask must still be answered
        log(f"ask failed: {type(e).__name__}: {e}")
        send(f"error: {e}")
    if not closed:
        ok, why = harvest.can_close(chat_id)
        send(f"Session can close — {why}." if ok else f"Not closing — {why}.")


def _handle(chat_id, text, reply, door, cwd):
    history = store.recent(chat_id)              # read before this ask is stored
    store.remember(chat_id, "user", text)        # stored once, whatever the door
    # Passing an ask to a session that is already running is decided before any
    # routing: it must never fall through to a build, which would start a new one.
    if relay.take(chat_id, text, reply, door, cwd):
        return
    if watch.take(chat_id, text, reply, door):   # "watch mail through … every weekday at …: …"
        return                                   # before the clock, which would hear only "every … at"
    if clock.take(chat_id, text, reply, door):   # "remind me …", "every weekday at …"
        return
    if todo.take(chat_id, text, reply, door):    # "add task: …", "my tasks", "done #3"
        return
    bmap = kb.kb_map()
    hinted, hinted_hand = _hint_kbs(text), _hint_hand(text)
    hinted_kind = _hint_kind(text)

    if len(hinted) == 1 and hinted_kind:
        # A hint names the KB and the first word names the work: no model call.
        route = {"kind": hinted_kind, "kb": hinted[0], "hand": hinted_hand or "auto",
                 "steps": [], "search_query": text, "reason": "hint", "by": "hint"}
    else:
        route = _model_route(text, bmap, hinted, bool(store.last_result(chat_id)))
        route["by"] = "model"
        if len(hinted) == 1:
            route["kb"] = hinted[0]              # the kind was unclear; the KB was not
    if hinted_hand:
        route["hand"] = hinted_hand
    log(f"route: {route}")

    kind = route["kind"]
    if kind in ("build", "review", "chain") and not policy.may_build(door):
        # Starting a hand needs a person at a door the policy trusts with it. The clock
        # may remind and read; it may not build.
        reply(f"Not started: the {door} door may only remind and read, not start a {kind}. "
              f"Ask for it yourself from the console or the command line when you want it run.")
        return
    choices = hinted if len(hinted) > 1 else list(bmap)
    kb_name = route["kb"] if route["kb"] in choices else None
    b = bmap[kb_name] if kb_name else {}

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

    if kind == "status":                        # from the ledger, no second model call
        reply(status.text())
        return
    if kind == "updates":
        reply("I do not read mail or notifications yet. That comes through a session's own "
              "connectors (roadmap EH-063). I can tell you what is running and what is pending.")
        return
    if kind == "chat":
        out = llm.ask([{"role": "system", "content": VOICE},
                       *history, {"role": "user", "content": text}])
        store.remember(chat_id, "assistant", out)
        reply(out)
        return

    # the caller's directory beats the kb default; kbs stay for context only
    workdir = cwd or b.get("repo")
    where = f" · in {workdir}" if cwd else ""
    hits = []
    if kb_name is None:
        # Never a default KB: answering from the wrong one is worse than from none.
        reply(f"No knowledge base matched this ask — going on without one{where}.")
    else:
        reply(f"On it — {kind} · kb: {kb_name}{where}.")
        try:
            hits = kb.search(kb_name, route["search_query"], k=5)
        except Exception as e:
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
        prior, task_id = None, None
        for i, step in enumerate(route["steps"], 1):
            h, goal = step["hand"], step["goal"]
            task_id = store.add_task(chat_id, f"chain:{i}", kb_name, h, goal, door)
            short = goal.split(".")[0][:150]
            reply(f"Step {i}/{len(route['steps'])} — {h}: {short}…")
            btxt = brief.render(f"{goal}\n\n(Original ask: {text})", hits, workdir,
                                prior_output=prior, sender=identity.stamp(door))
            step_kind = step.get("kind") or "review"   # unknown → the role that cannot edit
            res = hands.run(h, btxt, workdir, review=(step_kind == "review"),
                            task_id=task_id, kb=kb_name, kind=step_kind)
            store.finish_task(task_id, "done" if res["ok"] else "failed", res["out"])
            if not res["ok"]:
                reply(f"Step {i} FAILED ({h}): {res['out'][-1500:]}")
                return
            prior = res["out"]
            reply(f"Step {i} done ({h}).")
        store.remember(chat_id, "assistant", prior[:1500])
        reply(f"Chain complete:\n{prior[-3000:]}")
        # the last hand in the chain saw the most context, so it does the close-out
        _close_out(route["steps"][-1]["hand"], prior, workdir, door, chat_id, reply,
                   task_id, kb_name)
        return

    # build / review → delegate to a hand
    hand = route["hand"] if route["hand"] not in ("auto", "none") else ("codex" if kind == "review" else "claude")
    task_id = store.add_task(chat_id, kind, kb_name, hand, text, door)
    reply(f"Task #{task_id}: delegating to {hand} in {workdir or '(no repo)'} — I'll report back.")
    btxt = brief.render(text, hits, workdir, sender=identity.stamp(door))
    res = hands.run(hand, btxt, workdir, review=(kind == "review"), task_id=task_id,
                    kb=kb_name, kind=kind)
    store.finish_task(task_id, "done" if res["ok"] else "failed", res["out"])
    store.remember(chat_id, "assistant", res["out"][:1500])
    reply(f"Task #{task_id} {'done' if res['ok'] else 'FAILED'} ({hand}):\n{res['out'][-3000:]}")
    if res["ok"]:                                # failed work has nothing to harvest
        _close_out(hand, res["out"], workdir, door, chat_id, reply, task_id, kb_name)
