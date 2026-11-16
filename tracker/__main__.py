"""Daily pipeline: fetch arXiv -> analyse with the LLM -> regenerate README.

Usage: python -m tracker [--no-llm] [--render-only]
"""

from __future__ import annotations

import argparse
import json

from . import arxiv, config, llm, render


def load_store() -> dict[str, dict]:
    if not config.DATA_FILE.exists():
        return {}
    return {p["id"]: p for p in json.loads(config.DATA_FILE.read_text(encoding="utf-8"))}


def save_store(store: dict[str, dict]) -> None:
    papers = sorted(store.values(), key=lambda p: (p["published"], p["id"]), reverse=True)
    config.DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    config.DATA_FILE.write_text(
        json.dumps(papers, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
    )


def collect_new(store: dict[str, dict]) -> list[dict]:
    """Fetch every topic and return papers not yet in the store, capped per run."""
    candidates: dict[str, dict] = {}
    per_topic: list[list[dict]] = []
    for topic in config.TOPICS:
        per_topic.append([])
        limit = topic["max_results"] * config.FETCH_MULTIPLIER
        fetched = arxiv.fetch_topic(topic["query"], limit)
        fresh = 0
        for paper in fetched:
            known = store.get(paper["id"]) or candidates.get(paper["id"])
            if known:
                if topic["key"] not in known["topics"]:
                    known["topics"].append(topic["key"])
                continue
            paper["topics"] = [topic["key"]]
            paper["analysis"] = None
            candidates[paper["id"]] = paper
            per_topic[-1].append(paper)
            fresh += 1
        print(f"{topic['label']}: fetched {len(fetched)}, {fresh} new")

    if len(candidates) <= config.MAX_NEW_PER_RUN:
        return list(candidates.values())
    # Over the cap: take papers round-robin across topics (newest first within
    # each) so no single topic uses up the whole daily budget.
    print(f"Capping {len(candidates)} new papers to MAX_NEW_PER_RUN={config.MAX_NEW_PER_RUN}")
    new: list[dict] = []
    for rank in range(max(map(len, per_topic))):
        for papers in per_topic:
            if rank < len(papers) and len(new) < config.MAX_NEW_PER_RUN:
                new.append(papers[rank])
    return new


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--no-llm", action="store_true",
                        help="fetch and store papers but leave them unanalysed")
    parser.add_argument("--render-only", action="store_true",
                        help="regenerate README/chart from the existing store")
    args = parser.parse_args()

    store = load_store()
    if not args.render_only:
        new = collect_new(store)
        for paper in new:
            store[paper["id"]] = paper
        # Papers whose analysis failed on an earlier run are retried here.
        pending = [p for p in store.values() if not p.get("analysis")]
        if args.no_llm:
            print(f"--no-llm: {len(pending)} papers left unanalysed")
        else:
            try:
                done = llm.analyse(pending)
                print(f"Analysed {done}/{len(pending)} papers with {config.LLM_MODEL}")
            except BaseException:
                save_store(store)  # keep fetched papers so the next run retries them
                raise
        save_store(store)

    render.render_all(store)
    print(f"README updated: {sum(bool(p.get('analysis')) for p in store.values())} papers listed")


if __name__ == "__main__":
    main()
