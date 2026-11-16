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

每日自动追踪 arXiv 上 **Robotics / Human-in-the-loop / Industrial RL** 方向的最新论文，
由 LLM 生成中文摘要，并按「技术硬度」和「工业应用潜力」打分（1–5）。

"""

# Fixed colour per category so a category keeps its colour as data changes.
PALETTE = ["#4c78a8", "#f58518", "#54a24b", "#e45756", "#b279a2", "#72b7b2", "#eeca3b", "#9d9d9d"]
CATEGORY_COLOR = {key: PALETTE[i] for i, (key, _, _) in enumerate(config.CATEGORIES)}
INK = "#6e7781"  # readable on both GitHub light and dark backgrounds


def _cell(text: str) -> str:
    return " ".join(str(text).split()).replace("|", "\\|")


def _total(paper: dict) -> int:
    a = paper["analysis"]
    return a["technical_hardness"] + a["industrial_potential"]


def _table(papers: list[dict], with_date: bool = True) -> str:
    head = ["日期"] if with_date else []
    head += ["论文", "方向", "硬度", "工业", "摘要"]
    lines = ["| " + " | ".join(head) + " |", "|" + "|".join([" --- "] * len(head)) + "|"]
    for p in papers:
        a = p["analysis"]
        row = [p["published"][5:]] if with_date else []
        row += [
            f"[{_cell(p['title'])}]({p['url']})",
            config.CATEGORY_ZH.get(a["category"], a["category"]),
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
    for key, _, name in config.CATEGORIES:
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
        f"# {month} 论文归档",
        "",
        f"共 {len(papers)} 篇 · 平均技术硬度 "
        f"{_mean([p['analysis']['technical_hardness'] for p in papers]):.2f} · 平均工业潜力 "
        f"{_mean([p['analysis']['industrial_potential'] for p in papers]):.2f}",
        "",
        "[← 返回首页](../README.md)",
    ]
    for key, zh, _ in config.CATEGORIES:
        group = [p for p in papers if p["analysis"]["category"] == key]
        if not group:
            continue
        group.sort(key=lambda p: (-_total(p), p["published"]), reverse=False)
        lines += ["", f"## {zh}（{len(group)}）", "", _table(group)]
    config.ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    (config.ARCHIVE_DIR / f"{month}.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _readme_body(papers: list[dict], months: dict[str, list[dict]]) -> str:
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    out = [
        f"> 最近更新：{today}（UTC） · 已收录 {len(papers)} 篇 · 模型：`{config.LLM_MODEL}`",
        "",
        "## 📈 技术趋势",
        "",
        "![Monthly research trend](assets/trend.svg)",
    ]
    if not papers:
        return "\n".join(out + ["", "_暂无数据，等待首次运行。_"])

    latest = date.fromisoformat(max(p["published"] for p in papers))
    since = (latest - timedelta(days=config.README_TOP_DAYS - 1)).isoformat()
    top = sorted(
        (p for p in papers if p["published"] >= since),
        key=lambda p: (-_total(p), -p["analysis"]["industrial_potential"], p["id"]),
    )[: config.README_TOP_N]
    out += ["", f"## 🔥 近 {config.README_TOP_DAYS} 天精选 Top {config.README_TOP_N}", "",
            "按「技术硬度 + 工业潜力」总分排序。", "", _table(top)]

    out += ["", "## 🆕 最新论文"]
    days = sorted({p["published"] for p in papers}, reverse=True)[: config.README_RECENT_DAYS]
    for day in days:
        group = sorted((p for p in papers if p["published"] == day), key=lambda p: -_total(p))
        out += ["", f"### {day}（{len(group)} 篇）", "", _table(group, with_date=False)]

    out += ["", "## 🗂 按月归档", "",
            "| 月份 | 论文数 | 平均技术硬度 | 平均工业潜力 | 最热方向 |", "| --- | --- | --- | --- | --- |"]
    for month in sorted(months, reverse=True):
        group = months[month]
        hottest = Counter(p["analysis"]["category"] for p in group).most_common(1)[0][0]
        out.append(
            f"| [{month}](archive/{month}.md) | {len(group)} "
            f"| {_mean([p['analysis']['technical_hardness'] for p in group]):.2f} "
            f"| {_mean([p['analysis']['industrial_potential'] for p in group]):.2f} "
            f"| {config.CATEGORY_ZH.get(hottest, hottest)} |"
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
        text = README_HEADER
    if START in text and END in text:
        # Only the marked block is regenerated; anything around it is kept.
        text = text[: text.index(START)] + body + text[text.index(END) + len(END):]
    else:
        text = text.rstrip() + "\n\n" + body + "\n"
    config.README_FILE.write_text(text, encoding="utf-8")
