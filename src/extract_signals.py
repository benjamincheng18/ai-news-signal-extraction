"""
Module 1: Extracts structured per-ticker events (event_type, direction,
confidence) from scraped TechNews articles using Claude Haiku via tool-use.
"""

import os
import time
import json
import pandas as pd
from pathlib import Path
from typing import Literal
from pydantic import BaseModel
import anthropic
from dotenv import load_dotenv
load_dotenv()
client = anthropic.Anthropic()
from src.universe import get_scoped_universe

# ---- Schema ----

class TickerEvent(BaseModel):
    ticker: str
    event_type: str
    direction: Literal[-1, 0, 1]
    confidence: float

class ArticleExtraction(BaseModel):
    events: list[TickerEvent]


# ---- Config ----

MODEL = "claude-haiku-4-5-20251001"
RAW_ARTICLES_DIR = str(Path(__file__).resolve().parent.parent / "data" / "raw_articles")
METADATA_PATH = str(Path(__file__).resolve().parent.parent / "data" / "raw_articles" / "metadata_index.csv")
OUTPUT_PATH = str(Path(__file__).resolve().parent.parent / "data" / "extracted_signals.csv")
MAX_RETRIES = 3


EXTRACTION_TOOL = {
    "name": "record_ticker_events",
    "description": "Record structured events extracted from a news article, one entry per ticker discussed.",
    "input_schema": {
        "type": "object",
        "properties": {
            "events": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "ticker": {"type": "string"},
                        "event_type": {
                            "type": "string",
                            "description": "A short category label for the event, e.g. earnings_beat, supply_disruption, capacity_expansion, order_win. Propose a label that best fits — don't force-fit an unrelated category."
                        },
                        "direction": {
                            "type": "integer",
                            "enum": [-1, 0, 1],
                            "description": "-1 negative, 0 neutral, 1 positive impact on this ticker specifically"
                        },
                        "confidence": {
                            "type": "number",
                            "description": "0.0 to 1.0, how confident you are in this direction/event assessment"
                        }
                    },
                    "required": ["ticker", "event_type", "direction", "confidence"]
                }
            }
        },
        "required": ["events"]
    }
}


def load_article_text(filename: str) -> str:
    """Inputs: filename -> raw article text from disk"""
    with open(f"{RAW_ARTICLES_DIR}/{filename}", "r", encoding="utf-8") as file:
        content = file.read()
        return content
        

def extract_from_article(article_text: str, candidate_tickers: list[str]) -> ArticleExtraction:
    prompt = f"""Here is a news article. The following tickers were matched by
company name appearing somewhere in this article: {candidate_tickers}

ONLY report events for tickers in this exact list: {candidate_tickers}.
Do NOT report events for any other company, ticker, or entity, even if
mentioned in the article, even if you recognize it — only tickers from
the list above are valid. If none of the candidates are meaningfully
discussed, return an empty events list.

Article:
{article_text}
"""

    for attempt in range(MAX_RETRIES):
        try:
            response = client.messages.create(
                model=MODEL,
                max_tokens=1024,
                tools=[EXTRACTION_TOOL],
                tool_choice={"type": "tool", "name": "record_ticker_events"},
                messages=[
                    {"role": "user", "content": prompt}
                ]
            )
            tool_call = response.content[0]
            extracted_data = tool_call.input
            return ArticleExtraction(**extracted_data)

        except Exception as e:
            print(f"Attempt {attempt + 1} failed: {e}")
            if attempt < MAX_RETRIES - 1:
                time.sleep(2)
            else:
                raise


def process_all_articles(metadata_df: pd.DataFrame) -> pd.DataFrame:
    grouped = metadata_df.groupby('filename').agg({
        'tickers': list,
        'title': 'first',
        'url': 'first',
        'publish_date': 'first'
    }).reset_index()

    results = []
    for i, row in grouped.iterrows():
        text = load_article_text(row["filename"])
        llm_answer = extract_from_article(text, row["tickers"])
        for event in llm_answer.events:
            results.append({
                "ticker": event.ticker,
                "event_type": event.event_type,
                "direction": event.direction,
                "confidence": event.confidence,
                "url": row["url"],
                "publish_date": row["publish_date"]
            })

        if i%50 == 0:
            print(f"Current read: {i}/{len(grouped)} rows.")
            pd.DataFrame(results).to_csv(OUTPUT_PATH)
            
    return pd.DataFrame(results)


def save_signals(df: pd.DataFrame, output_path: str):
    df.to_csv(output_path, index=False)


if __name__ == "__main__":
    metadata_df = pd.read_csv(METADATA_PATH)
    signals_df = process_all_articles(metadata_df)

    valid_tickers = set(get_scoped_universe()['ticker'])
    before_count = len(signals_df)
    signals_df = signals_df[signals_df['ticker'].isin(valid_tickers)]
    dropped = before_count - len(signals_df)
    print(f"Dropped {dropped} rows with tickers outside the known universe.")

    save_signals(signals_df, OUTPUT_PATH)
    print(f"Done. Total extracted events: {len(signals_df)}")