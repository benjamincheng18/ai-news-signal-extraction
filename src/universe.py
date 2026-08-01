from pathlib import Path

import pandas as pd

TICKER_NAME_MAP_PATH = Path(__file__).parent / "ticker_name_map.csv"


def get_ticker_universe() -> dict[str, list[str]]:
    return {
        "semiconductor": [
            "2330.TW", "2454.TW", "3711.TW", "2303.TW",
            "2408.TW", "2344.TW", "5274.TWO", "3443.TW", "6223.TWO",
            "8299.TWO", "6488.TWO", "6515.TW", "3661.TW", "3189.TW",
            "6770.TW", "2449.TW", "2379.TW", "2337.TW",
            "3034.TW", "6239.TW", "3105.TWO", "6415.TW",
        ],
        "electronic_components": [
            "2308.TW", "2327.TW", "2383.TW", "3037.TW", "2368.TW",
            "2059.TW", "4958.TW", "3653.TW", "8046.TW", "6274.TWO",
            "2313.TW", "3044.TW", "3533.TW", "2492.TW",
        ],
        "computer_hardware": [
            "2382.TW", "3017.TW", "6669.TW", "2357.TW", "3231.TW",
            "2301.TW", "2395.TW", "2356.TW", "2376.TW", "4938.TW",
        ],
        "other_electronics": [
            "2317.TW", "2360.TW", "3665.TW", "2404.TW", "6139.TW",
        ],
        "optical": [
            "3008.TW", "3481.TW", "8069.TWO",
        ],
        "networking": [
            "2345.TW", "3081.TWO",
        ],
        "distribution": [
            "3036.TW",
        ],
    }


def get_scoped_universe() -> pd.DataFrame:
    names = pd.read_csv(TICKER_NAME_MAP_PATH)[["ticker", "name"]].rename(
        columns={"name": "chinese_name"}
    )

    universe = get_ticker_universe()
    industries = pd.DataFrame(
        [
            {"ticker": ticker, "industry": industry}
            for industry, tickers in universe.items()
            for ticker in tickers
        ]
    )

    df = names.merge(industries, on="ticker")
    return df.reset_index(drop=True)