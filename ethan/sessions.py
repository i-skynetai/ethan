"""Turn Claude Code session transcripts into something a kb can hold.

A transcript is mostly exhaust: tool calls, tool results, dumped file contents.
Ingesting it raw would bury the kb in its own noise. So: distil locally with
plain Python, let a hand write the session card, ingest the card — never the
transcript.

Sub-agent transcripts under <session>/subagents/ are skipped: they are
intermediate work already folded into their parent session.
"""
import json, os, re
from . import redact

PROJECTS = os.path.expanduser("~/.claude/projects")

# Turns that carry no knowledge, only plumbing.
_NOISE = re.compile(
    r"<(system-reminder|command-name|command-message|command-args|local-command-"
    r"stdout|local-command-caveat)\b", re.I)


def _text_of(content):
    """A message's content is either a string or a list of typed blocks. Keep
    human/assistant prose; drop tool_use and tool_result blocks entirely."""
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""
    out = []
    for b in content:
        if not isinstance(b, dict):
            continue
        if b.get("type") == "text" and b.get("text"):
            out.append(b["text"])
    return "\n".join(out)


def distil(path, max_chars=14000):
    """Read one transcript; return metadata plus the human/assistant prose."""
    turns, meta = [], {}
    with open(path, errors="replace") as f:
        for line in f:
            try:
                o = json.loads(line)
            except Exception:
                continue
            t = o.get("type")
            if t not in ("user", "assistant"):
                continue
            if o.get("isSidechain"):              # sub-agent chatter
                continue
            if not meta:
                meta = {"cwd": o.get("cwd", ""), "branch": o.get("gitBranch", ""),
                        "session": o.get("sessionId", ""), "started": o.get("timestamp", "")}
            meta["ended"] = o.get("timestamp", meta.get("ended", ""))
            body = _text_of((o.get("message") or {}).get("content"))
            body = body.strip()
            if not body or _NOISE.search(body):
                continue
            turns.append((t, body))

    # Keep the whole ask side, and trim assistant prose — the asks are what make a
    # session legible, the assistant text is where the volume is.
    parts = []
    for role, body in turns:
        parts.append(f"[{'YOU' if role == 'user' else 'CLAUDE'}] "
                     + (body if role == "user" else body[:2500]))
    text = "\n\n".join(parts)
    # Scrub BEFORE truncating and before any hand sees it. Past sessions were
    # sometimes about configuring credentials, so transcripts contain live ones.
    text, secrets = redact.scrub(text)
    if len(text) > max_chars:                     # keep the two ends, drop the middle
        head, tail = int(max_chars * 0.45), int(max_chars * 0.45)
        text = text[:head] + "\n\n[... middle of session omitted ...]\n\n" + text[-tail:]
    meta["turns"] = len(turns)
    meta["chars"] = len(text)
    meta["secrets_redacted"] = secrets
    return meta, text


def sessions_for(project_dir):
    """Top-level transcripts only — subagents/ is deliberately excluded."""
    d = os.path.join(PROJECTS, project_dir)
    if not os.path.isdir(d):
        return []
    return sorted(os.path.join(d, f) for f in os.listdir(d) if f.endswith(".jsonl"))


def all_projects():
    if not os.path.isdir(PROJECTS):
        return []
    return sorted(p for p in os.listdir(PROJECTS)
                  if os.path.isdir(os.path.join(PROJECTS, p)))


def route(cwd, kb_map):
    """Map a transcript's working directory to a kb via the kb map's repo."""
    if not cwd:
        return None
    cwd = os.path.realpath(os.path.expanduser(cwd))
    best, best_len = None, -1
    for name, b in kb_map.items():
        # "repo" is where a hand runs; "repos" widens routing to sibling projects
        # that belong to the same kb (e.g. a POC beside the main checkout).
        for repo in [b.get("repo")] + list(b.get("repos") or []):
            if not repo:
                continue
            repo = os.path.realpath(os.path.expanduser(repo))
            # longest matching prefix wins, so a nested repo beats its parent
            if (cwd == repo or cwd.startswith(repo + os.sep)) and len(repo) > best_len:
                best, best_len = name, len(repo)
    return best


CARD_PROMPT = """Below is a distilled record of one past working session: the
human's asks and the assistant's replies, with all tool calls and file dumps
stripped out.

Write a SESSION CARD for a long-term knowledge base. Someone will read this card
months from now with no other context.

Session metadata:
- working directory: {cwd}
- git branch: {branch}
- started: {started}
- turns kept: {turns}

--- SESSION ---
{body}
--- END SESSION ---

FIRST, on a line of its own, pick where this card belongs:

KB: <one of the names below, or NONE>

{kb_table}

Judge by what the session is actually ABOUT, not by the working directory. The
directory is often misleading — someone may run a tool from one project's folder
while working on a different project entirely. If the session's subject matter
does not clearly belong to one of these, answer KB: NONE.
Never file work about one project into another project's knowledge base.

THEN the card itself, as markdown, with exactly these sections, omitting any that
would be empty:

# <short title naming what this session was about>

Session: <the same title, repeated on this line verbatim>
Agent: {agent}
Project: <the canonical project or repo name this work belongs to>

**Asked:** what the human actually wanted, in one or two sentences.

**Decided:** decisions reached and the reason for each. This is the most valuable
section — be specific.

**Changed:** concrete changes made (files, commands, configuration, data). Include
paths and identifiers.

**Learned:** non-obvious facts established, gotchas, corrections of wrong beliefs,
measurements. Include numbers and file references.

**Open:** anything left unresolved, deferred, or explicitly parked.

Rules:
- Only what the session actually establishes. Do not infer or embellish.
- If something was assumed rather than verified, say so.
- Keep identifiers exactly as written: ticket ids, file paths, tenant codes, names.
- Some values appear as [REDACTED-...]. That is deliberate — they were secrets.
  Never guess at or reconstruct them, and do not copy any credential-looking
  string into the card.
- No preamble, no "in this session". Start with KB:, then the heading.
- The Session:, Agent: and Project: lines are required and must be plain lines,
  not bold. The knowledge base reads them to name the session, and it only ever
  sees one slice of the card at a time — so repeat the title on the Session:
  line even though it duplicates the heading.
- If the session achieved nothing worth recording, reply with exactly: SKIP
"""


def parse_card(out):
    """Split the hand's reply into (kb_or_None, card_markdown, error)."""
    out = (out or "").strip()
    if out.startswith("```"):                     # unwrap a fence if it wrapped everything
        out = out.split("\n", 1)[-1]
        if out.rstrip().endswith("```"):
            out = out.rstrip()[:-3].rstrip()
    if out.upper().startswith("SKIP"):
        return None, None, "hand judged the session not worth recording"
    m = re.search(r"^\s*(?:KB|BRAIN):\s*([A-Za-z0-9_\-]+)\s*$", out, re.M)
    if not m:
        return None, None, "hand did not state a KB: line"
    kb = m.group(1)
    card = (out[:m.start()] + out[m.end():]).strip()
    if kb.upper() == "NONE":
        return None, card, "hand judged it belongs to no available kb"
    if len(card) < 200:
        return None, card, f"card too short ({len(card)} chars)"
    return kb, card, None
