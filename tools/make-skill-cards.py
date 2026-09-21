"""Write one knowledge-base card per plugin skill.

The raw SKILL.md files are operating instructions, not knowledge: 5-8 KB each,
and CHUNK_SIZE is 2000, so the extractor sees most chunks with no skill name in
them and invents a title. One 8.5 KB file became four Skill nodes that way.

So each skill gets a card instead: a single chunk, under 2000 characters, that
leads with a "Skill:" header line the ontology keys off. Everything a future
agent needs to decide whether to open the real SKILL.md — when it applies, what
it takes, its steps, its guardrails, the tools it calls.

Regenerate after changing a skill, then re-ingest under `agent_context`.
"""
import os
D = os.path.expanduser(os.environ.get("ETHAN_SKILL_CARDS_DIR", "corpus/skills"))
KB = "mcp__plugin_sky_kb__"

cards = {}

cards["analyze"] = f"""**When to use.** The user asks to analyze or summarize one module — "analyze module X", "what does the retrieval module do" — or before working on an unfamiliar module.

**Input.** One module: a directory, package or service name. If several match, list the candidates and ask which one.

**Steps.** (1) Check for a cached card at project-specs/module-cards/<module>.md and reuse it when the module has not changed materially since it was written. (2) Read the module from the local checkout: structure, entry points, public interfaces, dependencies in both directions, covering tests. (3) Query the knowledge base for what it already holds on the module. (4) Reconcile the two: the local code wins for current state, and a contradicting document becomes a recorded gotcha. (5) Fill the module-card template and save it with the analysis date and the commit hash, so the freshness check works next time. (6) Back in the main thread, offer to ingest the card.

**Guardrails.** Read-only against the knowledge base; the single write is the confirmed ingest in step 6, and it never runs automatically. Raw source code is never ingested — current code always comes from the local checkout. Every retrieved claim carries a citation, and anything unresolved goes to OPEN questions instead of being guessed.

**Runs on.** The context-retriever agent, forked; falls back to running inline when that agent is not available.

**Tools.** {KB}kb_similarity_search, {KB}kb_agentic_search, {KB}kb_graph_query"""

cards["bugfix"] = f"""**When to use.** The user asks to fix a bug ticket — "fix PROJ-1234", "this module is broken", "/kb:bugfix PROJ-x". For new features use /kb:spec instead; this is the light track.

**Input.** A bug ticket id. Ask for it if not given.

**Steps.** (1) Pull the ticket live from the issue tracker, never from ingested content. (2) Run a short three-question retrieval: similar past incidents and fix notes, recent merge requests touching the suspect module, and the covering test suites. (3) Reproduce the bug locally before writing any fix. (4) Write a fix note from the template — root cause with file and line references, the minimal fix approach, the test plan, citations and OPEN questions — and show it before implementing. (5) Run the architect gate only when the fix crosses module boundaries; say which case applies. (6) Implement the fix plus a regression test, and verify the test fails on the unfixed code and passes on the fixed code. (7) Validate in a single pass. (8) Commit code, test and fix note together in one merge request linked to the ticket.

**Guardrails.** No repro, no fix — proceed only with an explicit recorded waiver. Cite or OPEN: no uncited factual claims in the fix note. Keep the fix minimal; if it grows into a redesign, stop and switch to /kb:spec. Never ingest the fix note by hand — CI ingests it after merge.

**Tools.** {KB}kb_similarity_search, {KB}kb_agentic_search, {KB}kb_graph_query"""

cards["context"] = f"""**When to use.** The user asks what the team already knows — "get context for PROJ-xxxx", "what do we know about this module", "how does X work", "find related designs" — or any design, spec or bugfix track is starting. This is the core retrieval primitive every other track begins with.

**Input.** One ticket id or a free-text topic. Ask for one if neither is given.

**Steps.** Run rounds of an escalating search loop, at most five. (1) Broad pass with similarity search: two to four queries to map which areas are relevant. (2) Deepen with agentic search over the promising areas, which adds one hop of graph evidence. (3) Use a read-only graph query only when structure or blast radius matters. (4) Use synthesis search only when prose over many sources is genuinely needed — it is the slowest and never the first pass. Anchor every query with concrete identifiers: ticket ids, module names, file or feature names. Abstract phrasing returns mush.

**Done when.** Five things are answered with citations: affected modules, governing documents, covering tests, recent activity, and downstream dependents. After five rounds, stop — unanswered items become OPEN questions.

**Guardrails.** Cite or OPEN: a claim that cannot be cited is never stated as fact. Ingested content never establishes current state. Read-only — writes nothing, modifies nothing. Return only the distilled pack to the caller, never the raw retrieval chunks.

**Runs on.** The context-retriever agent, forked, so raw chunks stay out of the main conversation.

**Tools.** {KB}kb_similarity_search, {KB}kb_agentic_search, {KB}kb_graph_query, {KB}kb_context_search"""

