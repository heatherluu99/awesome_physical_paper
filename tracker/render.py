"""Render README.md, monthly archives and the trend chart from the paper store."""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from . import config  # noqa: E402

START = "<!-- PAPERS:START -->"
END = "<!-- PAPERS:END -->"

README_HEADER = """# Awesome Physical AI

A daily, automatically updated tracker of new arXiv papers on **Robotics / Human-in-the-loop /
Industrial RL**. Each paper is summarised by an LLM and scored from 1 to 5 on **technical
hardness** and **industrial potential**.

"""

README_FOOTER = """
## Methodology

The pipeline runs once a day as a GitHub Action and has four stages: collection, assessment,
ranking, and aggregation. All parameters below are defined in `tracker/config.py`.

### 1. Paper collection

Three queries are sent to the [arXiv API](https://info.arxiv.org/help/api/index.html), each sorted
by submission date (newest first):

| Topic | Query | Papers fetched per run |
| --- | --- | --- |
| Robotics | primary or cross-listed category `cs.RO` | 100 |
| Human-in-the-loop | abstract contains "human-in-the-loop", "human in the loop", "interactive imitation learning" or "shared autonomy"; category in `cs.RO`, `cs.LG`, `cs.AI`, `cs.HC` | 30 |
| Industrial RL | abstract contains "reinforcement learning" and one of "industrial", "manufacturing", "factory", "process control"; category in `cs.LG`, `cs.RO`, `cs.AI`, `eess.SY` | 30 |

Papers are deduplicated by arXiv identifier (version suffix removed). A paper matched by several
queries is kept once and tagged with every matching topic. At most 50 previously unseen papers are
assessed per run; when more are available, they are selected round-robin across the three topics,
newest first within each topic.

### 2. LLM assessment

Each paper is assessed independently in a single model call. The model receives only the title,
the abstract, the primary arXiv category and the matched topics; the full text is not read. The
response is constrained by a JSON schema to exactly five fields:

1. `summary`: a 2-3 sentence summary (problem, method, result).
2. `technical_hardness`: an ordinal score *H* in {1, 2, 3, 4, 5}.
3. `industrial_potential`: an ordinal score *I* in {1, 2, 3, 4, 5}.
4. `category`: one label from a closed taxonomy of eight classes.
5. `rationale`: one sentence stating the main evidence for the two scores.

The exact prompt is in `tracker/llm.py`. A paper whose call fails is stored unscored and retried
on the next run.

### 3. Scoring rubric

Both dimensions use a 5-point ordinal scale with anchors at 1, 3 and 5. Scores of 2 and 4 are
left for the model to interpolate between adjacent anchors.

| Score | Technical hardness (*H*): depth and novelty of the method | Industrial potential (*I*): proximity to real deployment |
| --- | --- | --- |
| 1 | Survey, position paper, or straightforward application of an existing method | Purely theoretical, or validated only in toy environments |
| 3 | Solid incremental work with a clear methodological improvement and comparative experiments | Validated on real robots or realistic simulation; deployment still needs substantial engineering |
| 5 | New paradigm, or rigorous theoretical guarantees backed by large-scale real-world validation | Validated in a real industrial setting and addresses deployment constraints (safety, cost, reliability, cycle time) |

To counter score inflation, the model is instructed that most papers should fall in the 2-4
range, that 1 and 5 require strong evidence, and that an abstract which does not support a high
score should be scored conservatively.

### 4. Taxonomy

Manipulation · Locomotion & Navigation · Foundation Models / VLA · Human-in-the-loop ·
Industrial RL & Control · Simulation & Sim2Real · Perception & Mapping · Other.

The category is assigned by the model from the paper's content and is independent of the query
that retrieved the paper.

### 5. Ranking and aggregation

- **Composite score.** *S* = *H* + *I*, with *S* in [2, 10] and equal weight on both dimensions.
- **Top 10.** Papers published in the 7 days up to the most recent publication date are ranked by
  *S* in descending order; ties are broken by higher *I*.
- **Monthly trend.** Papers are grouped by publication month. The chart reports the number of
  papers per category and the arithmetic means of *H* and *I* for each month.

### 6. Limitations

- **Abstract-only evidence.** Scores reflect what the abstract claims, not a review of the full
  paper, its experiments or its code.
- **Single automated rater.** Scores come from one LLM and have not been calibrated against human
  expert ratings; no inter-rater reliability has been measured. Re-running the same paper may
  shift a score by one point.
- **Ordinal scale.** *H* and *I* are ordinal, so the composite score and monthly means are
  descriptive summaries rather than interval measurements.
- **Sampling.** Keyword queries trade recall for precision and can retrieve off-topic papers
  (typically labelled *Other*). Because of the daily cap, `cs.RO` is sampled rather than covered
  exhaustively, so monthly counts describe the tracked sample, not the whole field.
"""

