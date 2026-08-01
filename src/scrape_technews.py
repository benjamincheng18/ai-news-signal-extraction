"""
Module 0: Scrapes TechNews category archives for articles matching the
4-industry ticker universe (from universe.py), 2025-01-01 to 2026-06-30.
"""

import requests
from bs4 import BeautifulSoup
import pandas as pd
import re
import time
from datetime import datetime
from pathlib import Path
import hashlib
import os

from universe import get_scoped_universe

CATEGORY_SLUGS = {
    "semiconductor": "semiconductor",
    "electronic_components": "component",
    "computer_hardware": "pcnotebook",
    "optical": "component/%e5%85%89%e9%9b%bb%e7%a7%91%e6%8a%80",
}

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
                   'AppleWebKit/537.36 (KHTML, like Gecko) '
                   'Chrome/120.0.0.0 Safari/537.36'
}

START_DATE = datetime(2025, 1, 1)
END_DATE = datetime(2026, 6, 30)
REQUEST_DELAY_SECONDS = 0.5


def parse_publish_date(raw_text: str) -> datetime:
    """Inputs: raw date string '2026 年 07 月 28 日 21:50' -> datetime"""
    y, m, d, h, mi = re.findall(r'\d+', raw_text)
    return datetime(int(y), int(m), int(d), int(h), int(mi))


def fetch_archive_page(category_slug: str, page_num: int) -> str:
    if page_num == 1:
        url = f"https://technews.tw/category/{category_slug}/"
    else:
        url = f"https://technews.tw/category/{category_slug}/page/{page_num}/"

    time.sleep(REQUEST_DELAY_SECONDS)
    response = requests.get(url, headers=HEADERS)

    if response.status_code != 200 or len(response.text) < 5000:
        print(f"WARNING: suspicious response for page {page_num} "
              f"(status={response.status_code}, length={len(response.text)}) — "
              f"possible block. Retrying once after 5s.")
        time.sleep(5)
        response = requests.get(url, headers=HEADERS)

    return response.text


def parse_article_listing(html: str) -> list[dict]:
    """Inputs: archive page HTML -> list of {title, url, publish_date}"""
    soup = BeautifulSoup(html, 'html.parser')
    entries = soup.select('article')

    results = []
    for entry in entries:
        title_tag = entry.select_one('h1.entry-title a')
        title = title_tag.get_text(strip=True)
        url = title_tag['href']

        date_label = entry.find('span', class_='head', string='發布日期')
        date_value = date_label.find_next_sibling('span', class_='body')
        date_text = date_value.get_text(strip=True)
        publish_date = parse_publish_date(date_text)

        results.append({'title': title, 'url': url, 'publish_date': publish_date})

    return results


def fetch_full_article(url: str) -> str:
    """Inputs: article URL -> clean body text"""
    headers = HEADERS
    time.sleep(REQUEST_DELAY_SECONDS)
    response = requests.get(url, headers=headers)
    soup = BeautifulSoup(response.text, 'html.parser')

    content_div = soup.select_one('div.entry-content div.indent')
    paragraphs = content_div.select('p')  # all <p> tags inside, as a list
    article_text = '\n'.join(p.get_text(strip=True) for p in paragraphs)

    return article_text


def matches_ticker(text: str, scoped_universe: pd.DataFrame) -> list[str]:
    """Inputs: article text, universe DataFrame -> list of matched tickers"""
    matching_tickers = []
    for index, row in scoped_universe.iterrows():
        if row["chinese_name"] in text:
            matching_tickers.append(row["ticker"])
    return matching_tickers


