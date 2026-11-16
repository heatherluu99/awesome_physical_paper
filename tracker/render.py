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

README_FOOTER = r"""
## Methodology

The pipeline runs daily via GitHub Actions in four stages: **Collection → Assessment → Ranking → Aggregation**. All configurable parameters are defined in [`tracker/config.py`](tracker/config.py).

### 1. Paper Collection

Three queries are executed against the arXiv API, sorted by submission date (newest first):

| Topic | Categories | Abstract Filter | Fetch Cap |
| :--- | :--- | :--- | :---: |
| **Robotics** | `cs.RO` *(primary or cross-listed)* | *None* | 100 |
| **Human-in-the-loop** | `cs.RO`, `cs.LG`, `cs.AI`, `cs.HC` | `"human-in-the-loop"` OR `"human in the loop"` OR `"interactive imitation learning"` OR `"shared autonomy"` | 30 |
| **Industrial RL** | `cs.LG`, `cs.RO`, `cs.AI`, `eess.SY` | `"reinforcement learning"` **AND** (`"industrial"` OR `"manufacturing"` OR `"factory"` OR `"process control"`) | 30 |

* **Deduplication:** Papers are deduplicated by base arXiv ID (version suffix stripped); multi-query hits retain all matched topic tags.
* **Daily assessment cap:** At most **50** previously unseen papers are scored per run. When more are available, candidates are selected round-robin across the three topics (newest first within each topic).

---

### 2. LLM Assessment

Each paper is evaluated independently in a single LLM call using only its **title, abstract, primary category, and matched topics** (full text is not read). The exact prompt is located in [`tracker/llm.py`](tracker/llm.py). Failed calls remain unscored and are retried on the next run.

#### Output Schema (JSON)

| Field | Type / Range | Description |
| :--- | :--- | :--- |
| `summary` | `string` | 2–3 sentence summary covering problem, method, and result. |
| `technical_hardness` | $H \in \lbrace 1, 2, 3, 4, 5 \rbrace$ | Ordinal score for methodological depth and novelty. |
| `industrial_potential` | $I \in \lbrace 1, 2, 3, 4, 5 \rbrace$ | Ordinal score for proximity to real-world deployment. |
| `category` | `enum` (8 classes) | Assigned solely from paper content, independent of retrieval query. |
| `rationale` | `string` | One sentence citing the primary evidence for both scores. |

#### Scoring Rubric

Both dimensions use a 5-point ordinal scale anchored at **1, 3, and 5** (scores of **2** and **4** interpolate between adjacent anchors). To mitigate score inflation, the prompt instructs the model to place most papers in the **2–4** range, reserve **1** and **5** for strong evidence, and score ambiguous abstracts conservatively.

| Score | Technical Hardness ($H$): *Depth & Novelty* | Industrial Potential ($I$): *Deployment Readiness* |
| :---: | :--- | :--- |
| **1** | Survey, position paper, or straightforward application of an existing method. | Purely theoretical, or validated only in toy environments. |
| **3** | Solid incremental work with clear methodological improvement and comparative experiments. | Validated on real robots or realistic simulation; deployment still requires substantial engineering. |
| **5** | New paradigm, or rigorous theoretical guarantees backed by large-scale real-world validation. | Validated in a real industrial setting while addressing deployment constraints (safety, cost, reliability, cycle time). |

#### Closed Taxonomy

`Manipulation` · `Locomotion & Navigation` · `Foundation Models / VLA` · `Human-in-the-loop` · `Industrial RL & Control` · `Simulation & Sim2Real` · `Perception & Mapping` · `Other`

---

### 3. Ranking & Aggregation

* **Composite score:** $S = H + I \in [2, 10]$, weighting both dimensions equally.
* **Top 10:** Papers published within the 7-day window ending on the latest publication date are ranked by $S$ descending, with ties broken by higher $I$.
* **Monthly trend:** Papers are grouped by publication month to report category counts alongside the arithmetic means of $H$ and $I$.

---

## Limitations

> [!NOTE]
> Please interpret scores and trends with the following methodological constraints in mind:
> * **Abstract-only evidence:** Scores reflect claims made in the abstract rather than an audit of the full paper, experimental rigor, or code.
> * **Single automated rater:** Ratings come from a single LLM without human expert calibration or inter-rater reliability checks; re-running the same paper may shift a score by $\pm 1$ point.
> * **Ordinal scale:** $H$ and $I$ are ordinal variables, meaning $S$ and monthly arithmetic means serve as descriptive summaries rather than strict interval measurements.
> * **Sampling bias:** Keyword filters trade recall for precision (off-topic hits are typically tagged `Other`), and the daily cap samples `cs.RO` rather than covering it exhaustively. Monthly counts therefore reflect the tracked sample, not the entire field.
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
