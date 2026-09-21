#!/usr/bin/env python3
"""Backfill past Claude Code sessions into the kbs, as cards.

  python3 tools/backfill_sessions.py --plan              # show what would happen
  python3 tools/backfill_sessions.py --run --limit 3     # do a few
  python3 tools/backfill_sessions.py --run               # do all routable ones

Distil locally, let a hand write the card, Ethan ingests it. Never the transcript.
Already-done sessions are skipped via a ledger, so re-running is safe.
"""
import argparse, json, os, sys, time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from ethan.util import load_env, log, ROOT, cfg          # noqa: E402
from ethan import kb, hands, redact, sessions        # noqa: E402

LEDGER = os.path.join(ROOT, "state", "backfill.json")
DOOR = "backfill"


def ledger():
    if os.path.exists(LEDGER):
        try:
            with open(LEDGER) as fh:
                return json.load(fh)
        except Exception:
            pass
    return {}


def save(led):
    os.makedirs(os.path.dirname(LEDGER), exist_ok=True)
    tmp = LEDGER + ".tmp"
    with open(tmp, "w") as f:
        json.dump(led, f, indent=1)
    os.replace(tmp, LEDGER)                    # atomic: a crash never truncates it


def plan():
    """Every top-level session, with its destination KB (or why not)."""
    bmap = kb.kb_map()
    doors = cfg("doors.json")
    allowed = set((doors.get(DOOR) or {}).get("classes") or [])
    rows = []
    for proj in sessions.all_projects():
        for path in sessions.sessions_for(proj):
            meta, _ = sessions.distil(path, max_chars=400)
            kb_name = sessions.route(meta.get("cwd"), bmap)
            why = None
            if kb_name is None:
                why = "no kb owns this directory"
            elif not bmap[kb_name].get("write"):
                why = f"kb '{kb_name}' is read-only"
            elif bmap[kb_name].get("privacy") not in allowed:
                why = f"kb '{kb_name}' class not allowed for the backfill door"
            elif meta.get("turns", 0) < 4:
                why = f"only {meta.get('turns', 0)} substantive turns"
            rows.append({"path": path, "kb": kb_name, "skip": why,
                         "cwd": meta.get("cwd", ""), "turns": meta.get("turns", 0),
                         "branch": meta.get("branch", "")})
    return rows


def kb_table():
    rows = []
    for name, b in kb.kb_map().items():
        if not b.get("write"):
            continue                            # cannot be a destination anyway
        rows.append(f"- {name}: {b.get('purpose','')}")
    return "\n".join(rows) + "\n- NONE: belongs to none of these"


def card_for(meta, body, hand, repo):
    """Returns (kb, card, error). The HAND picks the kb, not the directory."""
    prompt = sessions.CARD_PROMPT.format(
        cwd=meta.get("cwd", "?"), branch=meta.get("branch") or "-",
        started=meta.get("started", "?"), turns=meta.get("turns", 0),
        body=body, kb_table=kb_table(),
        agent="Claude Code")     # these transcripts are Claude Code sessions
    res = hands.run(hand, prompt, repo)
    out = (res.get("out") or "").strip()
    if not res.get("ok") or not out:
        return None, None, f"hand {hand} failed: {out[:200]}"
    return sessions.parse_card(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--plan", action="store_true")
    ap.add_argument("--run", action="store_true")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--kb", help="only this KB")
    ap.add_argument("--hand", default="claude")
    a = ap.parse_args()
    load_env()

    rows = plan()
    todo = [r for r in rows if not r["skip"]]
    led = ledger()

    if a.plan or not a.run:
        by = {}
        for r in rows:
            key = r["kb"] if not r["skip"] else f"SKIP: {r['skip']}"
            by.setdefault(key, []).append(r)
        print(f"{len(rows)} top-level sessions\n")
        for key in sorted(by, key=lambda k: (k.startswith("SKIP"), k)):
            done = sum(1 for r in by[key] if r["path"] in led)
            print(f"  {len(by[key]):3}  {key}" + (f"   ({done} already done)" if done else ""))
        print(f"\n{len(todo)} routable, {sum(1 for r in todo if r['path'] in led)} already ingested")
        print("\nRun with --run to ingest. --limit N to do a few first.")
        return

    if a.kb:
        todo = [r for r in todo if r["kb"] == a.kb]
    todo = [r for r in todo if r["path"] not in led]
    if a.limit:
        todo = todo[:a.limit]
    if not todo:
        print("nothing to do"); return

    print(f"ingesting {len(todo)} session card(s) with hand={a.hand}\n")
    ok = fail = 0
    bmap = kb.kb_map()
    doors = cfg("doors.json")
    allowed = set((doors.get(DOOR) or {}).get("classes") or [])
    moved = 0
    for i, r in enumerate(todo, 1):
        name = os.path.basename(r["path"])[:8]
        meta, body = sessions.distil(r["path"])
        red = f" redacted={','.join(meta['secrets_redacted'])}" if meta.get("secrets_redacted") else ""
        print(f"[{i}/{len(todo)}] {name} cwd->{r['kb']} "
              f"({meta['turns']} turns, {meta['chars'] // 1024}KB{red}) ", end="", flush=True)
        repo = bmap[r["kb"]].get("repo")
        kb_name, card, err = card_for(meta, body, a.hand, repo)
        if err or not kb_name:
            print(f"SKIP — {err}")
            led[r["path"]] = {"state": "skipped", "why": err, "ts": time.time()}
            save(led); continue

        # The hand's choice wins over the directory, but Ethan still validates it.
        if kb_name not in bmap:
            print(f"SKIP — hand chose unknown kb '{kb_name}'")
            led[r["path"]] = {"state": "skipped", "why": f"unknown kb {kb_name}", "ts": time.time()}
            save(led); continue
        if not bmap[kb_name].get("write") or bmap[kb_name].get("privacy") not in allowed:
            print(f"SKIP — kb '{kb_name}' not writable through the {DOOR} door")
            led[r["path"]] = {"state": "refused", "why": f"policy: {kb_name}", "ts": time.time()}
            save(led); continue
        if kb_name != r["kb"]:
            moved += 1
            print(f"[hand says {kb_name}] ", end="", flush=True)

        leaks = redact.find(card)                # hard gate, even post-scrub
        if leaks:
            print(f"REFUSED — card still contains {', '.join(leaks)}")
            led[r["path"]] = {"state": "refused", "why": f"secret in card: {leaks}",
                              "ts": time.time()}
            save(led); fail += 1; continue

        fn = f"session-{meta.get('started','')[:10]}-{name}.md"
        try:
            job = kb.ingest(kb_name, fn, card, {
                "source": "claude-session", "doc_type": "session_card",
                "session_id": meta.get("session", ""), "cwd": meta.get("cwd", ""),
                "branch": meta.get("branch", ""), "started": meta.get("started", ""),
                "turns": meta.get("turns", 0), "routed_by": "hand",
            }, ontology="agent_context")
            print(f"OK job={job.get('job_id','?')[:8]} card={len(card)}B")
            led[r["path"]] = {"state": "ingested", "kb": kb_name, "file": fn,
                              "job": job.get("job_id"), "ts": time.time()}
            ok += 1
        except Exception as e:
            print(f"FAILED — {e}")
            led[r["path"]] = {"state": "failed", "why": str(e)[:300], "ts": time.time()}
            fail += 1
        save(led)
    print(f"\ndone: {ok} ingested, {fail} failed"
          + (f", {moved} re-routed by the hand away from the cwd guess" if moved else ""))


if __name__ == "__main__":
    main()
