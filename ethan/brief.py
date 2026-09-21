"""Task brief — what a hand receives. Never a bare prompt."""


def render(task, context_hits, repo, done_when=None, must_not=None, prior_output=None):
    lines = [f"# Task\n{task}\n"]
    if prior_output:
        lines.append("# Output of the previous step (review/build on top of this)\n"
                     + prior_output[:12000] + "\n")
    if context_hits:
        lines.append("# Context (cited — from the team knowledge base; verify against the repo)")
        for h in context_hits:
            lines.append(f"- [{h['source']} · {h['doc_id']}] {h['text'][:300]}")
        lines.append("")
    if repo:
        lines.append(f"# Repo\nWork in this directory: {repo}\n")
    lines.append("# Done when\n" + "\n".join(f"- {d}" for d in (done_when or
                  ["the ask is fully addressed", "you clearly report what you did and did not do"])))
    lines.append("\n# Must not\n" + "\n".join(f"- {m}" for m in (must_not or
                  ["push to any remote", "delete files outside the repo", "ingest anything anywhere"])))
    return "\n".join(lines)
