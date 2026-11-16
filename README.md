# Awesome Physical AI

A daily, automatically updated tracker of new arXiv papers on **Robotics / Human-in-the-loop /
Industrial RL**. Each paper is summarised by an LLM and scored from 1 to 5 on **technical
hardness** and **industrial potential**.

<!-- PAPERS:START -->
> Last updated: 2026-11-16 (UTC) · 0 papers tracked · Model: `claude-opus-5-5`

## 📈 Trends

![Monthly research trend](assets/trend.svg)

_No data yet. Waiting for the first run._
<!-- PAPERS:END -->

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
