# AI News Signal Extraction for Pairs Trading

An LLM-powered pipeline that extracts structured, per-ticker sentiment signals from Taiwan tech-supply-chain news, and rigorously tests whether those signals add predictive value to an existing statistical arbitrage pairs-trading strategy.

Built as an extension to [stat-arb-pairs-trading](https://github.com/benjamincheng18/stat-arb-pairs-trading) for the Polymer Capital Tech Expo 2026.

## Motivation

After finishing the [stat-arb-pairs-trading](https://github.com/benjamincheng18/stat-arb-pairs-trading) project, I was thinking about whether AI could boost the performance of the existing model. NLP came to mind right away. Stock price reflects everything — fundamentals, macroeconomic conditions, etc. In the short term, company-specific news is the most intuitive source that moves price. So I incorporated Claude Haiku 4.5 to analyze news scraped from TechNews (科技新報), one of the most widely used tech news sources in Taiwan, to test whether NLP-derived signals add value to the existing pairs-trading model.

## Overview

This project has two parts, working together:

1. **AI extraction layer (this repo):** scrapes Taiwan tech-supply-chain news, uses Claude Haiku to extract structured per-ticker events (event type, direction, confidence) from each article, then joins those events to the existing pairs-trading engine's spread/z-score data to test whether AI-flagged events predict subsequent spread movement.
2. **Quant engine ([stat-arb-pairs-trading](https://github.com/benjamincheng18/stat-arb-pairs-trading)):** the existing, independently-validated cointegration + Kalman-filter pairs-trading strategy this project builds on top of, unmodified.

The two repos are intentionally separate — this repo imports specific outputs (ticker universe, cointegrated pairs, spread series) from the quant engine as static data snapshots, rather than merging codebases, so each stands as independent evidence of its own methodology.

## Data

- **Source:** TechNews (technews.tw), scraped via category-archive pagination (no working site-wide search exists on the source, so coverage is category-scoped + client-side ticker-name matching).
- **Categories scraped:** semiconductor, component (electronic components + optical/光電科技 subcategory), pcnotebook (computer hardware) — 4 of the original 6 target industry groups; see Limitations.
- **Date range:** 2025-07-01 to 2026-06-30 (scoped to the regime where the underlying pairs-trading strategy shows tradeable signal, per stat-arb's walk-forward results).
- **Volume:** 2,706 unique articles scraped, 4,603 ticker-events extracted after filtering.
- **Ticker universe:** 57 Taiwan-listed tech-supply-chain tickers, with Chinese company names verified against TWSE/TPEx's official public ISIN lookup (not scraped/inferred).

## Methodology

**Module 0 — Scraping (`src/scrape_technews.py`):** Paginates TechNews category archives newest-first, matches article text against all 57 ticker names via substring search, fetches full article text for matches, and persists one `.txt` file per unique article plus a metadata index (ticker, title, url, publish date).

**Module 1 — Extraction (`src/extract_signals.py`):** For each article, calls Claude Haiku 4.5 via tool-use (schema-constrained generation) to extract one or more structured events — one call per article, returning a list of `{ticker, event_type, direction, confidence}` objects so articles discussing multiple tickers are captured correctly. Output is filtered to the known 57-ticker universe (removing incidental out-of-universe extractions), then the model-proposed event-type labels (1,441 distinct raw labels) are canonicalized into 15 fixed categories via a second Claude call.

**Module 2 — Signal Validation (`src/join_signals.py`):** Joins extracted events to the pairs-trading engine's daily spread/z-score series (persisted from `stat-arb-pairs-trading` for this date range) and tests whether an event's AI-assigned direction matches the pair's subsequent spread movement, across multiple reaction windows (1, 3, 5 trading days) and two z-score computation windows (60-day, 20-day).

**Validation approach:** an initial 1-day-window test showed apparent statistical significance (binomial test, p≈1e-9) against a naive 50% baseline. This was investigated further via two independent controls — a random-date control and a permutation test preserving the real event dates/tickers while shuffling direction labels — which revealed the true baseline confirmation rate (~63%) was driven by the underlying direction-label skew (~82% positive), not genuine predictive signal. This was independently confirmed with a second z-score window specification (20-day), which reproduced the null result exactly (real rate matched permutation baseline, p=0.512).

## Results

Across the primary 3-day and 5-day reaction windows, AI-flagged event direction matched subsequent spread movement roughly 50% of the time — no better than chance.

A shorter 1-day reaction window initially looked more promising: a naive binomial test against a 50% baseline returned p≈1e-9, suggesting strong significance. However, this test assumes direction labels are unbiased (50/50) — but the actual label distribution is ~82% positive. A significant p-value here only tells us the result differs from this assumed baseline; it does not establish that the underlying relationship is real, since the baseline itself may be wrong.

A permutation test — preserving the real event dates, tickers, and label distribution while randomizing which direction was assigned to each event — showed the true baseline confirmation rate is ~63%, not 50%. The real result (64.7%) was statistically indistinguishable from this permutation distribution (p=0.184), meaning AI-generated directions did not outperform randomly-shuffled directions once compared against the correct baseline.

Under rigorous testing, we conclude that a 60-day rolling z-score window with a 1-day reaction window does not support the original hypothesis that news-derived sentiment meaningfully predicts spread movement between a pair of stocks.

Even after changing the z-score window to 20 days, the same pattern held: the real confirmation rate (58.4%) matched the permutation baseline almost exactly (58.4% mean, p=0.512) — providing an independent confirmation that the earlier apparent signal was an artifact of label skew, not a specification-dependent fluke.

**This doesn't mean AI is useless in statistical pairs-trading arbitrage** — it means that this particular signal (ticker-level directional sentiment from news) doesn't add incremental predictive value to the existing price-based stat-arb model, at least at these time horizons and on this dataset.

## Limitations

- **Substring false-positive risk:** short, 2-character ticker names that are also common Chinese words can produce false-positive matches during scraping (e.g. 創意 / 3443.TW matched inside "創意生產力工具," an unrelated phrase meaning "creative productivity tool"). This was found to be self-correcting downstream — Claude's extraction step correctly excludes false-positive candidates when the ticker isn't meaningfully discussed — but the raw scrape-stage ticker tags should not be trusted without the extraction step.
- **Confidence score doesn't discriminate signal quality:** filtering to high-confidence extractions (>0.7, >0.8) did not meaningfully change results, suggesting the model's stated confidence tracks clarity of the article's language more than economic significance of the event.
- **~1% out-of-universe filtering and 10-pair effective sample size:** the 1-year date range (chosen to align with available news coverage) yields far fewer statistically significant cointegrated pairs (10) than the original stat-arb project's multi-year walk-forward study, due to reduced statistical power over a shorter window.
- **Category coverage gaps:** 2 of the original 6 ticker industry groups (other_electronics, distribution) have no dedicated TechNews category; those tickers are only matched incidentally within the 4 scoped categories, not comprehensively.
- **Data snapshot, not live-updating:** all data (articles, extracted signals, spread series) is a fixed snapshot for this date range. A production version would need live scraping/extraction to be useful for real-time arbitrage decisions.

## AI Tools Used

- **Claude (claude.ai chat interface):** used throughout for architecture design, code review, debugging, and validating statistical methodology — including catching a flawed naive significance test via permutation testing.
- **Claude Code:** used for repo diagnostics (verifying git state, confirming pipeline outputs), environment/HTML-structure checks during scraper development, and non-invasive additions to the existing `stat-arb-pairs-trading` codebase (persisting spread/cointegration data without modifying core pipeline logic — verified via `git diff --stat`).
- **Claude Haiku 4.5 (Anthropic API):** used in production, in `src/extract_signals.py`, to perform structured per-ticker event extraction from 2,706 scraped news articles via tool-use/schema-constrained generation, and to canonicalize the resulting event taxonomy.

## Setup

```bash
git clone https://github.com/benjamincheng18/ai-news-signal-extraction.git
cd ai-news-signal-extraction
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

Create a `.env` file in the repo root with your Anthropic API key:
```
ANTHROPIC_API_KEY=your-key-here
```

Run the pipeline in order:
```bash
python3 src/scrape_technews.py     # Module 0: scrape news articles
python3 src/extract_signals.py     # Module 1: extract structured signals via Claude Haiku
python3 src/join_signals.py        # Module 2: join signals to spread data, validate
```

Note: `src/join_signals.py` depends on `data/cointegrated_pairs_2025_2026.csv` and `data/spread_series_2025_2026.csv`, which are static snapshots copied from the [stat-arb-pairs-trading](https://github.com/benjamincheng18/stat-arb-pairs-trading) repo's `src/persist_spread_data.py` output, not regenerated by this repo.