# Fixed colour per category so a category keeps its colour as data changes.
PALETTE = ["#4c78a8", "#f58518", "#54a24b", "#e45756", "#b279a2", "#72b7b2", "#eeca3b", "#9d9d9d"]
CATEGORY_COLOR = {key: PALETTE[i] for i, (key, _) in enumerate(config.CATEGORIES)}
INK = "#6e7781"  # readable on both GitHub light and dark backgrounds


def _cell(text: str) -> str:
    return " ".join(str(text).split()).replace("|", "\\|")


def _total(paper: dict) -> int:
    a = paper["analysis"]
    return a["technical_hardness"] + a["industrial_potential"]


def _table(papers: list[dict], with_date: bool = True) -> str:
    head = ["Date"] if with_date else []
    head += ["Paper", "Category", "Hardness", "Industrial", "Summary"]
    lines = ["| " + " | ".join(head) + " |", "|" + "|".join([" --- "] * len(head)) + "|"]
    for p in papers:
        a = p["analysis"]
        row = [p["published"][5:]] if with_date else []
        row += [
            f"[{_cell(p['title'])}]({p['url']})",
            config.CATEGORY_NAME.get(a["category"], a["category"]),
            str(a["technical_hardness"]),
            str(a["industrial_potential"]),
            _cell(a["summary"]),
        ]
        lines.append("| " + " | ".join(row) + " |")
    return "\n".join(lines)


def _mean(values: list[int]) -> float:
    return sum(values) / len(values) if values else 0.0


def _by_month(papers: list[dict]) -> dict[str, list[dict]]:
    months: dict[str, list[dict]] = defaultdict(list)
    for p in papers:
        months[p["published"][:7]].append(p)
    return dict(sorted(months.items()))


def render_chart(months: dict[str, list[dict]]) -> None:
    labels = list(months)
    fig, (top, bottom) = plt.subplots(
        2, 1, figsize=(9, 6.2), sharex=True, height_ratios=[3, 2], layout="constrained"
    )
    x = range(len(labels))

    floor = [0] * len(labels)
    for key, name in config.CATEGORIES:
        counts = [sum(p["analysis"]["category"] == key for p in months[m]) for m in labels]
        if not any(counts):
            continue
        top.bar(x, counts, bottom=floor, width=0.6, label=name, color=CATEGORY_COLOR[key])
        floor = [f + c for f, c in zip(floor, counts)]
    top.set_ylabel("Papers per month")
    top.set_title("Monthly research trend", loc="left", fontweight="bold")
    if any(floor):
        top.legend(ncols=4, fontsize=8, frameon=False, labelcolor=INK, loc="upper left",
                   bbox_to_anchor=(0, -0.02), borderaxespad=0)

    for field, name, color in [
        ("technical_hardness", "Technical hardness", "#4c78a8"),
        ("industrial_potential", "Industrial potential", "#f58518"),
    ]:
        means = [_mean([p["analysis"][field] for p in months[m]]) for m in labels]
        bottom.plot(x, means, marker="o", linewidth=2, color=color, label=name)
        if means:
            bottom.annotate(f"{means[-1]:.2f}", (len(labels) - 1, means[-1]),
                            textcoords="offset points", xytext=(8, -3), color=color, fontsize=9)
    bottom.set_ylim(1, 5)
    bottom.set_ylabel("Average score (1-5)")
    bottom.legend(ncols=2, fontsize=8, frameon=False, labelcolor=INK, loc="upper left")
    bottom.set_xticks(list(x), labels)
    bottom.set_xlim(-0.6, max(len(labels) - 0.4, 2.6))

    for ax in (top, bottom):
        ax.set_facecolor("none")
        ax.grid(axis="y", color=INK, alpha=0.2, linewidth=0.8)
        ax.set_axisbelow(True)
        ax.tick_params(colors=INK)
        ax.yaxis.label.set_color(INK)
        ax.title.set_color(INK)
        for side in ("top", "right"):
            ax.spines[side].set_visible(False)
        for side in ("left", "bottom"):
            ax.spines[side].set_color(INK)

    config.CHART_FILE.parent.mkdir(parents=True, exist_ok=True)
    # Fixed salt + no date keeps the SVG byte-identical when data is unchanged.
    plt.rcParams["svg.hashsalt"] = "paper-tracker"
    fig.savefig(config.CHART_FILE, transparent=True, metadata={"Date": None})
    plt.close(fig)


