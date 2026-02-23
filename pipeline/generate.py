"""Generate JSON data artifacts for the static frontend.

Scrapes the latest data from roommatch.nl, fits the GP model,
and writes three JSON files into site/static/data/:
  - recently_rented.json  (full table)
  - predictions.json      (daily GP predictions + confidence intervals)
  - stats.json            (aggregated stats by city and room type)
"""

from __future__ import annotations

import datetime as dt
import json
import logging
from pathlib import Path
from typing import Any

import polars as pl
from rich.console import Console
from rich.table import Table

from pipeline.roomnl_model import fit_gp_with_calendar, predict_daily
from pipeline.scraper import scrape

MIN_ROWS_FOR_GP = 20

logging.disable(logging.CRITICAL)  # silence noisy library loggers

console = Console()

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
OUTPUT_DIR = ROOT / "site" / "static" / "data"

PARQUET_PATH = DATA_DIR / "recently_rented.parquet"
SEED_PATH = OUTPUT_DIR / "recently_rented.json"


def load_data() -> pl.DataFrame:
    """Load recently_rented from parquet or seed JSON."""
    if PARQUET_PATH.exists():
        return pl.read_parquet(PARQUET_PATH)

    if SEED_PATH.exists():
        raw = json.loads(SEED_PATH.read_text())
        return pl.DataFrame(raw).with_columns(
            pl.col("contract_date").str.strptime(pl.Date, "%Y-%m-%d")
        )

    msg = (
        f"No data found at {PARQUET_PATH} or {SEED_PATH}. "
        "Run the scraper first or provide seed data."
    )
    raise FileNotFoundError(msg)


def compute_stats(df: pl.DataFrame) -> list[dict[str, Any]]:
    """Aggregate stats by city and room type."""
    stats = (
        df.group_by("city", "type_of_room")
        .agg(
            count=pl.len(),
            median_reg_days=pl.col("registration_time").median(),
            mean_reg_days=pl.col("registration_time").mean(),
            min_reg_days=pl.col("registration_time").min(),
            max_reg_days=pl.col("registration_time").max(),
            median_reactions=pl.col("num_reactions").median(),
            pct_priority=pl.col("priority").mean() * 100,
        )
        .sort("city", "type_of_room")
    )
    return stats.to_dicts()


def _fit_and_predict(
    df: pl.DataFrame,
    horizon_days: int,
    city: str | None,
    type_of_room: str | None,
) -> list[dict[str, Any]]:
    """Fit one GP on a subset and return prediction dicts with city/type_of_room labels."""
    model_df = df.select("contract_date", "registration_time").drop_nulls()
    if len(model_df) < MIN_ROWS_FOR_GP:
        return []

    try:
        gp, scaler, _ = fit_gp_with_calendar(model_df)
    except Exception:
        return []

    today = dt.date.today()
    start: dt.date = model_df.get_column("contract_date").min()  # type: ignore[assignment]
    end = today + dt.timedelta(days=horizon_days)

    preds = predict_daily(gp, scaler, start, end)

    rows = preds.with_columns(
        pl.col("contract_date").cast(pl.Utf8),
        pl.col("pred_mean").round(1),
        pl.col("pred_lo").round(1),
        pl.col("pred_hi").round(1),
    ).to_dicts()

    for row in rows:
        row["city"] = city
        row["type_of_room"] = type_of_room

    return rows


def compute_all_predictions(
    df: pl.DataFrame,
    horizon_days: int = 730,
) -> list[dict[str, Any]]:
    """Fit GP per global / per-city / per-(city, type_of_room) subset and return all predictions."""
    results: list[dict[str, Any]] = []

    # Global model
    results.extend(_fit_and_predict(df, horizon_days, None, None))

    # Per-city models
    for city in sorted(df["city"].unique().to_list()):
        city_df = df.filter(pl.col("city") == city)
        results.extend(_fit_and_predict(city_df, horizon_days, city, None))

    # Per-(city, type_of_room) models
    combos = df.select("city", "type_of_room").unique().sort("city", "type_of_room")
    for row in combos.iter_rows(named=True):
        combo_df = df.filter(
            (pl.col("city") == row["city"]) & (pl.col("type_of_room") == row["type_of_room"])
        )
        results.extend(
            _fit_and_predict(combo_df, horizon_days, row["city"], row["type_of_room"])
        )

    return results


def serialize_recently_rented(df: pl.DataFrame) -> list[dict[str, Any]]:
    """Convert the recently_rented DataFrame to JSON-serializable dicts."""
    return df.with_columns(pl.col("contract_date").cast(pl.Utf8)).to_dicts()


def generate(horizon_days: int = 730) -> None:
    """Main entry point: scrape fresh data, compute artifacts, write JSON files."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    console.print()
    console.rule("[bold]roomnl-model generate[/bold]")
    console.print()

    # ── Step 1: Scrape ──────────────────────────────────────────────────────
    console.print("[bold cyan][1/4][/bold cyan] Scraping roommatch.nl...", end=" ")
    scraped_rows = 0
    try:
        result = scrape()
        scraped_rows = len(result) if result is not None else 0
        console.print(f"[green]✓[/green] {scraped_rows} rows fetched")
    except Exception as exc:
        short = str(exc).split("\n")[0][:120]
        console.print(f"[yellow]⚠ failed ({short}), using existing data[/yellow]")

    # ── Step 2: Load ────────────────────────────────────────────────────────
    console.print("[bold cyan][2/4][/bold cyan] Loading data...", end=" ")
    df = load_data()
    date_min = str(df["contract_date"].min())
    date_max = str(df["contract_date"].max())
    console.print(f"[green]✓[/green] {len(df):,} rows  [dim]({date_min} → {date_max})[/dim]")

    # ── Step 3: Fit GP + predict ─────────────────────────────────────────────
    console.print("[bold cyan][3/4][/bold cyan] Fitting GP models (global + per-city + per-combo)...")
    preds = compute_all_predictions(df, horizon_days)
    n_models = len({(p["city"], p["type_of_room"]) for p in preds})
    n_rows = len(preds)
    console.print(f"  [green]✓[/green] {n_models} models, {n_rows:,} prediction rows")

    # ── Step 4: Write JSON ───────────────────────────────────────────────────
    console.print("[bold cyan][4/4][/bold cyan] Writing JSON files...", end=" ")

    rr_data = serialize_recently_rented(df)
    (OUTPUT_DIR / "recently_rented.json").write_text(json.dumps(rr_data, indent=2))

    (OUTPUT_DIR / "predictions.json").write_text(json.dumps(preds))

    stats = compute_stats(df)
    (OUTPUT_DIR / "stats.json").write_text(json.dumps(stats, indent=2))

    console.print("[green]✓[/green]")

    # ── Summary ──────────────────────────────────────────────────────────────
    console.print()
    summary = Table(show_header=False, box=None, padding=(0, 2))
    summary.add_column(style="dim")
    summary.add_column(style="bold white")
    summary.add_column(style="dim")
    out = str(OUTPUT_DIR)
    summary.add_row("recently_rented.json", f"{len(rr_data):,} rows", f"{out}/recently_rented.json")
    summary.add_row("predictions.json", f"{n_rows:,} rows ({n_models} models)", f"{out}/predictions.json")
    summary.add_row("stats.json", f"{len(stats):,} groups", f"{out}/stats.json")
    console.print(summary)
    console.print()


if __name__ == "__main__":
    generate()