def scrape_category(category_slug: str, scoped_universe: pd.DataFrame,
                     start_date: datetime, end_date: datetime,
                     checkpoint_path: str = None) -> list[dict]:
    results = []
    stop = False
    MAX_PAGES_SAFETY_CAP = 1500

    for page_num in range(1, MAX_PAGES_SAFETY_CAP + 1):
        html = fetch_archive_page(category_slug, page_num)
        listings = parse_article_listing(html)

        if not listings:
            debug_path = f"data/raw_articles/_debug_empty_page_{page_num}.html"
            with open(debug_path, "w", encoding="utf-8") as f:
                f.write(html)
            print(f"[{category_slug}] page {page_num}: 0 listings — "
                  f"raw HTML saved to {debug_path} for inspection")
            break

        print(f"[{category_slug}] page {page_num}: {len(listings)} listings, "
              f"{len(results)} matches so far")

        for listing in listings:
            if listing["publish_date"] > end_date:
                continue
            elif listing["publish_date"] < start_date:
                print("Reached the boundary, stop after this page.")
                stop = True
                continue
            else:
                article = fetch_full_article(listing["url"])
                match = matches_ticker(article, scoped_universe)
                if match:
                    for ticker in match:
                        results.append({
                            "tickers": ticker,
                            "title": listing["title"],
                            "url": listing["url"],
                            "publish_date": listing["publish_date"],
                            "text": article
                        })

        if checkpoint_path:
            pd.DataFrame(results).to_csv(checkpoint_path, index=False)

        if stop:
            return results

    print(f"WARNING: hit MAX_PAGES_SAFETY_CAP ({MAX_PAGES_SAFETY_CAP}) "
          f"without reaching start_date — results may be incomplete.")
    return results


def save_articles(articles: list[dict], output_dir: str):
    """Side effects: writes .txt per article + metadata_index.csv, deduped by URL"""
    deduped = list({(a['url'], a['tickers']): a for a in articles}.values())

    Path(output_dir).mkdir(parents=True, exist_ok=True)
    metadata = []

    for article in deduped:
        filename = hashlib.md5(article['url'].encode()).hexdigest() + ".txt"
        filepath = Path(output_dir) / filename

        with open(filepath, "w", encoding="utf-8") as f:
            f.write(article['text'])

        metadata.append({
            "filename": filename,
            "tickers": article['tickers'],
            "title": article['title'],
            "url": article['url'],
            "publish_date": article['publish_date']
        })

    index_path = Path(output_dir) / "metadata_index.csv"
    metadata_df = pd.DataFrame(metadata)

    if index_path.exists():
        existing = pd.read_csv(index_path)
        metadata_df = pd.concat([existing, metadata_df]).drop_duplicates(subset='filename', keep='last')

    metadata_df.to_csv(index_path, index=False)


def rebuild_ticker_associations(raw_articles_dir: str, universe: pd.DataFrame) -> pd.DataFrame:
    """
    Fixes the dedup bug by re-deriving full ticker matches per article
    directly from saved text files, instead of trusting the lossy
    metadata_index.csv ticker column.
    """
    txt_files = [f for f in os.listdir(raw_articles_dir) if f.endswith('.txt')]
    old_metadata = pd.read_csv(f"{raw_articles_dir}/metadata_index.csv")

    rows = []
    for filename in txt_files:
        with open(f"{raw_articles_dir}/{filename}", "r", encoding="utf-8") as f:
            text = f.read()
        matched = matches_ticker(text, universe)
        meta_row = old_metadata[old_metadata['filename'] == filename]
        if meta_row.empty:
            continue  # shouldn't happen, but skip defensively
        for ticker in matched:
            rows.append({
                "filename": filename,
                "tickers": ticker,
                "title": meta_row.iloc[0]['title'],
                "url": meta_row.iloc[0]['url'],
                "publish_date": meta_row.iloc[0]['publish_date']
            })

    return pd.DataFrame(rows)


if __name__ == "__main__":
    universe = get_scoped_universe()
    START_DATE = datetime(2025, 7, 1)
    END_DATE = datetime(2026, 6, 30)

    remaining_categories = {
        "electronic_components": "component",
        "computer_hardware": "pcnotebook",
        "optical": "component/%e5%85%89%e9%9b%bb%e7%a7%91%e6%8a%80",
    }

    for industry, slug in remaining_categories.items():
        print(f"=== Starting category: {industry} ({slug}) ===")
        results = scrape_category(
            slug, universe, START_DATE, END_DATE,
            checkpoint_path=f"data/raw_articles/{industry}_checkpoint.csv"
        )
        save_articles(results, "data/raw_articles")
        print(f"=== Done with {industry}. Total matches: {len(results)} ===")