cards["design"] = f"""**When to use.** The user asks for a solution design — "create a solution design for PROJ-xxxx", "design a solution for this ticket", "architecture design for this story". Aimed at architects and senior developers.

**Input.** A ticket id.

**Steps.** (1) Fetch the ticket live from the issue tracker and say which path was used. (2) Build a cited context pack by running /kb:context on the ticket. (3) Draft the design from the template: problem, at least two options considered with trade-offs, the chosen approach and why the others lost, impacted modules derived from the graph, risks, test strategy. (4) Render every diagram as an image file and embed it — validate the SVG, produce a PNG where possible, and keep any diagram source in an appendix. (5) Present the draft and iterate until the architect explicitly approves it. (6) Save to project-specs/solution-designs/ with images alongside, and add a line to the index. (7) Confirm, then attach to the ticket and set the assignee. (8) Confirm, then ingest via /kb:ingest.

**Guardrails.** Never save, attach or ingest an unapproved draft. Both outward writes are confirmed separately. Never draft from memory when the tracker is unreachable — stop and say so. Never ship a diagram that exists only as source. Cite or OPEN on every claim.

**Tools.** {KB}kb_graph_query, {KB}kb_similarity_search"""

cards["impact"] = f"""**When to use.** The user asks what a change would break — "what breaks if I change X", "blast radius of this change", "who depends on this module", "which tests cover X".

**Input.** A module or service name, a change description, or a ticket id.

**Steps.** (1) Classify the input. (2) For a ticket, fetch it live and take its modules as anchor candidates. (3) Resolve the anchor to a real graph node: surface candidates with similarity search, confirm the exact node with a graph query, and check the real type names in the ontology if a query returns nothing. State the choice and the alternatives. (4) Walk the graph with small separate read-only queries: direct dependents, transitive dependents to two hops, covering tests, governing documents, related specs, recent related work. (5) Derive suggested reviewers from the author metadata of recent related work. (6) Verify against the local checkout — the graph may be stale — and exclude anything the repo contradicts. (7) Report as a table of affected modules, dependent services, tests to run, documents to update and suggested reviewers, with a source for every entry.

**Guardrails.** Strictly read-only: no ingest, no ticket updates, no file creation, and the query language is restricted to matching and returning. Never guess reviewer names when author metadata is missing. Stop at the report — point the user to another track to act on it.

**Runs on.** The context-retriever agent, forked.

**Tools.** {KB}kb_similarity_search, {KB}kb_graph_query, {KB}kb_ontologies_get"""

cards["ingest"] = f"""**When to use.** The user explicitly asks to push one document into the knowledge base — "ingest this file", "save this session context", "ingest this skill", "add this to the knowledge base". Never auto-runs.

**Input.** A file path or URL, plus an optional document type.

**Steps.** (1) Read the source and extract its title and a short summary. (2) Determine the document type from the allowed list, state the reasoning, and confirm it. (3) Select the ontology live from what the knowledge base actually offers — propose a default, never hard-code one. (4) Auto-select the rest: layer is always project, and metadata is always automatic. (5) Run a duplicate pre-check and show any near match plainly, leaving the decision to the user. (6) Nothing is written up to here. (7) Show one compact block of exactly what will be ingested and ask for an explicit yes. (8) Ingest with exactly one source: a URL, plain text, or base64 bytes. (9) Poll the asynchronous job and report the resulting document id, or quote the real error on failure.

**Guardrails.** Manual only — writing to a shared knowledge base is a deliberate human act, and no ingest tool is called before the step 7 confirmation. Never ingest raw source code; offer /kb:analyze to produce a module card instead. Never choose layer or metadata by asking the user. Never silently retry a failed job.

**Tools.** {KB}kb_ontologies_list, {KB}kb_similarity_search, {KB}kb_documents_ingest, {KB}kb_jobs_status, {KB}kb_jobs_output, {KB}kb_jobs_logs"""

cards["learn"] = f"""**When to use.** A working session is wrapping up and the takeaways should be recorded — "capture learnings", "what did we learn", "/kb:learn".

**Input.** The session itself, plus the ticket worked on if there was one.

**Steps.** (1) Review the whole session for what changed and why, decisions and their reasoning, surprises, corrections from the user, and gotchas discovered. Corrections are the highest-value material. (2) Propose a numbered list of candidates, each with a one-line title, a type, and two or three lines of substance. KNOWLEDGE means a fact or gotcha and goes to the knowledge base; RULE means a change to how the team works and becomes a repo change instead. (3) Get approval item by item — never batch-approve. (4) Write each approved knowledge learning as a short note with What, Why and How to apply, check for a near-duplicate first, then ingest it and report the document id. (5) Draft approved rule learnings as an exact file diff on a branch. (6) Close with a one-line summary naming document ids and the branch.

**Guardrails.** Never write anywhere without per-item approval. Skip routine work — a learning must be non-obvious and reusable by someone who was not there; if the session produced nothing, say so rather than inventing learnings. Mark unconfirmed behaviour OPEN rather than stating it as fact. Never push or merge the rule branch without being asked.

**Tools.** {KB}kb_similarity_search, {KB}kb_documents_ingest, {KB}kb_jobs_status, {KB}kb_jobs_output"""

