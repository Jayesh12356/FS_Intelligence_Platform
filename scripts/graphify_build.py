"""One-shot graphify build for the FS Intelligence Platform.

Drives the same pipeline graphify's `/graphify` skill drives, but
**code-only** (deterministic AST pass + cluster + report) so it can run
non-interactively without an LLM.

Outputs land in ``graphify-out/`` at the repo root:

* ``GRAPH_REPORT.md`` — god nodes, communities, suggested questions
* ``graph.json``      — full persisted graph for ``graphify query``
* ``graph.html``      — interactive viz (open in any browser)

Re-run any time the codebase changes. Semantic enrichment (docs, PDFs,
images) can be layered on later by typing ``/graphify .`` inside Cursor;
that flow uses Cursor's own LLM and writes to the same cache directory.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent  # scripts/ → repo root
OUT = REPO_ROOT / "graphify-out"
OUT.mkdir(exist_ok=True)


def main() -> int:
    from graphify.analyze import god_nodes, suggest_questions, surprising_connections
    from graphify.build import build_from_json
    from graphify.cluster import cluster, score_all
    from graphify import detect as _detect_mod
    from graphify.detect import detect
    from graphify.export import to_html, to_json
    from graphify.extract import collect_files, extract
    from graphify.report import generate

    # graphify hardcodes any directory called "build" as a noise dir
    # (next to dist/target/out), but our Next.js app uses
    # ``frontend/src/app/documents/[id]/build`` as a real user-facing
    # route. Drop "build" from the skip set so the Build page shows up
    # in the knowledge graph alongside the other [id]/* routes.
    _detect_mod._SKIP_DIRS.discard("build")

    print(f"graphify build for {REPO_ROOT}")

    # ── 1. detect
    detection = detect(REPO_ROOT)
    (OUT / ".graphify_detect.json").write_text(json.dumps(detection, indent=2))
    files = detection.get("files", {})
    counts = {k: len(v) for k, v in files.items() if v}
    print(f"  detect: {detection.get('total_files', 0)} files — {counts}")
    if detection.get("total_files", 0) == 0:
        print("  no supported files found; aborting.")
        return 1

    # ── 2. AST extraction (deterministic, no LLM)
    code_files: list[Path] = []
    for f in files.get("code", []):
        p = Path(f)
        code_files.extend(collect_files(p) if p.is_dir() else [p])
    if code_files:
        ast = extract(code_files, cache_root=REPO_ROOT)
        print(f"  AST: {len(ast['nodes'])} nodes / {len(ast['edges'])} edges")
    else:
        ast = {"nodes": [], "edges": [], "input_tokens": 0, "output_tokens": 0}

    semantic_empty = {
        "nodes": [],
        "edges": [],
        "hyperedges": [],
        "input_tokens": 0,
        "output_tokens": 0,
    }

    # ── 3. merge AST + (empty) semantic into the canonical extraction blob
    seen = {n["id"] for n in ast["nodes"]}
    merged_nodes = list(ast["nodes"])
    for n in semantic_empty["nodes"]:
        if n["id"] not in seen:
            merged_nodes.append(n)
            seen.add(n["id"])
    extraction = {
        "nodes": merged_nodes,
        "edges": ast["edges"] + semantic_empty["edges"],
        "hyperedges": semantic_empty["hyperedges"],
        "input_tokens": 0,
        "output_tokens": 0,
    }
    (OUT / ".graphify_extract.json").write_text(json.dumps(extraction, indent=2))

    # ── 4. build NetworkX graph
    G = build_from_json(extraction)
    if G.number_of_nodes() == 0:
        print("  ERROR: extraction produced 0 nodes")
        return 2
    print(f"  graph: {G.number_of_nodes()} nodes / {G.number_of_edges()} edges")

    # ── 5. cluster + analyse
    communities = cluster(G)
    cohesion = score_all(G, communities)
    gods = god_nodes(G)
    surprises = surprising_connections(G, communities)
    labels: dict[int, str] = {cid: f"Community {cid}" for cid in communities}
    questions = suggest_questions(G, communities, labels)
    print(f"  clustered into {len(communities)} communities; {len(gods)} god nodes")

    analysis = {
        "communities": {str(k): v for k, v in communities.items()},
        "cohesion": {str(k): v for k, v in cohesion.items()},
        "gods": gods,
        "surprises": surprises,
        "questions": questions,
    }
    (OUT / ".graphify_analysis.json").write_text(json.dumps(analysis, indent=2))
    (OUT / ".graphify_labels.json").write_text(
        json.dumps({str(k): v for k, v in labels.items()})
    )

    # ── 6. report + JSON + HTML
    tokens = {"input": 0, "output": 0}
    report = generate(
        G,
        communities,
        cohesion,
        labels,
        gods,
        surprises,
        detection,
        tokens,
        str(REPO_ROOT),
        suggested_questions=questions,
    )
    (OUT / "GRAPH_REPORT.md").write_text(report, encoding="utf-8")
    print(f"  wrote {OUT / 'GRAPH_REPORT.md'}")

    to_json(G, communities, str(OUT / "graph.json"))
    print(f"  wrote {OUT / 'graph.json'}")

    if G.number_of_nodes() <= 5000:
        to_html(G, communities, str(OUT / "graph.html"), community_labels=labels)
        print(f"  wrote {OUT / 'graph.html'}")
    else:
        print(
            f"  graph has {G.number_of_nodes()} nodes — skipping HTML viz "
            "(use Obsidian export instead)"
        )

    print("done.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