def render_archive(month: str, papers: list[dict]) -> None:
    lines = [
        f"# Paper archive: {month}",
        "",
        f"{len(papers)} papers · avg. technical hardness "
        f"{_mean([p['analysis']['technical_hardness'] for p in papers]):.2f} · avg. industrial potential "
        f"{_mean([p['analysis']['industrial_potential'] for p in papers]):.2f}",
        "",
        "[← Back to README](../README.md)",
    ]
    for key, name in config.CATEGORIES:
        group = [p for p in papers if p["analysis"]["category"] == key]
        if not group:
            continue
        group.sort(key=lambda p: (-_total(p), p["published"]), reverse=False)
        lines += ["", f"## {name} ({len(group)})", "", _table(group)]
    config.ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    (config.ARCHIVE_DIR / f"{month}.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _readme_body(papers: list[dict], months: dict[str, list[dict]]) -> str:
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    out = [
        f"> Last updated: {today} (UTC) · {len(papers)} papers tracked · Model: `{config.LLM_MODEL}`",
        "",
        "## 📈 Trends",
        "",
        "![Monthly research trend](assets/trend.svg)",
    ]
    if not papers:
        return "\n".join(out + ["", "_No data yet. Waiting for the first run._"])

    latest = date.fromisoformat(max(p["published"] for p in papers))
    since = (latest - timedelta(days=config.README_TOP_DAYS - 1)).isoformat()
    top = sorted(
        (p for p in papers if p["published"] >= since),
        key=lambda p: (-_total(p), -p["analysis"]["industrial_potential"], p["id"]),
    )[: config.README_TOP_N]
    out += ["", f"## 🔥 Top {config.README_TOP_N} of the last {config.README_TOP_DAYS} days", "",
            "Ranked by technical hardness + industrial potential.", "", _table(top)]

    out += ["", "## 🆕 Latest papers"]
    days = sorted({p["published"] for p in papers}, reverse=True)[: config.README_RECENT_DAYS]
    for day in days:
        group = sorted((p for p in papers if p["published"] == day), key=lambda p: -_total(p))
        out += ["", f"### {day} ({len(group)} papers)", "", _table(group, with_date=False)]

    out += ["", "## 🗂 Monthly archive", "",
            "| Month | Papers | Avg. hardness | Avg. industrial | Top category |", "| --- | --- | --- | --- | --- |"]
    for month in sorted(months, reverse=True):
        group = months[month]
        hottest = Counter(p["analysis"]["category"] for p in group).most_common(1)[0][0]
        out.append(
            f"| [{month}](archive/{month}.md) | {len(group)} "
            f"| {_mean([p['analysis']['technical_hardness'] for p in group]):.2f} "
            f"| {_mean([p['analysis']['industrial_potential'] for p in group]):.2f} "
            f"| {config.CATEGORY_NAME.get(hottest, hottest)} |"
        )
    return "\n".join(out)


def render_all(store: dict[str, dict]) -> None:
    papers = [p for p in store.values() if p.get("analysis")]
    months = _by_month(papers)
    render_chart(months)
    for month, group in months.items():
        render_archive(month, group)

    body = f"{START}\n{_readme_body(papers, months)}\n{END}"
    if config.README_FILE.exists():
        text = config.README_FILE.read_text(encoding="utf-8")
    else:
        text = README_HEADER + f"{START}\n{END}\n" + README_FOOTER
    if START in text and END in text:
        # Only the marked block is regenerated; anything around it is kept.
        text = text[: text.index(START)] + body + text[text.index(END) + len(END):]
    else:
        text = text.rstrip() + "\n\n" + body + "\n"
    config.README_FILE.write_text(text, encoding="utf-8")
