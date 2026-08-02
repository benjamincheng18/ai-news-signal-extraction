"""
Module 2: Joins Module 1's extracted AI signals to stat-arb's persisted
spread/z-score series, to test whether AI-flagged events correlate with
subsequent spread movement in the direction implied by the event.
"""

import pandas as pd
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
COINTEGRATED_PAIRS_PATH = DATA_DIR / "cointegrated_pairs_2025_2026.csv"
SPREAD_SERIES_PATH = DATA_DIR / "spread_series_2025_2026.csv"
SIGNALS_PATH = DATA_DIR / "extracted_signals.csv"
OUTPUT_PATH = DATA_DIR / "event_spread_reactions.csv"

REACTION_WINDOW_DAYS = 3  # trading days after event to measure spread reaction


def load_validated_pairs() -> pd.DataFrame:
    pairs = pd.read_csv(COINTEGRATED_PAIRS_PATH)
    return pairs[pairs["cointegrated"] == True].reset_index(drop=True)


def get_pair_side(ticker: str, pair_row: pd.Series) -> str:
    """
    Given a ticker and a pair row (stock1, stock2), returns 'stock1' or 'stock2'
    depending on which side of the pair this ticker is.
    """
    if ticker == pair_row["stock1"]:
        return "stock1"
    elif ticker == pair_row["stock2"]:
        return "stock2"
    else:
        raise ValueError(f"{ticker} is not in this pair")


def expected_spread_direction(event_direction: int, side: str) -> int:
    """
    Given the event's direction (-1/0/1) and which side of the pair the
    ticker is on, returns the EXPECTED direction of spread/zscore movement:
    +1 = expect spread to rise, -1 = expect spread to fall, 0 = no expectation.

    stock1 positive news -> spread should rise  (direction unchanged)
    stock1 negative news -> spread should fall  (direction unchanged)
    stock2 positive news -> spread should fall  (direction FLIPPED)
    stock2 negative news -> spread should rise  (direction FLIPPED)
    """
    if event_direction == 0:
        return 0
    if side == "stock1":
        return event_direction
    else:  # stock2
        return -event_direction


from datetime import date
def get_spread_reaction(pair_row: pd.Series, spread_series: pd.DataFrame,
                          event_date: pd.Timestamp, window_days: int) -> dict:
    filtered_series = spread_series[
        (spread_series["stock1"] == pair_row["stock1"]) & (spread_series["stock2"] == pair_row["stock2"])
    ].sort_values(by="date", ascending=True).reset_index(drop=True)

    if filtered_series.empty:
        return None

    series_start = filtered_series["date"].min()
    series_end = filtered_series["date"].max()
    if event_date < series_start or event_date > series_end:
        return None

    before_candidates = filtered_series[filtered_series["date"] <= event_date]
    if before_candidates.empty:
        return None
    before_idx = before_candidates.index[-1]

    after_idx = before_idx + window_days
    if after_idx >= len(filtered_series):
        return None

    before = filtered_series.iloc[before_idx]
    after = filtered_series.iloc[after_idx]

    return {
        "zscore_before": before["zscore"],
        "zscore_after": after["zscore"],
        "zscore_change": after["zscore"] - before["zscore"]
    }


def join_signals_to_spread(signals_df: pd.DataFrame, pairs_df: pd.DataFrame,
                             spread_series: pd.DataFrame,
                             window_days: int = REACTION_WINDOW_DAYS) -> pd.DataFrame:
    results = []

    for _, event in signals_df.iterrows():
        matching_pairs = pairs_df[
            (pairs_df["stock1"] == event["ticker"]) | (pairs_df["stock2"] == event["ticker"])
        ]

        for _, pair_row in matching_pairs.iterrows():
            side = get_pair_side(event["ticker"], pair_row)
            expected_dir = expected_spread_direction(event["direction"], side)

            reaction = get_spread_reaction(
                pair_row, spread_series, pd.Timestamp(event["publish_date"]), window_days
            )
            if reaction is None or reaction["zscore_change"] is None:
                continue  # event date outside persisted series range, skip

            if expected_dir == 0:
                direction_confirmed = None
            elif (reaction["zscore_change"] > 0) == (expected_dir > 0):
                direction_confirmed = True
            else:
                direction_confirmed = False


            results.append({
                "ticker": event["ticker"],
                "paired_with": pair_row["stock2"] if side == "stock1" else pair_row["stock1"],
                "event_type_canonical": event["event_type_canonical"],
                "direction": event["direction"],
                "confidence": event["confidence"],
                "event_date": event["publish_date"],
                "zscore_before": reaction["zscore_before"],
                "zscore_after": reaction["zscore_after"],
                "zscore_change": reaction["zscore_change"],
                "expected_direction": expected_dir,
                "direction_confirmed": direction_confirmed
            })

    return pd.DataFrame(results)


if __name__ == "__main__":
    pairs_df = load_validated_pairs()
    spread_series = pd.read_csv(SPREAD_SERIES_PATH, parse_dates=["date"])
    signals_df = pd.read_csv(SIGNALS_PATH, parse_dates=["publish_date"])

    reactions_df = join_signals_to_spread(signals_df, pairs_df, spread_series)
    reactions_df.to_csv(OUTPUT_PATH, index=False)
    print(f"Done. {len(reactions_df)} event-pair reactions computed.")
    if len(reactions_df) > 0:
        print(reactions_df["direction_confirmed"].value_counts())