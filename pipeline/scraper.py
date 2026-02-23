"""Simplified room.nl recently-rented scraper.

Replaces the Selenium-stealth + effect_py based WebUser/RoomNL classes with a
straightforward Playwright approach. The core logic (pd.read_html -> clean ->
dedup -> store) is preserved from the original room_nl.py.
"""

from __future__ import annotations

import io
import logging
import re
from pathlib import Path
from typing import Literal

import pandas as pd
import polars as pl

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
PARQUET_PATH = DATA_DIR / "recently_rented.parquet"

# robust pattern: grab everything up to the LAST " <digits...>" token
ADDRESS_PATTERN = r"^(?P<street>[^\d]*\S)\s+(?P<number>\d(?:.+)*)\s*$"

RENAME_EN: dict[str, str] = {
    "Current address": "current_address",
    "City": "city",
    "Type of room": "type_of_room",
    "Number of reactions": "num_reactions",
    "Contract date ↑": "contract_date",
    "Allocation based on (* is with priority)": "allocation_type",
}

RENAME_NL: dict[str, str] = {
    "Adres": "current_address",
    "Plaats": "city",
    "Kamertype": "type_of_room",
    "Aantal reacties": "num_reactions",
    "Contractdatum": "contract_date",
    "Toewijzing o.b.v. (* is met voorrang)": "allocation_type",
}


def parse_registration_time(s: str, language: Literal["english", "dutch"]) -> int | None:
    """Parse 'Registration time: X years, Y months, Z days' into total days."""
    pattern_en = re.compile(
        r"Registration time:\s*"
        r"(?:([0-9]+)\s*years?)?"
        r"(?:,\s*)?"
        r"(?:([0-9]+)\s*months?)?"
        r"(?:,\s*)?"
        r"(?:([0-9]+)\s*days?)?",
        re.IGNORECASE,
    )
    pattern_nl = re.compile(
        r"Inschrijfduur:\s*"
        r"(?:([0-9]+)\s*jaar)?"
        r"(?:,\s*)?"
        r"(?:([0-9]+)\s*maanden?)?"
        r"(?:,\s*)?"
        r"(?:([0-9]+)\s*dagen?)?",
        re.IGNORECASE,
    )

    m = (pattern_en if language == "english" else pattern_nl).search(s)
    if not m:
        return None

    years = int(m.group(1)) if m.group(1) else 0
    months = int(m.group(2)) if m.group(2) else 0
    days = int(m.group(3)) if m.group(3) else 0
    return years * 365 + months * 30 + days


def fetch_recently_rented_html() -> str:
    """Fetch the recently-rented page HTML using Playwright (headless)."""
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.on("console", lambda _: None)
        page.on("pageerror", lambda _: None)
        page.goto("https://www.roommatch.nl/en/recently-rented")
        page.wait_for_load_state("networkidle")
        # Wait for Angular to render the table into the DOM
        page.wait_for_selector("table", timeout=30_000)
        html = page.content()
        browser.close()

    return html


def clean_table(
    html: str,
    language: Literal["english", "dutch"] = "english",
) -> pl.DataFrame | None:
    """Parse HTML table and clean into the standard schema."""
    tables = pd.read_html(io.StringIO(html))
    if not tables:
        logger.info("No tables found in HTML")
        return None

    df = pl.from_pandas(tables[0])
    header_map = RENAME_EN if language == "english" else RENAME_NL
    alloc_prefix = "Registration time:" if language == "english" else "Inschrijfduur:"

    df = (
        df.rename({c: c.strip() for c in df.columns})
        .rename(header_map)
        .with_columns(
            pl.col("current_address").str.extract_groups(ADDRESS_PATTERN).alias("addr_parts")
        )
        .with_columns(
            pl.col("addr_parts").struct.field("street").str.strip_chars().alias("street"),
            pl.col("addr_parts").struct.field("number").str.strip_chars().alias("street_number"),
        )
        .drop("addr_parts", "current_address")
        .filter(pl.col("allocation_type").str.starts_with(alloc_prefix))
        .cast({"num_reactions": pl.Int64})
        .with_columns(pl.col("allocation_type").str.ends_with("*").alias("priority"))
        .with_columns(
            pl.struct(["allocation_type"])
            .map_elements(
                lambda r: parse_registration_time(r["allocation_type"], language),
                return_dtype=pl.Int64,
            )
            .alias("registration_time")
        )
        .with_columns(
            pl.col("contract_date").str.strptime(pl.Date, format="%d-%m-%Y", strict=False)
        )
        .filter(pl.col("registration_time").is_not_null())
        .drop("allocation_type")
    )

    return df


def store_parquet(df: pl.DataFrame, path: Path = PARQUET_PATH) -> None:
    """Append new rows to the parquet file, deduplicating on all columns."""
    path.parent.mkdir(parents=True, exist_ok=True)

    if path.exists():
        existing = pl.read_parquet(path)
        combined = pl.concat([existing, df.select(existing.columns)]).unique()
        combined.write_parquet(path)
        logger.info(f"Appended {len(df)} rows, {len(combined)} total after dedup")
    else:
        df.write_parquet(path)
        logger.info(f"Created {path} with {len(df)} rows")


def scrape(language: Literal["english", "dutch"] = "english") -> pl.DataFrame | None:
    """Full scrape pipeline: fetch -> clean -> store -> return."""
    html = fetch_recently_rented_html()
    df = clean_table(html, language)
    if df is not None and len(df) > 0:
        store_parquet(df)
    return df


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    result = scrape()
    if result is not None:
        print(result)
