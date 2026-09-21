"""Pre-flight validation using KB's OWN Ontology schema, so a bad upload is
import os
caught locally instead of as a 422 from the server.

Run with the kb-v2 venv python:
  .../kb-v2/.venv/bin/python validate_ontology.py <new.yaml> [<source.yaml>]
"""
import sys, yaml, importlib.util, pathlib

KB = pathlib.Path(os.environ.get("KB_REPO", "."))
spec = importlib.util.spec_from_file_location(
    "ont_schema", KB / "app/services/ontology/schema.py")
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
Ontology = mod.Ontology
# schema.py uses forward references; resolve them against the module namespace
# or pydantic refuses to instantiate ("is not fully defined").
try:
    Ontology.model_rebuild(_types_namespace=vars(mod))
except Exception as _e:
    print("WARN: could not rebuild Ontology model:", _e)

new = pathlib.Path(sys.argv[1])
raw = new.read_text()
print(f"file: {new.name}  ({len(raw)} bytes)")

if len(raw.encode()) > 256 * 1024:
    print("FAIL: exceeds the 256 KiB upload cap"); sys.exit(1)

parsed = yaml.safe_load(raw)
try:
    ont = Ontology(**parsed)
except Exception as e:
    print("FAIL: rejected by KB's own Ontology schema:\n", e); sys.exit(1)

print(f"PASS schema: name={ont.name!r}  {len(ont.entity_types)} entities  "
      f"{len(ont.relation_types)} relations")

ents = [e.name for e in ont.entity_types]
rels = [r.name for r in ont.relation_types]
for label, seq in (("entity", ents), ("relation", rels)):
    dupes = {n for n in seq if seq.count(n) > 1}
    if dupes:
        print(f"FAIL: duplicate {label} names: {sorted(dupes)}"); sys.exit(1)

# every relation endpoint resolves (the server checks this too, belt and braces)
missing = [(r.name, r.source, r.target) for r in ont.relation_types
           if r.source not in set(ents) or r.target not in set(ents)]
if missing:
    print("FAIL: relation endpoints not defined as entity types:", missing); sys.exit(1)
print("PASS endpoints: every relation source/target resolves")

# leak scan — this file is going into a client-facing environment
BANNED = ["kb", "example"]  # add private words in your own copy; never commit them
hits = []
for i, line in enumerate(raw.splitlines(), 1):
    low = line.lower()
    for b in BANNED:
        if b in low:
            hits.append((i, b, line.strip()[:100]))
if hits:
    print(f"FAIL leak scan: {len(hits)} banned reference(s)")
    for i, b, t in hits[:15]:
        print(f"  line {i}: [{b}] {t}")
    sys.exit(1)
print(f"PASS leak scan: none of {BANNED} appear")

# coverage vs the source ontology, if given
if len(sys.argv) > 2:
    src = yaml.safe_load(pathlib.Path(sys.argv[2]).read_text())
    s_ents = [e["name"] for e in src.get("entity_types", [])]
    s_rels = [r["name"] for r in src.get("relation_types", [])]
    lost_e, lost_r = set(s_ents) - set(ents), set(s_rels) - set(rels)
    extra_e, extra_r = set(ents) - set(s_ents), set(rels) - set(s_rels)
    print(f"\nsource: {len(s_ents)} entities / {len(s_rels)} relations")
    print(f"  dropped entities : {sorted(lost_e) or 'none'}")
    print(f"  dropped relations: {sorted(lost_r) or 'none'}")
    print(f"  added entities   : {sorted(extra_e) or 'none'}")
    print(f"  added relations  : {sorted(extra_r) or 'none'}")
    if lost_e or lost_r or extra_e or extra_r:
        print("FAIL: type coverage differs from source"); sys.exit(1)
    print("PASS coverage: identical type sets")

# descriptions must stay rich — they drive extraction quality in this format
thin = [e.name for e in ont.entity_types if len(e.description) < 40]
if thin:
    print(f"\nWARN: {len(thin)} entity description(s) under 40 chars: {thin}")
print("\nALL CHECKS PASSED — safe to upload")
