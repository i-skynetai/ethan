"""Secret scrubbing for anything on its way into a KB.

Found the hard way: session transcripts contain live credentials, because past
sessions were *about* configuring credentials. 15 of 68 transcripts carried at
least one. A KB is long-lived and searchable, so a secret written there is
worse than one in a terminal scrollback.

Two uses, and both matter:
  scrub()  — before a hand ever sees the text, so it cannot copy a secret forward
  find()   — a hard gate immediately before ingest, in case one got through
"""
import re

PATTERNS = [
    ("kb-pat",        re.compile(r"kb_pat_[A-Za-z0-9_\-]{16,}")),
    ("openai-key",      re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9_\-]{20,}")),
    ("anthropic-key",   re.compile(r"\bsk-ant-[A-Za-z0-9_\-]{20,}")),
    ("google-key",      re.compile(r"\bAIza[0-9A-Za-z_\-]{30,}")),
    ("gitlab-pat",      re.compile(r"\bglpat-[A-Za-z0-9_\-]{16,}")),
    ("github-pat",      re.compile(r"\b(?:ghp_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{20,})")),
    ("atlassian-token", re.compile(r"\bATATT[A-Za-z0-9_\-=]{20,}")),
    ("telegram-token",  re.compile(r"\b\d{8,10}:[A-Za-z0-9_\-]{30,}")),
    ("jwt",             re.compile(r"\beyJ[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,}")),
    ("private-key",     re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----")),
    ("bearer",          re.compile(r"(?i)\bbearer\s+[A-Za-z0-9_\-\.=]{16,}")),
    # last resort: an assignment whose name says secret. Deliberately broad; a
    # false positive costs a redacted string, a false negative costs a leak.
    ("named-secret",    re.compile(r"(?i)\b(pass(?:word|wd)?|secret|api[_\-]?key|auth[_\-]?token|"
                                   r"access[_\-]?token|client[_\-]?secret)\b\s*[:=]\s*"
                                   r"['\"]?([A-Za-z0-9_\-/+\.]{12,})")),
]


def scrub(text):
    """Replace every secret with a labelled placeholder. Returns (text, kinds)."""
    if not text:
        return text, []
    kinds = []
    for label, rx in PATTERNS:
        if label == "named-secret":
            def _named(m):
                kinds.append(label)
                return f"{m.group(1)}=[REDACTED-{label}]"
            text = rx.sub(_named, text)
        else:
            def _repl(m, _l=label):
                kinds.append(_l)
                return f"[REDACTED-{_l}]"
            text = rx.sub(_repl, text)
    return text, sorted(set(kinds))


def find(text):
    """What secrets are still present? Empty list means safe to store."""
    if not text:
        return []
    out = []
    for label, rx in PATTERNS:
        if rx.search(text):
            out.append(label)
    return out