cards["review"] = f"""**When to use.** The user asks for a review of a merge request, a branch, or the working diff. Also runs as the gate inside the spec and bugfix tracks.

**Input.** A merge request id, a branch name, or nothing — which means the current working diff.

**Steps.** (1) Identify the target. (2) Collect the diff from local git or live from the hosting system, say which path was used, and map the touched files to modules. (3) Reuse the session's existing context pack for those modules, or build one scoped to them: governing designs, related specs, past fix notes for the same areas, and graph neighbours. (4) Run the architect-reviewer agent with the diff, the context pack, and the approved spec or fix note when acting as a gate. It checks correctness and regressions, consistency with governing designs, blast radius and missing tests, and needless complexity. (5) Report numbered findings, most severe first, each with a severity, a file and line anchor, a concrete fix, and a citation. List OPEN questions separately. Print the verdict as the last line. (6) In gate mode return the verdict to the calling flow; standalone the review is advisory.

**Guardrails.** Never merges, pushes, or votes on a merge request. Posting findings as comments is always confirmed first. A blocked verdict needs at least one blocker finding. Never modify files during a review. Diff and file contents come from git or the live system, never from ingested content.

**Tools.** {KB}kb_similarity_search, {KB}kb_agentic_search, {KB}kb_graph_query"""

cards["spec"] = f"""**When to use.** The user wants a feature story implemented end to end — "work on PROJ-1234", "implement this story", "build PROJ-x". This is the main orchestrator. Not for bugs, which go to /kb:bugfix, and not for pure research, which goes to /kb:context.

**Input.** A story ticket id, plus an optional flag to stop after the approved plan.

**Steps.** (1) Fetch the story live from the issue tracker; stop if it cannot be fetched rather than substituting history. (2) Build the context pack via /kb:context, then check for an existing solution design — if one exists it is the primary input, and any deviation becomes a question, never a silent change. (3) Ask three to five clarifying questions in one message and wait for answers. (4) Write the two-part spec: what and why, and how file by file with a test plan. Every claim cites a source. (5) Run the architect gate and loop until it approves. (6) Stop here when only a plan was asked for. (7) Implement exactly per the plan, reading current file contents from the local checkout before every edit. (8) Validate and fix until it passes. (9) Commit and open a merge request that carries the spec together with the code.

**Guardrails.** Never write implementation code before the gate approves. This track never ingests anything — CI ingests merged specs. Gates run in order with no skipping. Current code comes only from the local checkout; ticket state only from the live tracker.

**Tools.** {KB}kb_similarity_search, {KB}kb_agentic_search, {KB}kb_graph_query"""

cards["test"] = f"""**When to use.** The user asks to run the tests that matter for a change, module or ticket — "run affected tests", "regression for X", "test this change" — or a change was just implemented.

**Input.** A change, a module, or a ticket id.

**Steps.** (1) Determine the scope, preferring an existing context pack, then a graph impact analysis, and only last the git diff on the branch. Do not default to running everything. (2) Discover the local runner from the repo itself — makefile targets, test configuration, package scripts, CI docs — and use the repo's own command verbatim. (3) Map the scope to concrete test paths or expressions; note an unclear mapping as an OPEN question rather than widening the run. (4) Run the local tests immediately and capture the full output. (5) Decide whether a remote run is warranted at all. (6) Prepare the remote plan without executing it, present the suites, environment and reason for each, and stop for confirmation. (7) Execute only confirmed remote runs and poll them. (8) Report what ran, pass and fail counts, the failures with their relevant output, and one concrete next step.

**Guardrails.** Local tests run freely; shared-environment suites never fire without an explicit yes, because other people depend on those environments. Test-management record-keeping is out of scope. Never guess which suite covers which module. Never silently re-fire a stuck remote run.

**Tools.** {KB}kb_tools_regression_run_regression_tests, {KB}kb_tools_browser_execute_suite, {KB}kb_graph_query"""

for name, body in cards.items():
    text = (f"# /kb:{name}\n\n"
            f"Skill: /kb:{name}\n"
            f"Project: kb-sdd-plugin\n\n"
            f"{body}\n")
    path = os.path.join(D, f"kb-{name}.md")
    with open(path, "w") as fh:
        fh.write(text)
    flag = "OK " if len(text) < 2000 else "OVER"
    print(f"{flag} {len(text):5} chars  {path}")
